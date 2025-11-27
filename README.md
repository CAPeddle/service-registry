# Service Registry

A web-based service registry for Ubuntu systemd services with automatic discovery, health monitoring, and a clean web interface.

## Features

- **Automatic Service Discovery**: Scans systemd for running services
- **Port Detection**: Identifies web services by listening ports
- **Health Monitoring**: HTTP health checks with caching
- **Web UI**: Clean dashboard and service configuration interface
- **REST API**: Full CRUD API for service management
- **Database**: SQLite with automatic schema initialization

## Screenshots

### Landing Page
Dashboard showing all configured services with health status indicators.

### Scan Page
Discover systemd services, view listening ports, and configure services via modal dialog.

## Requirements

- **Python**: 3.11 or higher
- **OS**: Ubuntu/Debian (requires systemd)
- **Permissions**: Root/sudo access (for systemctl and ss commands)
- **Optional**: Nginx (for production deployment on port 80)

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/CAPeddle/service-registry.git
cd service-registry

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run development server (requires sudo for systemd access)
sudo venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 5. Visit http://192.168.2.24:8000
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Available settings:

```env
# Application Settings
APP_NAME="Service Registry"
VERSION="0.1.0"
DEBUG=false

# Server Settings
HOST=0.0.0.0
PORT=8000

# Database Settings
DATABASE_URL=sqlite:///./service_registry.db

# API Settings
API_PREFIX=/api/v1

# Health Check Settings
HEALTH_CHECK_TIMEOUT=2.0
HEALTH_CHECK_CACHE_TTL=60
```

## Production Deployment

### Option 1: Direct on Port 80 (Simple)

Run directly on port 80 to access without specifying a port:

```bash
sudo venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 80
```

Access at: `http://192.168.2.24`

### Option 2: Nginx Reverse Proxy (Recommended)

This is the recommended production setup as it allows:
- Running the service as non-root on port 8000
- Nginx handles port 80
- Easy SSL/HTTPS setup later
- Better performance and security

#### Step 1: Install Nginx

```bash
sudo apt update
sudo apt install nginx
```

#### Step 2: Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/service-registry
```

Paste the following configuration:

```nginx
server {
    listen 80;
    server_name 192.168.2.24;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Step 3: Enable the Site

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/service-registry /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

#### Step 4: Create Systemd Service

Create `/etc/systemd/system/service-registry.service`:

```bash
sudo nano /etc/systemd/system/service-registry.service
```

Paste:

```ini
[Unit]
Description=Service Registry API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/cpeddle/projects/personal/service_registry
Environment="PATH=/home/cpeddle/projects/personal/service_registry/venv/bin"
ExecStart=/home/cpeddle/projects/personal/service_registry/venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Note**: Adjust the `WorkingDirectory` and paths to match your installation location.

#### Step 5: Start the Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable service-registry

# Start the service
sudo systemctl start service-registry

# Check status
sudo systemctl status service-registry
```

#### Step 6: Access the Application

Visit `http://192.168.2.24` (no port needed!)

## Usage

### Web Interface

1. **Dashboard** (`/`): View all configured services with health status
2. **Scan Page** (`/scan`): Click "Scan for Services" button
   - Discovers all systemd services
   - Shows web services (detected by listening ports)
   - Configure services by clicking "Configure" button

### API Endpoints

#### Service Management

```bash
# List all services
GET /api/services

# Get service by ID
GET /api/services/{id}

# Create new service
POST /api/services
{
  "name": "myapp.service",
  "description": "My Application",
  "base_url": "http://192.168.2.24:8080",
  "port": 8080,
  "health_endpoint": "/health"
}

# Update service
PUT /api/services/{id}
{
  "description": "Updated description"
}

# Delete service
DELETE /api/services/{id}
```

#### Scan Services

```bash
# Trigger systemd scan
POST /api/scan
```

Returns:
```json
{
  "message": "Scan completed successfully",
  "stats": {
    "total_scanned": 150,
    "new_discovered": 3,
    "updated": 5,
    "new_raw": 142
  }
}
```

### Interactive API Documentation

- **Swagger UI**: `http://192.168.2.24/docs`
- **ReDoc**: `http://192.168.2.24/redoc`

## Development

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test types
pytest tests/unit/
pytest tests/integration/

# Watch mode (requires pytest-watch)
ptw
```

### Project Structure

```
service_registry/
├── src/
│   ├── api/                    # API layer
│   │   ├── routes/            # API endpoints
│   │   ├── schemas/           # Pydantic models
│   │   ├── dependencies/      # Dependency injection
│   │   └── templates/         # HTML templates
│   ├── core/                   # Core utilities
│   ├── models/                 # Database models
│   ├── services/              # Business logic
│   │   ├── systemd_discovery.py
│   │   ├── port_detection.py
│   │   ├── registry_service.py
│   │   └── health_check.py
│   └── config/                # Configuration
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── docs/                      # Documentation
└── requirements.txt           # Python dependencies
```

### Architecture

The project follows a layered architecture:

1. **API Layer** (`src/api/`): FastAPI routes and request/response handling
2. **Service Layer** (`src/services/`): Business logic
3. **Model Layer** (`src/models/`): SQLAlchemy database models
4. **Core Layer** (`src/core/`): Shared utilities

### Adding New Features

1. Write tests first (TDD approach)
2. Implement service layer logic
3. Add API endpoints
4. Update documentation

### Integrating Services with Registry

**For developers creating new services or modifying existing ones:**

See the comprehensive [Service Integration Guide](docs/SERVICE_INTEGRATION_GUIDE.md) for:
- Systemd service configuration (recommended)
- Manual API registration
- Health check setup
- Port detection requirements
- Common integration patterns
- Troubleshooting tips

This guide is optimized for AI coding assistants (Claude, Copilot) but useful for all developers.

## Troubleshooting

### Permission Denied Errors

The service requires root/sudo access for:
- `systemctl` commands (systemd service discovery)
- `ss -tlnp` command (port detection)

**Solution**: Always run with `sudo`

### Database Not Found

The database is automatically created on first startup. If you encounter issues:

```bash
# Remove old database
rm service_registry.db

# Restart the application (database will be recreated)
sudo systemctl restart service-registry
```

### Nginx 502 Bad Gateway

If Nginx shows a 502 error:

```bash
# Check if service is running
sudo systemctl status service-registry

# Check service logs
sudo journalctl -u service-registry -f

# Restart service
sudo systemctl restart service-registry
```

### Port Already in Use

If port 8000 (or 80) is already in use:

```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the process or change PORT in .env
```

## Contributing

This project follows:
- **SOLID principles**
- **Test-driven development**
- **Layered architecture**
- **Repository pattern**

## License

MIT License - See LICENSE file for details

## Author

Built with Claude Code

---

**Need help?** Open an issue at https://github.com/CAPeddle/service-registry/issues
