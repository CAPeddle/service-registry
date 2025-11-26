# Service Registry Design

**Date:** 2025-11-26
**Status:** Approved
**Purpose:** Personal home server service discovery and management dashboard

---

## Overview

A web-based service registry that discovers running services on an Ubuntu server via systemd, intelligently identifies web services, and provides a simple dashboard for quick access with health monitoring.

**Target User:** Personal use - single administrator managing home server infrastructure

---

## System Architecture

### Core Components

**1. Discovery Layer**
- Interfaces with systemd via `systemctl` commands
- Applies smart filtering to identify web services (ports 80, 443, 3000-9999)
- Flags web services as "discovered", others as "raw"

**2. Data Layer (SQLite)**
- Services table: id, name, description, port, health_endpoint, base_url, status, systemd_state, timestamps
- Health checks table: id, service_id, checked_at, is_healthy, response_code
- Status types: raw (systemd service), discovered (auto-detected web service), configured (user-registered)

**3. API + Frontend Layer**
- FastAPI serving REST endpoints and HTML templates
- Single landing page with simple table view
- Separate scan page for discovery and configuration

### Data Flow

1. **Landing Page Load**: Display configured services → perform health checks → render table
2. **Scan Trigger**: User clicks "Scan for Services" → query systemd → detect ports → categorize services → display on scan page
3. **Service Configuration**: User clicks "Configure" → web form → save to DB → mark as configured
4. **Health Monitoring**: On-demand when loading dashboard → HTTP GET to health endpoint → cache for 30-60s

---

## User Interface

### Landing Page (/)
**Purpose:** Quick access to configured services

**Layout:**
- Simple HTML table
- Columns: Service Name | Status | Description | Actions
- Status indicators: ● green (healthy), ● red (unhealthy), ● gray (no health check)
- Service name is clickable link to service URL
- "Scan for Services" button in header (top-right)

**Behavior:**
- Shows only services with status="configured"
- Real-time health checks on page load (cached 30-60s)
- Click service name → navigate to service
- Click "Visit" → open service in new tab
- Click "Health" → trigger immediate health check

### Scan Page (/scan)
**Purpose:** Discover and configure services

**Layout:**
- Section 1: "New Discovered Services" - Web services not yet configured
  - Table with: Name | Port | Systemd State | Action (Configure button)
- Section 2: "All Systemd Services" - Collapsible/accordion view
  - Full list of systemd services with "Add to Registry" buttons

**Behavior:**
- Click "Configure" or "Add to Registry" → open configuration form
- Form pre-fills: service name, detected port
- User fills: description, health endpoint (optional), base URL
- Submit → save to DB as "configured" → refresh page
- "Back to Dashboard" button returns to landing page

### Configuration Form
**Fields:**
- Service Name (pre-filled, read-only)
- Description (text input, required)
- Base URL (text input, auto-populated if port detected, required)
- Health Endpoint (text input, optional, e.g., "/health")
- Port (number input, auto-populated if detected)

---

## Systemd Integration

### Service Discovery

**Command:** `systemctl list-units --type=service --all --no-pager`
- Returns list of all systemd services with states
- Parse output to extract service names and current state (active/inactive/failed)

**Metadata Extraction:** `systemctl show <service>`
- Get additional service details (PID, MainPID, etc.)

### Port Detection (Smart Web Service Filtering)

**Method:** Use `ss -tlnp` or `netstat -tlnp`
- Map process IDs to listening ports
- Match systemd service PIDs to ports
- Flag services on ports: 80, 443, 3000-3999, 4000-4999, 5000-5999, 8000-8999

**Service Categorization:**
- **raw**: In systemd, not listening on web ports
- **discovered**: Auto-detected web service (not configured)
- **configured**: User has added details, shows on main dashboard

---

## API Endpoints

```
GET  /                          # Landing page (configured services table)
GET  /scan                      # Scan page (discovered + all services)
POST /api/scan                  # Trigger systemd scan, return discovered services
GET  /api/services              # List all configured services with health status
POST /api/services              # Create/configure a service
PUT  /api/services/{id}         # Update service details
DELETE /api/services/{id}       # Remove service from registry
GET  /api/services/{id}/health  # Check health of specific service
```

---

## Database Schema

### services Table

```python
class Service(Base):
    __tablename__ = 'services'

    id: int                          # Primary key
    name: str                        # Unique, indexed (systemd service name)
    description: str | None          # User-provided description
    port: int | None                 # Listening port
    health_endpoint: str | None      # e.g., "/health", "/api/status"
    base_url: str | None             # e.g., "http://192.168.2.24:8080"
    status: str                      # enum: raw/discovered/configured
    systemd_state: str               # active/inactive/failed
    last_scanned_at: datetime | None # Last systemd scan timestamp
    created_at: datetime
    updated_at: datetime
```

### health_checks Table (Optional - for history)

```python
class HealthCheck(Base):
    __tablename__ = 'health_checks'

    id: int                    # Primary key
    service_id: int            # Foreign key to services.id
    checked_at: datetime
    is_healthy: bool
    response_code: int | None
```

---

## Health Checking

### Mechanism

**Trigger:** On-demand when loading dashboard
**Process:**
1. Construct full URL: `{base_url}{health_endpoint}`
2. HTTP GET request with 2-second timeout
3. Check response code == 200
4. Return status: healthy (green), unhealthy (red), unknown (gray)

**Caching:** Cache health status for 30-60 seconds to prevent excessive requests on page refresh

**Status Display:**
- ● Green: HTTP 200 received
- ● Red: Timeout, connection refused, or non-200 response
- ● Gray: No health endpoint configured

### Error Handling

**Systemd Scan Failures:**
- Show error banner on scan page
- Log error details
- Provide retry button

**Port Detection Failures:**
- Still show service
- Mark port as "unknown"
- Allow manual configuration

**Health Check Failures:**
- Treat as "unhealthy" (red indicator)
- Log timeout/connection errors
- Don't block page rendering

**Database Errors:**
- Log to application logs
- Show generic error message to user
- Graceful degradation where possible

**Validation:**
- base_url: Valid URL format
- port: Integer 1-65535
- health_endpoint: Starts with "/" if provided

---

## Edge Cases

1. **Service removed from systemd but still in DB:**
   - On next scan, mark as "not found" or set systemd_state to "removed"
   - Option to clean up stale services

2. **Duplicate service names:**
   - Use systemd service name as unique constraint
   - Prevent duplicates at database level

3. **Services without ports:**
   - Allow manual configuration
   - Won't auto-detect as web service
   - Can still be configured and monitored

4. **Services on non-standard ports:**
   - Auto-detect if in range (3000-9999)
   - Otherwise require manual addition via scan page

---

## Implementation Notes

**Technology Stack:**
- FastAPI for API and HTML templating
- SQLAlchemy with SQLite for persistence
- Jinja2 templates for HTML rendering
- subprocess for systemd commands
- httpx or requests for health checks

**Security Considerations:**
- Service registry runs on localhost or private network
- No authentication required (personal use)
- Input validation on all user-provided data
- Command injection prevention (parameterized systemctl calls)

**Future Enhancements (YAGNI - not implementing initially):**
- Periodic background health checks
- Service restart capability
- Health check history graphs
- Service grouping/tagging
- Email/notification on service failures
- Multi-server support
