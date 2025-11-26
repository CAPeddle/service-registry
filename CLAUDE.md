# service_registry - Claude Context

**Project Type:** Python FastAPI  
**Last Updated:** 2025-11-26  
**Skill Version:** 3.0.0

---

## Project Overview

**Purpose:** [Describe your project]

**Key Features:**
- FastAPI REST API
- Layered architecture
- pytest testing infrastructure
- SQLAlchemy ORM

---

## Technical Stack

**Language:** Python 3.11+

**Frameworks:**
- FastAPI 0.104+
- SQLAlchemy 2.0+
- Pydantic 2.5+

**Key Dependencies:**
- uvicorn (ASGI server)
- pytest (testing)
- alembic (migrations)

**Testing Framework:** pytest

---

## Architecture

**Structure:**
```
service_registry/
├── src/
│   ├── api/          # HTTP interface
│   ├── services/     # Business logic
│   ├── repositories/ # Data access
│   ├── models/       # Domain models
│   └── core/         # Shared utilities
├── tests/            # Test suite
└── docs/             # Documentation
```

**Key Components:**
1. **API Layer**: FastAPI routes and schemas
2. **Service Layer**: Business logic
3. **Repository Layer**: Data access abstraction
4. **Models**: SQLAlchemy models

---

## Development Workflow

**Following:** WAY_OF_WORK.md (universal standards)

**Project-Specific Practices:**
- Use pytest for all testing
- Follow layered architecture pattern
- Repository pattern for data access
- Type hints everywhere

---

## Current Status

**Development Phase:** Initial Setup

**Recent Work:**
- Project structure created
- Basic FastAPI app configured
- Testing infrastructure established

**Next Priorities:**
1. Define domain models
2. Implement core business logic
3. Create API endpoints
4. Write comprehensive tests

---

## Standards Compliance

**Skill:** project-standardization v3.0.0

**Required Skills:**
- fastapi-review (for code review)
- test-driven-development (for TDD)
- systematic-debugging (for troubleshooting)

---

## Quick Commands

```bash
# Run development server
uvicorn src.api.main:app --reload

# Run tests
pytest

# Run with coverage
pytest --cov

# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/
```

---

## Notes

Project follows:
- SOLID principles
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple)
- YAGNI (You Aren't Gonna Need It)
- Test-driven development
