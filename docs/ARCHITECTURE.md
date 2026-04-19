# PMON-AI-OPS Backend — 系统架构文档

> 本文档描述 PMON-AI-OPS 后端系统的完整技术架构、组件职责、数据流向与 API 接口。
> 技术栈：Python 3.13 · FastAPI · uvicorn · Pydantic v2 · httpx · watchdog 6.0 · orjson

---

## 1. 系统概述

PMON-AI-OPS 后端是一个**异步事件驱动的嵌入式设备日志实时监控系统**。

**核心能力：**

- 接收设备通过 TFTP 推送的日志文件
- 实时解析日志，提取电压/电流/温度等遥测指标
- 基于正则引擎检测 Kernel Oops / Panic / Segfault 等致命错误
- 调用 DeepSeek AI（大模型）进行根因分析与补丁生成
- 通过 WebSocket 实时向前端推送 metrics 与告警

**技术特性：**

| 特性 | 说明 |
|------|------|
| 全异步架构 | 基于 asyncio + uvicorn，所有 I/O 操作非阻塞 |
| 生产者-消费者模式 | TFTP watcher → 队列 → Pipeline processor |
| 零拷贝消息分发 | WebSocket 广播基于 asyncio.Lock 并发安全 |
| AI Chain-of-Thought | DeepSeek 输出经过 CoT parser 结构化提取 |
| 指数退避重试 | AI 请求失败时自动重试 3 次，最长等待 4 秒 |
| 优雅降级 | DeepSeek API 不可用时仍可发送告警（fallback 摘要） |

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        设备端（Board）                           │
│    TFTP Client ──── push board01_20260415.log ──────────────►  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI (uvicorn) :8000                      │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ TFTP Watcher │  │   Pipeline    │  │  WebSocket Manager   │  │
│  │ (watchdog)   │  │  Processor    │  │  ConnectionManager   │  │
│  │              │  │              │  │                      │  │
│  │ · 文件检测   │  │ · 日志解析   │  │ · 连接池管理         │  │
│  │ · 稳定等待   │──│ · 指标提取   │──│ · 广播（orjson）    │  │
│  │ · 事件入队   │  │ · 错误检测   │  │ · 死连接清理         │  │
│  └──────────────┘  │ · AI 分析    │  └─────────────────────┘  │
│        ▲          │ · 告警推送   │            │                │
│        │          └──────┬───────┘            │                │
│        │                 │                    │                │
│        │          ┌───────▼────────┐          │                │
│        │          │  asyncio.Queue │          │                │
│        └──────────┤  (单生产者)    │          │                │
│                   └────────────────┘          │                │
│                                               │                │
│  HTTP API Routes (/api/*) ◄───────────────────┘                │
│  WebSocket Route (/ws) ◄───────────────────────────────────   │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
   前端浏览器           DeepSeek API           花生壳映射
   WebSocket           (LLM 分析)            (外网访问)
   ws://localhost:8000
```

---

## 3. 组件详细说明

### 3.1 事件监听层 — TFTP Watcher

**模块：** `src.core.listener.tftp_watcher`

**职责：** 实时监听 TFTP 上传目录，使用 watchdog 库监控文件系统事件，将新文件路径放入 asyncio 队列供下游处理。

**核心设计：**

```python
TFTPHandler(Queue, Loop)
  ├── dispatch(event)         # 路由到具体 on_* 方法（watchdog 6.x 兼容）
  ├── on_created(event)       # 过滤 .log/.txt/.dmp/.core 文件
  └── _enqueue(path)          # 等待写入完成 → asyncio.Queue.put()
```

**关键设计点：**

- **跨线程安全**：`on_created()` 运行在 watchdog 内部线程池线程中，通过 `asyncio.run_coroutine_threadsafe()` 将协程安全调度到主事件循环
- **文件稳定性检测**：调用 `wait_for_file_complete()` 等待文件写入稳定（0.5 秒内大小不变），避免读到截断文件
- **设备名提取**：从文件名提取设备标识（`board01_20260415.log` → `board01`）

**文件扩展名白名单：** `.log`, `.txt`, `.dmp`, `.core`

---

### 3.2 数据模型层

**模块：** `src.schemas`

统一使用 Pydantic v2 定义数据结构，与 FastAPI 路由验证无缝集成。

| 模型 | 用途 |
|------|------|
| `LogEntry` | 单条日志行：原始文本、时间戳、日志级别、设备、消息体 |
| `MetricsData` | 电压/电流/温度遥测数据（来自日志内容提取） |
| `ErrorContext` | 错误上下文：类型、首次出现行、栈追踪、寄存器 dump |
| `AIDiagnosis` | DeepSeek AI 结构化诊断结果：根因、修复建议、代码补丁 |
| `AlertPayload` | WebSocket 告警消息（最终推送格式） |
| `StreamPayload` | TFTP 文件传输事件（传输速率、字节数） |
| `MetricsPayload` | 实时遥测指标 WebSocket 消息 |

---

### 3.3 日志解析引擎

**模块：** `src.core.listener.log_parser`

**职责：** 将原始日志文件解析为结构化 `LogEntry` 列表。

**解析策略：**

1. **时间戳提取**：支持 ISO 格式（`2026-04-15T00:00:00`）和 syslog 格式（`2026/04/15 00:00:00`）
2. **日志级别推断**：基于关键词匹配推断级别
   - `CRITICAL`：PANIC、Oops、FATAL、BUG、EMERGENCY
   - `ERROR`：ERROR、PANIC、OOPS、BUG、FAULT
   - `WARNING`：WARNING、ERROR、FAIL、TIMEOUT、RETRY、OVERFLOW
3. **级别前缀清洗**：自动去除 `[INFO]`、`<WARN>`、`INFO:` 等常见前缀

**正则提取（`constants.py`）：**

| 指标 | 正则模式 |
|------|---------|
| 电压 | `voltage[:=]\s*([\d.]+)\s*(mv)?` |
| 电流 | `current[:=]\s*([\d.]+)\s*(ma)?` |
| 温度 | `temp(erature)?[:=]\s*([\d.]+)\s*(c\|°c)?` |

---

### 3.4 错误检测引擎

**模块：** `src.core.preprocessor.error_detector`

**职责：** 基于正则模式扫描 `LogEntry` 列表，识别 Kernel Oops、Panic、Segfault 等致命错误。

**检测模式：**

| 错误类型 | 正则模式 |
|---------|---------|
| Kernel Oops | `kernel\s+oops\|oops\s+#\|BUG\s+\w+` |
| Kernel Panic | `kernel\s+panic\|panic\s+at\|fatal\s+exception` |
| Segfault | `segfault\|segmentation\s+fault\|SIGSEGV` |

**上下文窗口**：检测到错误后，自动收集前后各 5 行作为 `surrounding_lines`，供 AI 分析使用。

---

### 3.5 AI 诊断引擎

**模块：** `src.core.ai_engine.client`

**职责：** 将错误上下文发送给 DeepSeek Chat API，获取结构化根因分析与修复建议。

**核心设计：**

```
DeepSeekClient
  ├── analyze(ErrorContext)      # 主入口，带重试逻辑
  ├── _get_client()              # 懒加载 httpx.AsyncClient
  ├── build_prompts()            # 组装 system + user prompt
  ├── parse_ai_response()        # 解析 CoT 输出
  └── generate_and_save_patch()  # 保存 unified diff 到 patches/
```

**重试策略（指数退避）：**

```
Attempt 1: wait 1.0s   → fail
Attempt 2: wait 2.0s   → fail
Attempt 3: wait 4.0s   → fail
→ return AIDiagnosis with fallback root_cause
```

**Chain-of-Thought 输出格式：**

```
## ANALYSIS
<AI 推理过程>
## DIFF
--- a/mm/slab.c
+++ b/mm/slab.c
@@ -100,5 +100,8 @@
     return ptr;
```

**HTTP 配置：**

- Base URL：`https://api.deepseek.com/v1`
- Model：`deepseek-chat`
- Temperature：0.2（低随机性，适合诊断任务）
- Max Tokens：1024
- Timeout：30s per request

---

### 3.6 数据处理流水线

**模块：** `src.services.pipeline`

**职责：** 异步消费 TFTP 事件队列，依次执行解析 → 指标提取 → 错误检测 → AI 分析 → 广播推送的全流程。

**流水线阶段（Pipeline Stage）：**

```
Queue.pop(TFTPFileEvent)
    │
    ├─► Stage 1: parse_log_file()        → LogEntry[]
    │
    ├─► Stage 2: dispatch_stream()        → WebSocket: StreamPayload
    │
    ├─► Stage 3: extract_metrics()         → MetricsData[]
    │       └─► dispatch_metrics()         → WebSocket: MetricsPayload
    │
    ├─► Stage 4: detect_error()            → ErrorContext | None
    │       └─► [if error]
    │           ├─► enrich_error_context()
    │           ├─► deepseek.analyze()    → AIDiagnosis
    │           └─► dispatch_alert()       → WebSocket: AlertPayload
    │
    └─► Queue.task_done()
```

**每个日志文件触发 1~3 条 WebSocket 消息：**

| 场景 | 消息数 | 消息类型 |
|------|--------|---------|
| 仅遥测数据 | 2 | `stream` + `metrics` |
| 含错误告警 | 3 | `stream` + `metrics` + `alert` |
| 仅错误无指标 | 2 | `stream` + `alert` |

---

### 3.7 WebSocket 连接管理器

**模块：** `src.core.notifier.manager`

**职责：** 管理所有活跃 WebSocket 连接，提供并发安全的广播接口。

```python
ConnectionManager
  ├── _connections: set[WebSocket]    # 活跃连接集合
  ├── _lock: asyncio.Lock             # 并发访问锁
  │
  ├── connect(websocket)              # accept() 并注册
  ├── disconnect(websocket)            # 注销连接
  ├── broadcast(payload)              # 序列化 → 发送给所有客户端
  │                                    #   · 自动跳过已断开连接
  │                                    #   · 清理 dead connections
  └── active_count                     # 当前连接数（metrics 指标）
```

**序列化优化：** 优先使用 `orjson`（比 stdlib json 快约 2 倍），不可用时 fallback 到 stdlib json。

---

### 3.8 HTTP API 层

**模块：** `src.api.router`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 存活探针，返回 `{"status":"ok"}` |
| `/api/health/deep` | GET | 完整健康检查：TFTP 目录 + DeepSeek 连通性 |
| `/api/metrics` | GET | 运行时指标：`ws_clients`、`queue_size` |
| `/api/admin/reload-config` | POST | 配置热重载（预留接口） |
| `/ws` | WebSocket | 实时消息推送（见 §3.7） |

---

## 4. 数据流向

```
TFTP 推送文件
     │
     ▼
watchdog.on_created()
     │
     ▼
asyncio.Queue.put(TFTPFileEvent)
     │
     ▼
Pipeline: while True: queue.get()
     │
     ├─► log_parser.parse_log_file()     → LogEntry[]
     │       │
     │       ▼
     │   extract_metrics()              → MetricsData[]
     │       │
     │       ▼
     │   ConnectionManager.broadcast(StreamPayload)     ──► WS Client
     │   ConnectionManager.broadcast(MetricsPayload)   ──► WS Client
     │
     └─► error_detector.detect_error()  → ErrorContext | None
             │
             ▼
         DeepSeekClient.analyze()       → AIDiagnosis
             │
             ▼
         ConnectionManager.broadcast(AlertPayload)     ──► WS Client
```

---

## 5. 配置管理

**模块：** `src.config`（基于 Pydantic Settings）

所有配置从 `.env` 文件加载，无需硬编码：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DEEPSEEK_API_KEY` | `sk-please-set-your-key` | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | API 端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |
| `TFTP_RECEIVE_DIR` | `./tftp_receive` | TFTP 接收目录 |
| `PATCHES_DIR` | `./patches` | 补丁文件存储目录 |
| `HTTP_PORT` | `8000` | HTTP/WebSocket 端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 6. 目录结构

```
backend/
├── src/
│   ├── main.py                    # FastAPI 入口 + lifespan 管理
│   ├── config.py                  # Pydantic Settings 配置
│   ├── constants.py               # 全局正则 + 关键词常量
│   │
│   ├── api/
│   │   ├── router.py              # HTTP API 路由（/api/*）
│   │   ├── websocket.py           # WebSocket 端点 (/ws)
│   │   └── deps.py                # 依赖注入工具
│   │
│   ├── core/
│   │   ├── listener/
│   │   │   ├── tftp_watcher.py    # watchdog 文件监听
│   │   │   ├── log_parser.py      # 日志文件解析
│   │   │   └── models.py          # TFTPFileEvent 数据模型
│   │   │
│   │   ├── preprocessor/
│   │   │   ├── error_detector.py  # 致命错误正则检测
│   │   │   ├── context_extractor.py # 上下文窗口提取
│   │   │   └── normalizer.py      # 日志规范化
│   │   │
│   │   ├── ai_engine/
│   │   │   ├── client.py          # DeepSeek HTTP 客户端（重试）
│   │   │   ├── prompt_builder.py  # AI Prompt 模板构建
│   │   │   ├── cot_parser.py      # CoT 输出结构化解析
│   │   │   └── patch_generator.py  # unified diff 生成与保存
│   │   │
│   │   └── notifier/
│   │       ├── manager.py         # WebSocket 连接池管理器
│   │       └── dispatcher.py      # 消息广播辅助函数
│   │
│   ├── services/
│   │   ├── pipeline.py            # 异步处理流水线
│   │   └── health.py              # 健康检查服务
│   │
│   ├── schemas/
│   │   ├── log.py                 # LogEntry / MetricsData / ErrorContext
│   │   ├── alert.py               # AlertLevel / AIDiagnosis / AlertPayload
│   │   └── ws_message.py          # WSPayload 联合类型
│   │
│   └── utils/
│       ├── logger.py              # Loguru 全局日志配置
│       ├── file_utils.py          # 文件稳定性检测
│       └── diff_formatter.py       # unified diff 格式化
│
├── tftp_receive/                  # TFTP 推送文件存放目录
├── patches/                       # AI 生成的补丁文件目录
├── logs/                          # 后端运行日志
│
├── .env                           # 环境变量配置（API Key 等）
├── .env.example                    # 配置模板
├── pyproject.toml                 # 项目元数据 + 依赖声明
├── requirements.txt               # pip 依赖清单
├── start_backend.bat              # Windows 快速启动脚本
└── README.md                      # 快速开始文档
```

---

## 7. 部署说明

### 开发环境启动

```bash
cd F:\CodingProjects\电源监控日志实时分析系统\backend
start_backend.bat
```

或手动：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
# 编辑 .env 文件，设置 DEEPSEEK_API_KEY=sk-xxx

# 3. 启动服务
python -X utf8 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level info
```

### 生产环境启动

```bash
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 花生壳内网穿透

将 `0.0.0.0:8000` 通过花生壳映射到外网：
- 协议：HTTP
- 内网端口：8000
- 外网域名：`22mj4798in35.vicp.fun:443`

---

## 8. API 参考

### HTTP 接口

#### GET /api/health

存活探针。

```bash
curl http://localhost:8000/api/health
# Response: {"status":"ok"}
```

#### GET /api/metrics

运行时指标。

```bash
curl http://localhost:8000/api/metrics
# Response: {"ws_clients":2,"queue_size":0}
```

#### GET /api/health/deep

完整健康检查。

```bash
curl http://localhost:8000/api/health/deep
```

### WebSocket 接口

**端点：** `ws://localhost:8000/ws`

连接后自动接收推送消息，无需订阅。

#### 消息类型 1：StreamPayload（TFTP 文件传输事件）

```json
{
  "type": "stream",
  "device": "board01",
  "lines_per_sec": 4.29,
  "bytes_transferred": 429
}
```

#### 消息类型 2：MetricsPayload（实时遥测）

```json
{
  "type": "metrics",
  "device": "board01",
  "voltage_mv": 3298.0,
  "current_ma": 448.0,
  "temp_c": 43.5
}
```

#### 消息类型 3：AlertPayload（告警）

```json
{
  "type": "alert",
  "id": "alert-1744657757.956",
  "device": "board01",
  "level": "WARNING",
  "summary": "Kernel Oops detected at mm/slab.c:2847",
  "ai_suggestion": "Allocate zeroed pages before calling kmalloc...",
  "patch_content": "--- a/mm/slab.c\n+++ b/mm/slab.c\n@@ -100,5 +100,8 @@",
  "timestamp": "2026-04-15T07:20:05.000000"
}
```

---

*文档版本：v1.0 | 生成时间：2026-04-15*
