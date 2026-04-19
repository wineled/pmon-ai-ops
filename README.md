# PMON-AI-OPS

> 电源监控日志实时分析系统 — Embedded Power Monitor with AI-Powered Log Analysis

## Architecture

```
TFTP PUT → watchdog → log_parser → error_detector → DeepSeek CoT → WebSocket → React UI
                                                                    ↘ patch_generator
```

**Backend**: Python 3.11+ / FastAPI / WebSocket / watchdog / DeepSeek API
**Frontend**: React 18 / TypeScript / Vite / Tailwind CSS / ECharts / Zustand

## Quick Start

```bash
# Start all services (backend + frontend + proxy)
python pmon.py start

# Stop / Restart / Status / Logs
python pmon.py stop|restart|status|logs
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/docs (Swagger)
- External (花生壳): https://22mj4798in35.vicp.fun

## Project Structure

```
pmon-ai-ops/
├── backend/                   # Python FastAPI backend
│   ├── src/
│   │   ├── main.py            # FastAPI app + lifespan
│   │   ├── config.py          # Pydantic Settings (.env)
│   │   ├── constants.py       # Shared constants
│   │   ├── api/               # HTTP + WebSocket routes
│   │   ├── core/              # Business logic
│   │   │   ├── ai_engine/     # DeepSeek client, CoT parser, prompt builder
│   │   │   ├── listener/      # TFTP watcher, log parser
│   │   │   ├── notifier/      # WebSocket manager, dispatcher
│   │   │   └── preprocessor/  # Context extractor, error detector
│   │   ├── schemas/           # Pydantic models
│   │   ├── services/          # High-level services (pipeline, disasm, LLM, CFG, etc.)
│   │   └── utils/             # Helpers (logger, diff, file ops)
│   ├── tests/                 # Test suite (pytest)
│   ├── .env.example           # Environment template
│   └── pyproject.toml         # Python project config
├── frontend/                  # React + TypeScript frontend
│   ├── src/
│   │   ├── components/        # UI components
│   │   ├── pages/             # Route pages
│   │   ├── hooks/             # Custom hooks (useWebSocket)
│   │   ├── store/             # Zustand stores
│   │   ├── lib/               # Utilities & types
│   │   └── router/            # Route definitions
│   ├── tests/                 # Frontend test suite
│   └── package.json
├── tools/                     # Dev & ops utilities
│   ├── mock_tftp_push.py      # Simulate TFTP file upload
│   ├── http_proxy.py          # HTTP reverse proxy (:10444 → :5173)
│   ├── https_proxy.py         # HTTPS reverse proxy (:10443 → :5173)
│   ├── screenshot.cjs         # Puppeteer screenshot tool
│   └── query_db.py            # 花生壳 DB query utility
├── docs/                      # Documentation
├── pmon.py                    # Unified service manager
└── .gitignore
```

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | (required) | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | API endpoint |
| `TFTP_RECEIVE_DIR` | `./tftp_receive` | TFTP log directory |
| `CODE_INDEX_DIRS` | `../,../../` | Code index dirs for LLM (comma-separated) |
| `HTTP_PORT` | `8000` | Backend HTTP port |
| `LOG_LEVEL` | `INFO` | Logging level |

## Testing

```bash
cd backend
pytest                          # All tests
pytest tests/test_disasm_service.py -v   # Specific module
pytest -k "TestFR" --tb=short   # By keyword
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/logs` | Recent logs |
| GET | `/api/alerts` | Recent alerts |
| WS | `/ws` | Real-time log/alert stream |
| POST | `/api/disasm/upload` | Upload binary for disassembly |
| POST | `/api/disasm/disasm` | Disassemble binary |
| POST | `/api/llm/log` | LLM-powered log analysis |
| POST | `/api/llm/index` | Build code index |

## License

Private project.
