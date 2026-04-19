# PMON-AI-OPS 前端组件架构文档

> 版本：v1.0.0 | 日期：2026-04-14 | 技术栈：React 18 + TypeScript + Vite + Tailwind CSS + ECharts + Zustand

---

## 1. 整体架构概览

### 1.1 系统定位

PMON-AI-OPS（Power MONitoring with AI Operations）前端是电源监控日志实时分析系统的可视化界面，负责连接后端 AI Agent 服务，以实时仪表盘和告警日志两种视图呈现电源监控数据。系统采用典型的前后端分离架构（CSR），前端通过 WebSocket 与 Agent 交互，获取实时指标、日志流和 AI 告警。

### 1.2 技术选型

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 框架 | React 18 + React Router v6 | 组件化 UI + 声明式路由 |
| 语言 | TypeScript 5 | 静态类型保障，降低运行时错误 |
| 构建 | Vite 5 | 基于 ESM 的极速开发服务器 |
| 样式 | Tailwind CSS 3 | 原子化 CSS，driven by CSS 变量 |
| 图表 | Apache ECharts (via `echarts-for-react`) | 双 Y 轴时序折线图，电压/电流双系列 |
| 状态 | Zustand | 轻量级状态管理，Store 分离为 AppStore / DataStore |
| UI 原语 | Radix UI (`@radix-ui/react-scroll-area`) | 无障碍、可访问的基础 UI 组件 |
| 样式工具 | `clsx` + `tailwind-merge` (cn util) | 动态类名合并 |
| 语法高亮 | `react-syntax-highlighter` (Prism) | 告警 Patch diff 着色 |
| 图标 | `lucide-react` | 一致的 SVG 图标集 |

---

## 2. 项目文件结构

```
frontend/src/
├── main.tsx                     # 入口点，React 18 createRoot 挂载
├── App.tsx                      # 根组件 + React Router 路由声明
├── index.css                    # Tailwind CSS 入口，CSS 变量 / 全局样式
│
├── router/
│   └── index.tsx                # createBrowserRouter 路由配置（备用）
│
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx          # 可折叠侧边导航栏
│   │   └── Header.tsx           # 顶部状态栏（连接状态 + 测试模式开关）
│   ├── dashboard/
│   │   ├── MetricsGrid.tsx      # 四格指标卡片（电压/电流/温度/日志速率）
│   │   ├── PowerGauge.tsx       # ECharts 双 Y 轴时序折线图
│   │   └── LogStream.tsx        # 实时日志流 + 色彩分类
│   └── ui/                      # 原子化基础 UI 组件（Radix UI 封装）
│       ├── card.tsx             # Card / CardHeader / CardContent / CardTitle
│       ├── badge.tsx            # Badge（CVA 变体：default / destructive / warning / info）
│       ├── button.tsx           # Button（CVA 变体 + Radix Slot asChild）
│       ├── progress.tsx         # Progress（Radix Progress 封装）
│       └── scroll-area.tsx      # ScrollArea（Radix ScrollArea 封装）
│
├── pages/
│   ├── DashboardPage.tsx       # 监控面板页（MetricsGrid + PowerGauge + LogStream）
│   └── AlertsPage.tsx          # AI 告警日志页（可折叠告警卡片 + Patch 高亮）
│
├── hooks/
│   └── useWebSocket.ts         # WebSocket 生命周期 + 测试模式模拟数据生成
│
├── lib/
│   ├── types.ts                 # TypeScript 类型定义（AgentPayload 联合类型）
│   ├── utils.ts                 # cn() / formatDateTime() / generateId()
│   └── websocket.ts            # WebSocketClient 类（单例，指数退避重连）
│
└── store/
    ├── useAppStore.ts          # App 级状态（sidebarCollapsed / testMode / wsConnected）
    └── useDataStore.ts         # Data 级状态（metricsHistory / logs / alerts / streamStats）
```

---

## 3. 核心组件详解

### 3.1 布局组件（Layout Layer）

#### `<Sidebar />`
**文件**: `components/layout/Sidebar.tsx`  
**职责**: 提供全局导航入口，支撑应用整体框架布局。

**技术实现**:
- **固定定位**: `fixed left-0 top-0 h-screen`，不受页面滚动影响
- **可折叠**: 折叠态 `w-16` / 展开态 `w-56`，通过 `sidebarCollapsed` 状态驱动，`transition-all duration-300` 动画
- **导航激活**: `useLocation()` 获取当前路径，与 `navItems` 逐项比对，`isActive` 触发 `bg-slate-800 text-slate-50` 样式
- **图标**: `lucide-react`，每个导航项独立 Icon（`LayoutDashboard`、`AlertTriangle`）
- **折叠按钮**: 绝对定位 `bottom-4 right-0`，圆形 `rounded-full border`，切换时图标从 `ChevronRight` 变为 `ChevronLeft`
- **Tailwind 条件类**: `cn()` 合并静态类 + 动态 `isActive` 类名

**关键代码片段**:
```tsx
<aside className={cn(
  "fixed left-0 top-0 z-40 h-screen border-r border-slate-800 bg-slate-900",
  sidebarCollapsed ? "w-16" : "w-56"
)}>
  {/* Logo */}
  <div className="flex h-16 items-center justify-center border-b border-slate-800">
    <Zap className="h-6 w-6 text-yellow-500" />
    {!sidebarCollapsed && <span className="ml-2 text-lg font-bold text-slate-50">PMON-AI-OPS</span>}
  </div>
  {/* Navigation */}
  <nav className="flex flex-col gap-1 p-3">
    {navItems.map((item) => (
      <Link key={item.path} to={item.path} className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
        isActive ? "bg-slate-800 text-slate-50" : "text-slate-400 hover:bg-slate-800"
      )}>
        <Icon className="h-5 w-5 flex-shrink-0" />
        {!sidebarCollapsed && <span>{item.label}</span>}
      </Link>
    ))}
  </nav>
</aside>
```

#### `<Header />`
**文件**: `components/layout/Header.tsx`  
**职责**: 展示 WebSocket 连接状态和测试模式开关，右侧为操作控制区。

**技术实现**:
- **动态左边距**: `left-56`（展开态）或 `left-16`（折叠态），与 Sidebar 宽度联动，`transition-all duration-300` 同步动画
- **连接状态指示器**: 绿色（`bg-green-900/30 text-green-400`）或红色（`bg-red-900/30 text-red-400`），根据 `wsConnected || testMode` 判断
- **测试模式按钮**: `Button variant={testMode ? "destructive" : "outline"}`，点击 `toggleTestMode` 切换

---

### 3.2 数据展示组件（Dashboard Components）

#### `<MetricsGrid />`
**文件**: `components/dashboard/MetricsGrid.tsx`  
**职责**: 以 2×2（四列 lg 断点）网格布局展示四个实时核心指标。

**指标定义**:

| 指标 | 图标 | 数据字段 | 单位 | 颜色主题 |
|------|------|----------|------|----------|
| 电压 | `Zap` (Lucide) | `currentMetrics.voltage_mv` | mV | 蓝色系 `text-blue-400` |
| 电流 | `Activity` (Lucide) | `currentMetrics.current_ma` | mA | 琥珀色系 `text-amber-400` |
| 温度 | `Thermometer` (Lucide) | `currentMetrics.temp_c` | °C | 红色系 `text-red-400` |
| 日志速率 | `FileText` (Lucide) | `streamStats.linesPerSec` | 行/秒 | 绿色系 `text-green-400` |

**`<AnimatedNumber />` 子组件**:
- 用途：数值变化时执行缓动插值动画（Easing），提升数据刷新时的视觉平滑度
- 实现：每 30ms 执行一步插值 `step = diff / 10`，共 10 步到达目标值
- 特点：当变化量 `< 0.01` 时直接跳变，避免微小抖动触发动画

**CSS Grid 响应式**:
```tsx
<div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
  {/* 移动端 2 列，平板/桌面 4 列 */}
```

#### `<PowerGauge />`
**文件**: `components/dashboard/PowerGauge.tsx`  
**职责**: ECharts 折线图，展示最近 30 秒（60 个数据点）的电压/电流时序变化。

**ECharts 配置要点**:

- **双 Y 轴设计**：
  - 左侧 Y 轴（`position: 'left'`）：电压量程 11000–13000 mV，蓝色 `#3b82f6`
  - 右侧 Y 轴（`position: 'right'`）：电流量程 350–550 mA，琥珀色 `#f59e0b`
- **面积填充**：`areaStyle` 使用线性渐变（`linearGradient`），顶部 30% 透明度，底部接近 0，平滑过渡
- **数据窗口**：`MAX_METRICS_POINTS = 60`，每 500ms 一个采样点，覆盖 30 秒
- **平滑曲线**：`smooth: true`，`lineStyle.width: 2`
- **空数据降级**：无数据时显示「等待数据...」，不渲染空图表

**数据源**: `metricsHistory: MetricsDataPoint[]`，从 `useDataStore` 获取，X 轴为 `toLocaleTimeString('zh-CN', { hour12: false })`。

#### `<LogStream />`
**文件**: `components/dashboard/LogStream.tsx`  
**职责**: 实时滚动日志展示面板，按日志级别着色，自动跟底。

**技术实现**:
- **虚拟滚动区域**：`ScrollArea`（Radix UI），固定高度 280px，垂直滚动条
- **自动跟底**：`useEffect` 监听 `logs` 变化，执行 `scrollTop = scrollHeight`，确保新日志出现时视图自动滚动到底部
- **色彩分类逻辑**：

| 日志关键词 | 颜色类名 | 含义 |
|------------|----------|------|
| `[ALERT:CRITICAL]` | `text-red-400` | 危险告警 |
| `[ALERT:WARNING]` | `text-yellow-400` | 警告告警 |
| `[ALERT:INFO]` | `text-blue-400` | 信息告警 |
| `[STREAM]` | `text-green-400` | 流数据统计 |
| 其他 | `text-slate-300` | 普通日志 |

- **清空按钮**：Header 右侧 `Trash2` 图标，触发 `clearLogs()`
- **时间戳格式**：`[HH:mm:ss]`，24 小时制，`hour12: false`

---

### 3.3 告警组件（Alert Components）

#### `<AlertsPage />`
**文件**: `pages/AlertsPage.tsx`  
**职责**: 展示 AI 分析后的告警列表，支持展开查看详情、Patch diff 和一键复制。

**告警数据结构** (`AlertPayload`):
```typescript
interface AlertPayload {
  type: 'alert';
  id: string;                    // 唯一标识
  device: string;               // 触发设备
  level: 'CRITICAL' | 'WARNING' | 'INFO';  // 告警级别
  summary: string;               // 告警摘要
  ai_suggestion: string;         // AI 分析建议
  patch_content?: string;        // 可选的修复 Patch（diff 格式）
  timestamp: string;            // ISO 时间戳
}
```

**可折叠卡片设计**:
- 收起态：显示告警级别 Badge + 摘要 + 设备 + 时间
- 展开态 (`expandedId === alert.id`)：增加 AI 建议区 + Patch diff 区
- 展开图标：`ChevronRight` / `ChevronDown`，随状态切换

**Patch 高亮**:
- 使用 `react-syntax-highlighter` 的 Prism 引擎
- 语言指定为 `diff`，使用 `oneDark` 主题（深色主题）
- 复制按钮：点击 `navigator.clipboard.writeText(patch)`，2 秒后恢复「复制」状态

**Badge 变体**（`badgeVariants`）:
| 变体 | 颜色 | 用途 |
|------|------|------|
| `critical` | 红色 `#dc2626` | CRITICAL 级别 |
| `warning` | 黄色 `#eab308` | WARNING 级别 |
| `info` | 蓝色 `#3b82f6` | INFO 级别 |

---

## 4. 状态管理（Zustand）

### 4.1 `useAppStore` — 应用级状态

```typescript
interface AppState {
  sidebarCollapsed: boolean      // 侧边栏折叠态
  testMode: boolean              // 测试模式开关（开启后使用模拟数据）
  wsConnected: boolean           // WebSocket 连接状态
  toggleSidebar: () => void
  toggleTestMode: () => void
  setWsConnected: (connected: boolean) => void
}
```

**特点**：全局单例，无需 Context API 封装，直接在组件中 `useAppStore()` 调用。

### 4.2 `useDataStore` — 数据级状态

```typescript
interface DataState {
  metricsHistory: MetricsDataPoint[]   // 时序数据（最多 60 点，30 秒窗口）
  currentMetrics: MetricsDataPoint | null  // 最新一条指标
  logs: LogEntry[]                     // 日志列表（最多 500 条，FIFO）
  alerts: AlertPayload[]              // 告警列表（最多 100 条，新在前）
  streamStats: { linesPerSec: number; bytesTransferred: number } | null
}
```

**关键设计**：
- `metricsHistory` 固定窗口 `MAX_METRICS_POINTS = 60`，新数据 `push` 后 `shift()` 保持长度
- `logs` 最多 500 条，日志量较大时防止内存泄漏
- `alerts` 最多 100 条且 `unshift`（新在前），告警历史倒序展示

---

## 5. WebSocket 通信层

### 5.1 `WebSocketClient` 类
**文件**: `lib/websocket.ts`  
**模式**: 单例模式（`export const wsClient = new WebSocketClient()`）

**核心能力**:

| 能力 | 实现 |
|------|------|
| 自动重连 | 指数退避：`delay = 1000 * 2^attempts`，最多 10 次 |
| 心跳保活 | 每 30 秒发送 `ping`，检测连接存活 |
| 消息订阅 | `Set<MessageHandler>` 订阅者模式，`subscribe()` 返回取消订阅函数 |
| 状态同步 | `syncStatus()` 同步至 `useAppStore.wsConnected` |
| JSON 解析 | `JSON.parse` 包裹在 `try/catch`，解析失败不影响连接 |

**WebSocket URL**: `ws://localhost:8765`（`wsClient` 构造函数默认值）

### 5.2 `useWebSocket` Hook
**文件**: `hooks/useWebSocket.ts`  
**职责**: 在 Layout 组件挂载时初始化，管理 WebSocket 生命周期和测试模式模拟。

**双模式逻辑**:
```
testMode === true  →  startMockMode()      模拟数据生成
testMode === false →  wsClient.connect()    连接真实 Agent
```

**测试模式数据生成**（每 500ms）：
- **指标数据**：`voltage_mv: 12000±250mV`，`current_ma: 450±50mA`，`temp_c: 48±4°C`
- **日志数据**：概率 30% 生成设备日志（`pmu_read_regs`、`thermal_zone` 等）
- **告警数据**：概率 5% 生成告警（CRITICAL/WARNING/INFO 随机），50% 含 Patch diff

**消息路由**（`handleMessage`）:

| Payload 类型 | 处理动作 |
|--------------|----------|
| `stream` | 更新 `streamStats` → 添加带 `[STREAM]` 前缀的日志 |
| `metrics` | 更新 `metricsHistory` + `currentMetrics` |
| `alert` | 添加告警到 `alerts` 列表 → 添加带 `[ALERT:LEVEL]` 前缀的日志 |

---

## 6. 类型系统

### 6.1 联合类型 — `AgentPayload`

```typescript
export type AgentPayload = StreamPayload | MetricsPayload | AlertPayload;
```

TypeScript 的联合类型确保每个 handler 需通过 `payload.type` 字段 narrowing 再访问特定字段。

### 6.2 类型守卫模式

```typescript
switch (payload.type) {
  case 'stream':   // payload 被 narrowing 为 StreamPayload
    updateStreamStats({ linesPerSec: payload.lines_per_sec, ... });
    break;
  case 'metrics':  // payload 被 narrowing 为 MetricsPayload
    addMetrics({ voltage_mv: payload.voltage_mv, ... });
    break;
  case 'alert':   // payload 被 narrowing 为 AlertPayload
    addAlert(payload);
    break;
}
```

---

## 7. 路由架构

### 7.1 嵌套路由设计

```
/ (Layout 布局组件，作为父路由)
├── /dashboard  → <DashboardPage />   (默认重定向)
└── /alerts     → <AlertsPage />
```

**实现方式**：React Router v6 嵌套路由 + `<Outlet />`

- `App.tsx` 中的 `<Routes>` 定义路由树
- `<Layout />` 组件内 `<Outlet />` 渲染匹配到的子路由
- Layout 层统一挂载 `<Sidebar />`、`<Header />` 和 `<useWebSocket />`

---

## 8. UI 基础组件库

所有基础 UI 组件均基于 **Radix UI** 原语封装，外层包裹 **Tailwind CSS**，使用 **CVA**（Class Variance Authority）管理多变体。

### 8.1 统一模式

```typescript
// CVA 定义变体
const badgeVariants = cva("base-classes", {
  variants: { variant: { critical: "bg-red-600", warning: "bg-yellow-500" } },
  defaultVariants: { variant: "default" }
})

// React.forwardRef 透传 ref
const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, ...props }, ref) =>
    <div ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />
)
```

### 8.2 组件清单

| 组件 | 基于 | 变体 |
|------|------|------|
| `Card` | 原生 `div` | — |
| `CardHeader` | 原生 `div` | flex + padding |
| `CardTitle` | 原生 `h3` | — |
| `CardContent` | 原生 `div` | `pt-0` 覆盖 |
| `Badge` | 原生 `div` | `default / secondary / destructive / outline / critical / warning / info` |
| `Button` | 原生 `button` + Radix `Slot` | `default / destructive / outline / secondary / ghost / link` × `size` |
| `Progress` | Radix `ProgressPrimitive.Root` | — |
| `ScrollArea` | Radix `ScrollAreaPrimitive.Root` | 垂直/水平滚动条自适应 |

---

## 9. 工具函数

### `cn()` — 类名合并
```typescript
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```
- `clsx`：处理字符串/数组/对象类名拼接
- `twMerge`：自动合并 Tailwind 同类冲突（如 `pl-2 pl-4` → `pl-4`）

### `formatDateTime()` — 日期时间格式化
```typescript
toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
// → "04/14 23:03:01"
```

### `generateId()` — 唯一 ID 生成
```typescript
Math.random().toString(36).substring(2, 15)
// → 8 位短 ID，用于日志/告警 key
```

---

## 10. 部署与网络架构

```
[外网用户]
    ↓ HTTPS
[花生壳反向代理]  22mj4798in35.vicp.fun:443
    ↓ HTTP
[Python HTTP 代理]  127.0.0.1:10444
    ↓ HTTP
[Vite Dev Server]  192.168.10.5:5173
    ↓
[WebSocket] ws://localhost:8765
[PMON AI Agent Backend]
```

> 注：花生壳 HTTP 映射与 Vite chunked transfer encoding 存在协议兼容性问题，线上部署建议使用 Nginx 作为 HTTP/HTTPS 终止层。

---

*文档生成时间：2026-04-14 | 由 QClaw AI Assistant 自动生成*
