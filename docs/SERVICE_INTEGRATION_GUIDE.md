# Service Integration Guide

**For AI Coding Assistants (Claude, Copilot, etc.)**
**Version:** 1.0.0
**Last Updated:** 2025-11-27

---

## Overview

This guide provides instructions for integrating services with the Service Registry. Use this when creating new services or modifying existing ones that need to be tracked and monitored.

The Service Registry provides:
- **Automatic discovery** of systemd services
- **Health monitoring** for HTTP/HTTPS endpoints
- **Status tracking** (active/inactive/failed)
- **Centralized dashboard** for all registered services

---

## Integration Methods

### Method 1: Systemd Service (Recommended)

**When to use:** For production services that should run continuously and start on boot.

**Advantages:**
- ✅ Automatic discovery via systemd scan
- ✅ Automatic restart on failure
- ✅ System-level management
- ✅ No manual API calls needed

**How it works:**
1. Service Registry scans systemd services via `/api/scan`
2. Discovers services ending in `.service`
3. Extracts service name, state, and description
4. Detects listening ports (if applicable)
5. Stores in database for monitoring

**Configuration Requirements:**

```ini
[Unit]
Description=Your Service Name  # This becomes the display name
After=network.target

[Service]
Type=simple
User=serviceuser
WorkingDirectory=/path/to/service
Environment="PATH=/path/to/service/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/path/to/service/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Critical Configuration Notes:**

1. **PATH Environment Variable:**
   - MUST include system binaries: `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
   - MUST include your virtualenv bin directory first
   - Service Registry needs to execute `systemctl` and `ss` commands

2. **Service Naming:**
   - Use descriptive names ending in `.service`
   - Example: `myapp-api.service`, `data-processor.service`
   - The filename becomes the service identifier

3. **Description Field:**
   - Use meaningful descriptions in the `[Unit]` section
   - This appears in the Service Registry dashboard

**Installation Steps:**

```bash
# 1. Create service file
sudo nano /etc/systemd/system/myapp.service

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable service (start on boot)
sudo systemctl enable myapp.service

# 4. Start service
sudo systemctl start myapp.service

# 5. Verify status
sudo systemctl status myapp.service

# 6. Trigger discovery in Service Registry
curl -X POST http://localhost:8000/api/scan
# Or visit http://your-registry-ip/scan in browser
```

---

### Method 2: Manual API Registration

**When to use:**
- Non-systemd services
- External services on other servers
- Services that need custom configuration
- Quick testing and development

**Advantages:**
- ✅ Works for any HTTP/HTTPS service
- ✅ Can register remote services
- ✅ Flexible configuration
- ✅ No systemd required

**API Endpoint:**

```http
POST /api/services
Content-Type: application/json

{
  "name": "My Service",
  "url": "http://localhost:3000",
  "status": "active",
  "port": 3000
}
```

**Field Requirements:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | Yes | Display name (1-100 chars) |
| url | string | Yes | Valid HTTP/HTTPS URL |
| status | string | No | "active", "inactive", or "failed" (default: "active") |
| port | integer | No | Port number (1-65535) |

**Example using curl:**

```bash
curl -X POST http://localhost:8000/api/services \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My API",
    "url": "http://192.168.1.100:8080",
    "status": "active",
    "port": 8080
  }'
```

**Example using Python:**

```python
import requests

response = requests.post(
    "http://localhost:8000/api/services",
    json={
        "name": "My API",
        "url": "http://192.168.1.100:8080",
        "status": "active",
        "port": 8080
    }
)

if response.status_code == 200:
    service = response.json()
    print(f"Registered service with ID: {service['id']}")
```

---

## Health Check Configuration

**Purpose:** Enable automatic health monitoring for your service.

### Requirements:

1. **HTTP/HTTPS Endpoint:**
   - Service must expose an HTTP or HTTPS URL
   - URL must be accessible from the Service Registry server

2. **Health Check Response:**
   - Any 2xx status code = healthy
   - Any other status or timeout = unhealthy
   - Timeout: 2.0 seconds

3. **Caching:**
   - Health checks are cached for 60 seconds
   - Reduces load on monitored services
   - Balance between freshness and performance

### Recommended Health Endpoint:

**For FastAPI services:**

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**For Flask services:**

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"})
```

**For Express.js services:**

```javascript
app.get('/health', (req, res) => {
  res.json({ status: 'healthy' });
});
```

### Advanced Health Checks:

For production services, include dependency checks:

```python
@app.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "external_api": await check_external_api()
    }

    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "checks": checks
        }
    )
```

---

## Port Detection

**Automatic Detection:**

The Service Registry automatically detects listening ports for systemd services:

- **Port Range:** 80, 443, 3000-9999
- **Detection Method:** Uses `ss -tlnp` command
- **Requirements:** Service must be listening on a TCP port

**How it works:**

1. Service Registry runs systemd scan
2. Gets PID for each active service via `systemctl show`
3. Uses `ss -tlnp` to find ports bound to that PID
4. Filters for web service ports (80, 443, 3000-9999)
5. Stores first detected port in database

**Limitations:**

- Only detects TCP listening ports
- Only checks specific port ranges
- Takes first port if multiple are detected
- Requires service to be running (`active` state)

**Manual Port Configuration:**

If automatic detection doesn't work or you need a specific port:

```bash
# Update service via API
curl -X PUT http://localhost:8000/api/services/{id} \
  -H "Content-Type: application/json" \
  -d '{
    "port": 8080
  }'
```

---

## Common Integration Patterns

### Pattern 1: FastAPI Service with Systemd

**Use case:** Production Python API service

**Files to create:**

1. **Service code:** `src/api/main.py`
```python
from fastapi import FastAPI

app = FastAPI(title="My Service")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {"message": "Service running"}
```

2. **Systemd service:** `/etc/systemd/system/myapp-api.service`
```ini
[Unit]
Description=My Application API
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/myapp
Environment="PATH=/opt/myapp/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/myapp/.venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. **Deployment commands:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable myapp-api.service
sudo systemctl start myapp-api.service

# Register with Service Registry
curl -X POST http://registry-server:8000/api/scan
```

---

### Pattern 2: Node.js Service with PM2

**Use case:** Node.js service managed by PM2 (not systemd)

**Configuration:**

1. **PM2 ecosystem file:** `ecosystem.config.js`
```javascript
module.exports = {
  apps: [{
    name: 'myapp',
    script: './server.js',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
  }]
};
```

2. **Manual registration:**
```bash
# Start service with PM2
pm2 start ecosystem.config.js

# Register with Service Registry via API
curl -X POST http://registry-server:8000/api/services \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Node App",
    "url": "http://localhost:3000",
    "status": "active",
    "port": 3000
  }'
```

---

### Pattern 3: Docker Container Service

**Use case:** Containerized service with systemd wrapper

**Files to create:**

1. **Systemd service:** `/etc/systemd/system/myapp-container.service`
```ini
[Unit]
Description=My App Docker Container
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/usr/bin/docker run --rm --name myapp -p 8080:8080 myapp:latest
ExecStop=/usr/bin/docker stop myapp
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. **Registration:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable myapp-container.service
sudo systemctl start myapp-container.service

# Trigger systemd scan
curl -X POST http://registry-server:8000/api/scan
```

---

### Pattern 4: Remote Service Registration

**Use case:** Service running on different server

**Registration:**

```python
# run_on_service_startup.py
import requests
import os

REGISTRY_URL = os.getenv("SERVICE_REGISTRY_URL", "http://registry-server:8000")
SERVICE_NAME = "Remote Data Processor"
SERVICE_URL = "http://data-server:5000"
SERVICE_PORT = 5000

def register_with_registry():
    """Register this service with the central registry on startup."""
    try:
        response = requests.post(
            f"{REGISTRY_URL}/api/services",
            json={
                "name": SERVICE_NAME,
                "url": SERVICE_URL,
                "status": "active",
                "port": SERVICE_PORT
            },
            timeout=5.0
        )
        response.raise_for_status()
        print(f"✅ Registered with Service Registry: {response.json()}")
    except Exception as e:
        print(f"⚠️  Failed to register with Service Registry: {e}")
        # Continue running even if registration fails

# Call during application startup
if __name__ == "__main__":
    register_with_registry()
    # ... start your application
```

---

## Service Registry API Reference

### List All Services

```http
GET /api/services
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "service-registry.service",
    "url": "http://127.0.0.1:8000",
    "status": "active",
    "port": 8000,
    "last_health_check": "2025-11-27T10:30:00",
    "health_status": "healthy"
  }
]
```

### Get Single Service

```http
GET /api/services/{id}
```

### Create Service

```http
POST /api/services
Content-Type: application/json

{
  "name": "My Service",
  "url": "http://localhost:3000",
  "status": "active",
  "port": 3000
}
```

### Update Service

```http
PUT /api/services/{id}
Content-Type: application/json

{
  "name": "Updated Name",
  "url": "http://localhost:3001",
  "status": "active",
  "port": 3001
}
```

### Delete Service

```http
DELETE /api/services/{id}
```

### Trigger Systemd Scan

```http
POST /api/scan
```

**Response:**
```json
{
  "discovered": 5,
  "updated": 3,
  "services": [...]
}
```

---

## Best Practices

### DO:

✅ **Use systemd for production services**
- Automatic discovery
- System-level management
- Consistent deployment

✅ **Include health check endpoints**
- Simple `/health` endpoint
- Return 200 OK for healthy state
- Include dependency checks for production

✅ **Use descriptive service names**
- Clear, meaningful names
- Include service purpose
- Example: `myapp-api.service`, `data-worker.service`

✅ **Set proper PATH in systemd**
- Include virtual environment bin directory
- Include all system binary paths
- Critical for Service Registry discovery

✅ **Enable auto-restart**
- `Restart=always` in systemd
- `RestartSec=10` to prevent restart loops
- Ensures service availability

✅ **Test service before registering**
- Verify service starts correctly
- Check health endpoint responds
- Confirm port is listening

### DON'T:

❌ **Don't skip PATH configuration**
- Service Registry needs `systemctl` and `ss` commands
- Missing PATH causes discovery failures

❌ **Don't use generic service names**
- Avoid names like `app.service`, `service.service`
- Use descriptive, unique names

❌ **Don't skip health endpoints**
- Health monitoring requires HTTP/HTTPS URL
- Without it, you only get systemd state

❌ **Don't hardcode registry URL in service code**
- Use environment variables
- Makes services portable across environments

❌ **Don't register services that aren't running**
- Verify service is active first
- Check with `systemctl status`

❌ **Don't edit services on production servers**
- Follow the WAY_OF_WORK.md workflow
- Investigate remotely, fix locally, commit, deploy

---

## Troubleshooting

### Service not discovered after scan

**Possible causes:**

1. **Service name doesn't end in `.service`**
   - Fix: Rename service file to include `.service` extension

2. **Service is not active**
   - Check: `systemctl status myapp.service`
   - Fix: `systemctl start myapp.service`

3. **PATH missing in systemd service**
   - Fix: Add complete PATH environment variable
   ```ini
   Environment="PATH=/path/to/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
   ```

4. **Service Registry not running as root/sudo**
   - Some systemctl commands require elevated permissions
   - Check Service Registry's own systemd configuration

### Port not detected

**Possible causes:**

1. **Port outside detection range**
   - Service Registry only checks: 80, 443, 3000-9999
   - Fix: Manually set port via API

2. **Service not listening on TCP**
   - Only TCP ports are detected
   - Fix: Ensure service binds to TCP socket

3. **Service bound to specific interface**
   - `ss` might not detect interface-specific bindings
   - Fix: Manually set port via API

### Health check shows unhealthy

**Possible causes:**

1. **URL not accessible**
   - Check firewall rules
   - Verify service is listening on correct interface
   - Test with: `curl http://service-url`

2. **Response timeout**
   - Health checks timeout after 2.0 seconds
   - Check service performance
   - Check network latency

3. **Non-2xx status code**
   - Health endpoint must return 200-299 status
   - Fix: Update endpoint to return 200 OK

### Manual registration fails with validation error

**Possible causes:**

1. **Invalid URL format**
   - Must include protocol: `http://` or `https://`
   - Must be valid URL format

2. **Port out of range**
   - Must be 1-65535
   - Must be integer

3. **Name too long**
   - Maximum 100 characters
   - Must be non-empty

---

## Examples for Common Scenarios

### Scenario 1: New Python FastAPI Microservice

**Task:** Create and register a new FastAPI microservice for processing data.

**Steps:**

1. Create FastAPI application with health endpoint
2. Create systemd service file with proper PATH
3. Install and start systemd service
4. Trigger Service Registry scan
5. Verify in dashboard

**Code example:** See Pattern 1 above.

---

### Scenario 2: Register Third-Party Service

**Task:** Register a third-party service (e.g., PostgreSQL admin panel) running on port 5050.

**Steps:**

```bash
curl -X POST http://registry-server:8000/api/services \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PostgreSQL Admin (pgAdmin)",
    "url": "http://192.168.1.50:5050",
    "status": "active",
    "port": 5050
  }'
```

---

### Scenario 3: Migrate Existing Service to Registry

**Task:** You have an existing systemd service that needs to be tracked.

**Steps:**

1. Verify service has proper PATH in systemd config
2. Ensure service has health endpoint (or add one)
3. Restart service: `sudo systemctl restart myservice.service`
4. Trigger scan: `curl -X POST http://registry-server:8000/api/scan`
5. Verify in dashboard

**If service lacks health endpoint:**

Add simple endpoint to your application, then:

```bash
# Update service in registry with correct URL
curl -X PUT http://registry-server:8000/api/services/123 \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://localhost:8080/health"
  }'
```

---

## Testing Your Integration

### Checklist:

- [ ] Service starts successfully
- [ ] Service appears in systemd list: `systemctl list-units --type=service`
- [ ] Service has proper PATH in systemd config
- [ ] Health endpoint responds with 200 OK
- [ ] Port is listening: `ss -tlnp | grep <port>`
- [ ] Service Registry scan discovers service
- [ ] Service appears in dashboard at `http://registry-server/`
- [ ] Health status updates correctly
- [ ] Service restarts after system reboot (if enabled)

### Manual Testing Commands:

```bash
# 1. Check service status
systemctl status myapp.service

# 2. Check listening ports
ss -tlnp | grep myapp

# 3. Test health endpoint
curl http://localhost:8000/health

# 4. Trigger registry scan
curl -X POST http://registry-server:8000/api/scan

# 5. List registered services
curl http://registry-server:8000/api/services

# 6. View dashboard
# Open http://registry-server/ in browser
```

---

## Summary for AI Assistants

**When creating a new service:**

1. **Default to systemd integration** for production services
2. **Always include PATH** with full system binaries in systemd config
3. **Always add health endpoint** at `/health` returning 200 OK
4. **Use descriptive service names** ending in `.service`
5. **Test before registering** - verify service runs and responds
6. **Trigger scan after deployment** via `/api/scan` endpoint

**When modifying existing service:**

1. **Investigate remotely** if deployed on production server
2. **Fix locally** in development environment
3. **Write/update tests** for the changes
4. **Commit to version control**
5. **Deploy via git pull** on remote server
6. **Restart service** with `systemctl restart`
7. **Verify in Service Registry** dashboard

**Key files to reference:**

- Service Registry API: `/home/cpeddle/projects/personal/service_registry/src/api/routes/services.py`
- Systemd Discovery: `/home/cpeddle/projects/personal/service_registry/src/services/systemd_discovery.py`
- Port Detection: `/home/cpeddle/projects/personal/service_registry/src/services/port_detection.py`
- Health Checks: `/home/cpeddle/projects/personal/service_registry/src/services/health_check.py`

**Remember:** The Service Registry is designed to make service discovery automatic. Prefer systemd integration over manual API registration whenever possible.
