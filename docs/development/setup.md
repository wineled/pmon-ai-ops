# 开发环境搭建指南

## 前置要求

- Python 3.11+
- Node.js 20+
- Git
- Make (可选，用于使用 Makefile)
- Docker (可选，用于容器化开发)

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/wineled/pmon-ai-ops.git
cd pmon-ai-ops
```

### 2. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置必要的变量
# 特别是 DEEPSEEK_API_KEY
```

### 3. 安装依赖

使用 Makefile (推荐):
```bash
make install
```

或手动安装:
```bash
# 后端
cd backend
pip install -e ".[dev]"

# 前端
cd ../frontend
npm install
```

### 4. 启动开发环境

使用 pmon.py:
```bash
python pmon.py start
```

或使用 Makefile:
```bash
make dev
```

单独启动:
```bash
# 仅后端
make dev-backend

# 仅前端
make dev-frontend
```

### 5. 访问服务

- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

## 项目结构说明

```
pmon-ai-ops/
├── backend/           # Python FastAPI 后端
│   ├── src/          # 源代码
│   ├── tests/        # 测试文件
│   └── pyproject.toml # Python 项目配置
├── frontend/          # React TypeScript 前端
│   ├── src/          # 源代码
│   ├── tests/        # 测试文件
│   └── package.json  # Node 依赖配置
├── docker/           # Docker 配置
├── docs/             # 文档
├── tools/            # 开发工具
└── scripts/          # 脚本文件
```

## 开发工作流

### 代码规范

我们使用以下工具保证代码质量:

- **Python**: ruff (lint + format), mypy (type check)
- **TypeScript**: ESLint, Prettier

运行检查:
```bash
make lint          # 运行所有 linter
make format        # 格式化代码
make typecheck     # 类型检查
make check         # 运行所有检查
```

### 测试

```bash
make test          # 运行所有测试
make test-backend  # 仅后端测试
make coverage      # 生成覆盖率报告
```

### Git 工作流

1. 创建功能分支: `git checkout -b feature/your-feature`
2. 提交更改: `git commit -m "feat: add something"`
3. 推送分支: `git push origin feature/your-feature`
4. 创建 Pull Request

提交信息规范:
- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

## 常用命令

| 命令 | 说明 |
|------|------|
| `make help` | 显示所有可用命令 |
| `make dev` | 启动开发环境 |
| `make stop` | 停止所有服务 |
| `make restart` | 重启服务 |
| `make status` | 查看服务状态 |
| `make logs` | 查看日志 |
| `make test` | 运行测试 |
| `make lint` | 代码检查 |
| `make build` | 构建生产版本 |

## 调试技巧

### 后端调试

1. 使用 VSCode 调试配置 (已包含在 .vscode/launch.json)
2. 设置断点并按 F5 启动调试
3. 或使用 `print()` + `make logs` 查看输出

### 前端调试

1. 浏览器 DevTools
2. React Developer Tools 扩展
3. Redux DevTools (Zustand 兼容)

### 常见问题

**Q: 端口被占用**
```bash
# 查找占用端口的进程
netstat -ano | findstr :8000

# 使用 pmon.py 自动清理
python pmon.py stop
```

**Q: 依赖安装失败**
```bash
# 清理后重新安装
cd backend && pip cache purge && pip install -e ".[dev]"
cd frontend && rm -rf node_modules && npm install
```

**Q: WebSocket 连接失败**
- 检查后端是否正常运行
- 检查防火墙设置
- 查看浏览器控制台网络日志

## Docker 开发

使用 Docker 可以隔离开发环境:

```bash
# 构建镜像
make docker-build

# 启动服务
make docker-up

# 查看日志
make docker-logs

# 停止服务
make docker-down
```

## 贡献指南

1. Fork 仓库
2. 创建特性分支
3. 确保测试通过
4. 提交 Pull Request

## 获取帮助

- 查看 [API 文档](./api/openapi.yaml)
- 查看 [架构文档](./architecture/overview.md)
- 提交 Issue
