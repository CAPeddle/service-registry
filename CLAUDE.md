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

## Deployment

**Production Server:** 192.168.2.48 (Ubuntu)
**Service Location:** `/home/cpeddle/service-registry`
**Virtual Environment:** `.venv` (not `venv`)
**Service Name:** `service-registry.service`

### Deployment Workflow

**Investigate → Fix → Test → Commit → Deploy**

1. **SSH Access**: `ssh cpeddle@192.168.2.48`
2. **Investigation**: Debug issues remotely, capture errors
3. **Fix Locally**: Return to local dev, write tests, fix code
4. **Commit**: Git commit and push to origin
5. **Deploy**: SSH to server, `git pull`, `sudo systemctl restart service-registry`

### Important Notes

- ✅ **ALWAYS** fix code locally, never edit on server
- ✅ **ALWAYS** write tests for bug fixes
- ✅ **ALWAYS** commit before deploying
- ❌ **NEVER** make quick fixes directly on production
- ❌ **NEVER** skip version control

### Service Management

```bash
# View logs
sudo journalctl -u service-registry -f

# Restart service
sudo systemctl restart service-registry

# Check status
sudo systemctl status service-registry

# Pull latest code
cd /home/cpeddle/service-registry
git pull origin master
```

### Systemd Service Configuration

**Path**: `/etc/systemd/system/service-registry.service`
**User**: `root` (required for systemctl/ss commands)
**WorkingDirectory**: `/home/cpeddle/service-registry`
**Port**: 8000 (Nginx proxies from port 80)

**Critical**: Service needs full PATH including system binaries:
```
Environment="PATH=/home/cpeddle/service-registry/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

---

## Notes

Project follows:
- SOLID principles
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple)
- YAGNI (You Aren't Gonna Need It)
- Test-driven development
- **Remote debugging workflow** (see WAY_OF_WORK.md)
