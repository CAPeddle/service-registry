# service_registry - Claude Context

**Project Type:** Python FastAPI
**Last Updated:** 2026-11-22
**Skill Version:** 3.0.0

---

## Project Overview

**Purpose:** A landing page for the Z2 home server (192.168.2.48, hostname `z2`). It lists every service listening on a TCP port, discovered live on each page load, and shows how each can be reached (LAN, tailnet, internal only).

**Key Features:**
- Live discovery from `ss`, `/proc/<pid>/cgroup`, `docker ps`, `tailscale serve status --json`, `ufw status verbose` and `systemctl show` (about 10 s cache; Refresh link bypasses it)
- Per-row reachability: LAN link, blocked by firewall, tailnet only, internal only, reachability unknown
- Links only when the port answers HTTP (probed on 127.0.0.1) or a link override is set
- Annotations (SQLite table `annotations`, keyed by identity such as `system:<unit>`, `docker:<project>/<service>`, `manual:<name>`): display name, description, hidden, link override, health path, primary port; edited from the page
- REST API for annotations (`/api/services`), `/api/v1/health`, `/docs`
- No scan page or scan endpoint; nothing needs to be registered
- Layered architecture, pytest suite

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
│   ├── services/     # discovery/ (sockets, cgroups, units, docker_ports,
│   │                 #   tailscale_serve, firewall, inventory, cache), health_check.py
│   ├── repositories/ # annotation_repository.py
│   ├── models/       # annotation.py (current), service.py (legacy table, imported once)
│   └── core/         # database.py, exceptions
├── deploy/           # nginx vhost and systemd unit
├── tests/            # Test suite (fixtures in tests/fixtures/z2/)
└── docs/             # Documentation
```

**Key Components:**
1. **API Layer**: FastAPI routes (landing page, annotations API) and schemas
2. **Discovery/Service Layer**: builds the live inventory and merges annotations; probes ports for HTTP
3. **Repository Layer**: annotation storage
4. **Models**: SQLAlchemy models

---

## Development Workflow

**Following:** WAY_OF_WORK.md (universal standards)

**Project-Specific Practices:**
- Use pytest for all testing
- Follow layered architecture pattern
- Repository pattern for data access
- Type hints everywhere
- Tests must never touch the real database: `tests/conftest.py` sets `DATABASE_URL` to a temporary file before the app is imported. Never point tests at `service_registry.db`.

---

## Current Status

**Development Phase:** Production, running on the Z2

**Implementation Status:**
- Landing page with live discovery and annotations replaces the earlier scan-based dashboard
- Old hand-approved rows from the `services` table are imported into annotations once on first start
- Deployment steps are in README.md

**Current Priorities:**
1. Maintain and monitor production deployment
2. Address any production issues or bugs
3. Consider future enhancements (see docs/PROGRESS.md)
4. Expand test coverage for edge cases (discovery tests use captured output in tests/fixtures/z2/)

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

1. **Investigation**: Debug issues , capture errors
2. **Fix**: Write tests, fix code
3. **Commit**: Git commit and push to origin
4. **Deploy**: `sudo systemctl restart service-registry` (the app runs on this machine; no SSH to another host)

### Important Notes

- ✅ **ALWAYS** write tests for bug fixes
- ✅ **ALWAYS** commit 
- ❌ **NEVER** make quick fixes 
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
**Port**: 8000 on 127.0.0.1 (nginx proxies from port 80; vhost in `deploy/nginx/service-registry.conf`)
**Unit file**: `deploy/systemd/service-registry.service`

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
