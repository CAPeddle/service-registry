# Clickable Services Design

**Date:** 2025-12-31
**Status:** Approved
**Feature:** Click-through to open services in new tabs

## Overview

Add clickable links to service names on both the landing page and scan page, allowing users to open services in new browser tabs. Links are constructed from the detected port and the registry's current hostname.

## Requirements

- Service names become clickable on both landing and scan pages
- Clicking opens service in new tab
- URL constructed as `http://{registry-host}:{service-port}`
- Services without ports show visual warning but remain clickable with tooltip
- Minimal backend changes - leverage existing port data

## URL Construction Strategy

### Core Approach
Construct service URLs dynamically from detected ports using the registry's current hostname. The hostname is determined from the incoming request, allowing the feature to work whether accessed via IP address, localhost, or custom hostname.

### Implementation
- Frontend receives registry's current hostname via template context
- JavaScript constructs URLs as `http://{registry-host}:{service-port}`
- Services without ports get disabled/warning state with tooltip

### Benefits
- Auto-adapts to different access methods (IP, hostname, localhost)
- No hardcoded IPs in configuration
- Simple client-side logic
- Uses existing port detection data

## Frontend Implementation

### Landing Page (`/`)

**Service Cards:**
- Service name becomes clickable link
- Link styled with blue color, underline on hover
- Cursor changes to pointer
- Opens in new tab (`target="_blank"`)

**No Port Handling:**
- Name grayed out with disabled styling
- Tooltip shows "No port detected"
- Link still present but visually indicates limitation

### Scan Page (`/scan`)

**Discovered Services Table:**
- Identical treatment to landing page
- Service names in scan results become clickable links
- Same styling and tooltip behavior

### HTML/JavaScript Structure

**Link Construction:**
```javascript
// In template or inline script
const currentHost = '{{ host }}';  // From Jinja2 context

function buildServiceUrl(port) {
  if (!port) return null;
  return `http://${currentHost}:${port}`;
}
```

**HTML Pattern:**
```html
{% if service.port %}
  <a href="http://{{ host }}:{{ service.port }}"
     target="_blank"
     class="service-link">
    {{ service.name }}
  </a>
{% else %}
  <span class="service-link disabled"
        title="No port detected">
    {{ service.name }}
  </span>
{% endif %}
```

### CSS Styling

```css
.service-link {
  color: #0066cc;
  text-decoration: none;
  cursor: pointer;
}

.service-link:hover {
  text-decoration: underline;
}

.service-link.disabled {
  color: #999;
  cursor: not-allowed;
}
```

## Backend Changes

### Minimal API Impact

No new endpoints required. Existing data already contains necessary information:
- `GET /api/services` - returns services with port field
- `POST /api/scan` - returns discovered services with ports

### Template Context Enhancement

Update route handlers to pass hostname to templates:

```python
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    # Existing service fetch logic
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "services": services,
            "host": request.url.hostname
        }
    )

@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    return templates.TemplateResponse(
        "scan.html",
        {
            "request": request,
            "host": request.url.hostname
        }
    )
```

### Data Model Verification

Confirm existing fields:
- `Service.port` - integer field, nullable
- Scan result DTOs include port information
- Both already present in API responses

**No database schema changes required** - using existing data in new way.

## User Experience Flow

### Happy Path
1. User views landing page or scan page
2. Sees service name as blue, underlined link
3. Hovers - cursor changes to pointer
4. Clicks service name
5. New tab opens with `http://192.168.2.24:{port}`
6. Service loads in new tab

### No Port Edge Case
1. User views service without detected port
2. Service name appears grayed out
3. Hovers - sees "No port detected" tooltip
4. Visual indication that clickthrough may not work
5. Can still click if they want to try

## Technical Considerations

### Security
- All links use `http://` - assumes local network usage
- `target="_blank"` opens new tab (no `rel="noopener"` needed for same-origin)
- No user input in URL construction - port from database

### Compatibility
- Works with any hostname/IP used to access registry
- No hardcoded network addresses
- Adapts to development vs production environments

### Future Enhancements
Could later add:
- HTTPS support detection
- Custom URL overrides per service
- Health check before opening
- Visual indicator if service is down

## Implementation Steps

1. Update template route handlers to pass `host` context
2. Modify `landing.html` - add link logic to service cards
3. Modify `scan.html` - add link logic to discovered services
4. Add CSS styling for `.service-link` states
5. Test with services that have ports
6. Test with services that lack ports
7. Verify new tab behavior
8. Test with different hostname access methods

## Success Criteria

- Service names clickable on both pages
- New tab opens correctly
- URL format is `http://{host}:{port}`
- Services without ports show disabled state
- Tooltip provides feedback for missing ports
- No breaking changes to existing functionality
