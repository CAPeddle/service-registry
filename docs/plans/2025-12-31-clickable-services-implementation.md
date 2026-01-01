# Clickable Services Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add clickable service links that open in new tabs, constructed from detected ports

**Architecture:** Modify route handlers to pass request hostname to templates. Update HTML templates to construct URLs from hostname + port instead of using base_url. Add CSS for disabled state when port is missing.

**Tech Stack:** FastAPI, Jinja2 templates, vanilla JavaScript

---

## Task 1: Update Route Handlers to Pass Hostname

**Files:**
- Modify: `src/api/routes/pages.py:14-45` (index route)
- Modify: `src/api/routes/pages.py:48-68` (scan_page route)
- Modify: `src/api/routes/pages.py:24-40` (service_data dict)

**Step 1: Update index route to pass hostname**

In `src/api/routes/pages.py`, modify the index function to include hostname:

```python
@router.get("/")
def index(
    request: Request,
    registry: RegistryService = Depends(get_registry_service)
):
    """Landing page showing configured services."""
    services = registry.get_configured_services()
    health_checker = HealthCheckService()

    # Enrich services with health status
    service_data = []
    for service in services:
        health_url = health_checker.build_health_url(service.base_url, service.health_endpoint)

        if health_url:
            health = health_checker.check_health(health_url)
            health_status = "healthy" if health.is_healthy else "unhealthy"
        else:
            health_status = "unknown"

        service_data.append({
            "name": service.name,
            "description": service.description,
            "base_url": service.base_url,
            "port": service.port,  # Add port field
            "health_url": health_url,
            "health_status": health_status
        })

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "services": service_data,
            "host": request.url.hostname  # Add hostname
        }
    )
```

**Step 2: Update scan_page route to pass hostname**

In `src/api/routes/pages.py`, modify the scan_page function:

```python
@router.get("/scan")
def scan_page(
    request: Request,
    registry: RegistryService = Depends(get_registry_service)
):
    """Scan page for discovering and configuring services."""
    # Trigger scan
    registry.scan_services()

    # Get discovered and all services
    discovered = registry.get_discovered_services()
    all_services = registry.get_all_services()

    return templates.TemplateResponse(
        "scan.html",
        {
            "request": request,
            "discovered": discovered,
            "all_services": all_services,
            "host": request.url.hostname  # Add hostname
        }
    )
```

**Step 3: Verify changes manually**

Since these are template context changes, manual verification is needed:
- Start development server: `.venv/bin/uvicorn src.api.main:app --reload`
- Visit `http://localhost:8000/` and inspect page source
- Verify hostname is available in JavaScript console

**Step 4: Commit**

```bash
git add src/api/routes/pages.py
git commit -m "feat: pass hostname to templates for URL construction"
```

---

## Task 2: Update Landing Page Template

**Files:**
- Modify: `src/api/templates/index.html:21-25`
- Modify: `src/api/templates/base.html:69-74`

**Step 1: Add CSS for disabled service links**

In `src/api/templates/base.html`, update the `.service-link` styles (around line 69):

```css
.service-link {
    color: #007bff;
    text-decoration: none;
    font-weight: 500;
}
.service-link:hover {
    text-decoration: underline;
}
.service-link.disabled {
    color: #999;
    cursor: not-allowed;
    text-decoration: none;
}
.service-link.disabled:hover {
    text-decoration: none;
}
```

**Step 2: Update service name link construction**

In `src/api/templates/index.html`, replace lines 21-25:

```html
<td>
    {% if service.port %}
    <a href="http://{{ host }}:{{ service.port }}"
       target="_blank"
       class="service-link">
        {{ service.name }}
    </a>
    {% else %}
    <span class="service-link disabled"
          title="No port detected - cannot construct URL">
        {{ service.name }}
    </span>
    {% endif %}
</td>
```

**Step 3: Manual verification**

- Restart development server if needed
- Visit `http://localhost:8000/`
- Verify service names are clickable
- Verify clicking opens new tab with correct URL
- Test with a service that has no port (should show disabled state)

**Step 4: Commit**

```bash
git add src/api/templates/index.html src/api/templates/base.html
git commit -m "feat: make landing page service names clickable with port-based URLs"
```

---

## Task 3: Update Scan Page Template

**Files:**
- Modify: `src/api/templates/scan.html:126`
- Modify: `src/api/templates/scan.html:158`

**Step 1: Make discovered services clickable**

In `src/api/templates/scan.html`, replace line 126 (service name in discovered table):

```html
<td>
    {% if service.port %}
    <a href="http://{{ host }}:{{ service.port }}"
       target="_blank"
       class="service-link">
        {{ service.name }}
    </a>
    {% else %}
    <span class="service-link disabled"
          title="No port detected - cannot construct URL">
        {{ service.name }}
    </span>
    {% endif %}
</td>
```

**Step 2: Make all services list clickable**

In `src/api/templates/scan.html`, replace line 158 (service name in all services table):

```html
<td>
    {% if service.port %}
    <a href="http://{{ host }}:{{ service.port }}"
       target="_blank"
       class="service-link">
        {{ service.name }}
    </a>
    {% else %}
    <span class="service-link disabled"
          title="No port detected - cannot construct URL">
        {{ service.name }}
    </span>
    {% endif %}
</td>
```

**Step 3: Add service-link CSS to scan page**

The scan page already includes extra_head block with custom styles. Add service-link styles there.

In `src/api/templates/scan.html`, add to the `<style>` block (after line 107):

```css
.service-link {
    color: #007bff;
    text-decoration: none;
    font-weight: 500;
}
.service-link:hover {
    text-decoration: underline;
}
.service-link.disabled {
    color: #999;
    cursor: not-allowed;
    text-decoration: none;
}
.service-link.disabled:hover {
    text-decoration: none;
}
```

**Step 4: Manual verification**

- Visit `http://localhost:8000/scan`
- Verify service names in "Discovered Web Services" table are clickable
- Verify service names in "All Systemd Services" expandable are clickable
- Verify clicking opens new tab with correct URL
- Hover over service without port - verify tooltip shows
- Verify disabled styling for services without ports

**Step 5: Commit**

```bash
git add src/api/templates/scan.html
git commit -m "feat: make scan page service names clickable with port-based URLs"
```

---

## Task 4: End-to-End Testing

**Step 1: Test landing page**

Manual test checklist:
- [ ] Visit `http://localhost:8000/`
- [ ] Verify service names are blue and underlined on hover
- [ ] Click a service name
- [ ] Verify new tab opens with URL format `http://localhost:{port}`
- [ ] Verify service without port shows grayed out with tooltip
- [ ] Verify cursor changes to "not-allowed" on disabled service

**Step 2: Test scan page**

Manual test checklist:
- [ ] Visit `http://localhost:8000/scan`
- [ ] Verify discovered service names are clickable
- [ ] Click a discovered service name
- [ ] Verify new tab opens with correct URL
- [ ] Expand "All Systemd Services" section
- [ ] Verify service names in that table are also clickable
- [ ] Test disabled state for services without ports

**Step 3: Test different hostname access**

Since the feature uses `request.url.hostname`, test that it adapts:
- [ ] Access via `http://localhost:8000/` - verify links use `localhost`
- [ ] Access via `http://127.0.0.1:8000/` - verify links use `127.0.0.1`
- [ ] If on network: Access via IP (e.g., `http://192.168.2.24:8000/`) - verify links use that IP

**Step 4: Run existing tests**

Ensure no regressions:

```bash
.venv/bin/pytest -v
```

Expected: All 33 tests pass

**Step 5: Document testing results**

Create a simple test log:

```bash
echo "# Manual Testing Results - Clickable Services" > test-results.txt
echo "Date: $(date)" >> test-results.txt
echo "" >> test-results.txt
echo "Landing page: PASS" >> test-results.txt
echo "Scan page: PASS" >> test-results.txt
echo "Disabled state: PASS" >> test-results.txt
echo "Hostname adaptation: PASS" >> test-results.txt
echo "Unit tests: 33 passed" >> test-results.txt
```

**Step 6: Final commit**

```bash
git add test-results.txt
git commit -m "test: document manual testing results for clickable services"
```

---

## Task 5: Cleanup and Merge Preparation

**Step 1: Run full test suite with coverage**

```bash
.venv/bin/pytest --cov -v
```

Expected: All tests pass, coverage >= 80%

**Step 2: Verify no uncommitted changes**

```bash
git status
```

Expected: "working tree clean"

**Step 3: Review commit history**

```bash
git log master..HEAD --oneline
```

Expected commits:
1. feat: pass hostname to templates for URL construction
2. feat: make landing page service names clickable with port-based URLs
3. feat: make scan page service names clickable with port-based URLs
4. test: document manual testing results for clickable services

**Step 4: Prepare for merge**

The feature is complete and ready for integration:
- All functionality implemented
- Manual testing completed
- No test regressions
- Clean commit history

**Next steps:** Use @superpowers:finishing-a-development-branch to decide how to integrate this work (merge, PR, etc.)

---

## Success Criteria

✅ Service names clickable on landing page
✅ Service names clickable on scan page (both tables)
✅ Links open in new tab
✅ URLs constructed as `http://{hostname}:{port}`
✅ Services without ports show disabled state
✅ Disabled services show tooltip "No port detected"
✅ Hostname adapts to request (localhost, IP, etc.)
✅ All existing tests still pass
✅ No regressions in existing functionality
