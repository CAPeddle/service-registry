# service_registry

FastAPI project created with project-standardization skill v3.0.0

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Run development server
uvicorn src.api.main:app --reload
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific markers
pytest -m unit
pytest -m api

# Watch mode
ptw
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
service_registry/
├── src/
│   ├── api/              # API layer
│   ├── core/             # Core business logic
│   ├── models/           # Database models
│   ├── services/         # Business services
│   ├── repositories/     # Data access
│   └── config/           # Configuration
├── tests/
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── docs/                 # Documentation
└── scripts/              # Utility scripts
```

## Development

Follows **WAY_OF_WORK.md** methodology:
- SOLID principles
- Test-driven development
- Layered architecture
- Repository pattern

## Deployment

(Add deployment instructions)
