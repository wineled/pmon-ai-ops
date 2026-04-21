# AI-Ops

> 人工智能运维系统 — 日志实时分析、AI 诊断、二进制反汇编

[![CI](https://github.com/wineled/pmon-ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/wineled/pmon-ai-ops/actions/workflows/ci.yml)
[![Docker](https://github.com/wineled/pmon-ai-ops/actions/workflows/docker.yml/badge.svg)](https://github.com/wineled/pmon-ai-ops/actions/workflows/docker.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 20+](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-Private-red.svg)](LICENSE)

## Architecture

```
TFTP PUT → watchdog → log_parser → error_detector → LLM CoT → WebSocket → React UI
                                                                    ↘ patch_generator
```

**Backend**: Python 3.11+ / FastAPI / WebSocket / watchdog / Groq API  
**Frontend**: React 18 / TypeScript / Vite / Tailwind CSS / ECharts / Zustand

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git

### 1. Clone & Setup

```bash
git clone https://github.com/wineled/pmon-ai-ops.git
cd pmon-ai-ops

# Run setup script
./scripts/setup.sh

# Or use Make
make install
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and set DEEPSEEK_API_KEY
```

### 3. Start Development

```bash
# Start all services
make dev

# Or use pmon.py
python pmon.py start
```

### 4. Access Services

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000/docs (Swagger)
- **WebSocket**: ws://localhost:8000/ws
- **External** (花生壳): https://22mj4798in35.vicp.fun

## Project Structure

```
pmon-ai-ops/
├── backend/              # Python FastAPI backend
│   ├── src/
│   │   ├── api/         # HTTP + WebSocket routes
│   │   ├── core/        # Business logic
│   │   │   ├── ai_engine/      # DeepSeek integration
│   │   │   ├── listener/       # TFTP watcher
│   │   │   ├── notifier/       # WebSocket manager
│   │   │   └── preprocessor/   # Log processing
│   │   ├── schemas/     # Pydantic models
│   │   ├── services/    # High-level services
│   │   └── utils/       # Utilities
│   ├── tests/           # Test suite
│   └── pyproject.toml   # Python config
├── frontend/            # React TypeScript frontend
│   ├── src/
│   │   ├── components/  # UI components
│   │   ├── pages/       # Route pages
│   │   ├── hooks/       # Custom hooks
│   │   ├── store/       # Zustand stores
│   │   └── lib/         # Utilities
│   └── package.json
├── docker/              # Docker configurations
├── docs/                # Documentation
├── scripts/             # Utility scripts
├── tools/               # Dev tools
├── Makefile             # Unified commands
└── pmon.py              # Service manager
```

## Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all commands |
| `make dev` | Start development environment |
| `make stop` | Stop all services |
| `make restart` | Restart services |
| `make status` | Check service status |
| `make logs` | Tail logs |
| `make test` | Run all tests |
| `make lint` | Run linters |
| `make format` | Format code |
| `make build` | Build production |
| `make docker-up` | Start with Docker |

## Development

### Code Quality

```bash
# Run all checks
make check

# Individual checks
make lint        # Run linters
make format      # Format code
make typecheck   # Type checking
make test        # Run tests
make coverage    # Coverage report
```

### Testing

```bash
# Backend tests
cd backend && pytest -v

# Specific test
pytest tests/test_disasm_service.py -v

# With coverage
pytest --cov=src --cov-report=html
```

### Docker

```bash
# Build images
make docker-build

# Start services
make docker-up

# View logs
make docker-logs

# Stop services
make docker-down
```

## Configuration

Key environment variables (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key (free tier) |
| `DEEPSEEK_BASE_URL` | No | LLM API endpoint (default: `https://api.groq.com/openai/v1`) |
| `DEEPSEEK_MODEL` | No | LLM model (default: `llama-3.3-70b-versatile`) |
| `TFTP_RECEIVE_DIR` | No | TFTP log directory (default: `./tftp_receive`) |
| `HTTP_PORT` | No | Backend port (default: `8000`) |
| `VITE_PORT` | No | Frontend port (default: `5173`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Development Setup](docs/development/setup.md)
- [API Documentation](http://localhost:8000/docs) (when running)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/logs` | Recent logs |
| GET | `/api/alerts` | Recent alerts |
| WS | `/ws` | Real-time stream |
| POST | `/api/disasm/upload` | Upload binary |
| POST | `/api/disasm/disasm` | Disassemble |
| POST | `/api/llm/log` | LLM analysis |

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'feat: add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

### Commit Convention

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code refactoring
- `test:` Tests
- `chore:` Build/tools

## License

Private project - All rights reserved.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Groq](https://groq.com/) - LLM inference engine (free tier)
- [React](https://react.dev/) - UI library
- [Tailwind CSS](https://tailwindcss.com/) - CSS framework
