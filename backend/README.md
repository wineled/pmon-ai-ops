# PMON-AI-OPS Backend

## Quick Start

```bash
# From project root
python pmon.py start

# Or run backend only
cd backend
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

Copy `.env.example` to `.env` and set your values.

## Testing

```bash
pytest                    # All tests
pytest -k test_disasm     # Specific tests
pytest --tb=short -v      # Verbose with short tracebacks
```

## API Docs

When running, visit http://localhost:8000/docs for Swagger UI.
