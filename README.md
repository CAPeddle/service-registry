# Service Registry

A landing page for the Z2 home server. It lists every service listening on a
TCP port, shows how each one can be reached (LAN, tailnet, or only from the
machine itself), and links to the ones that answer HTTP. Nothing has to be
registered: the list is discovered live on each page load.

The app runs on the Z2 itself (LAN IP 192.168.2.48, hostname `z2`). nginx
serves it on port 80.

## How discovery works

Each page load (cached for about 10 seconds; the Refresh link bypasses the
cache) combines these sources:

| Source | Used for |
|--------|----------|
| `ss -tlnpH` | listening sockets and the PIDs that own them |
| `/proc/<pid>/cgroup` | mapping a PID to a system or user systemd unit |
| `docker ps` | published ports and compose project/service labels |
| `tailscale serve status --json` | tailnet front-ends for local ports |
| `ufw status verbose` | which ports the firewall admits from the LAN |
| `systemctl show` | unit descriptions and state (user units via `systemctl --user -M <user>@`) |

The app runs as root (see `deploy/systemd/service-registry.service`) so it can
see every socket's process, read the ufw rules and query user units.

If a source fails, the affected rows show "reachability unknown" and a banner
at the top of the page names the source.

## The landing page

Each row shows how the service can be reached:

- a LAN link, built from the address the visitor used to open the page
- "blocked by firewall": listening on the LAN but not admitted by ufw
- "tailnet only": reachable over Tailscale (MagicDNS links). Services bound to
  all addresses always get this, because tailscaled admits tailnet traffic
  ahead of ufw.
- "internal only": bound to loopback, no link
- "reachability unknown": a source failed

A link is shown only when the port answers HTTP (probed on 127.0.0.1,
concurrently, within about 1.5 seconds) or when you set a link override.

Rows are grouped as Unknown, Web (LAN), Tailnet, Internal and Not running.
Noise (ssh, DNS, tailscaled internals, nginx, the registry itself,
unattributed processes) is hidden by default. "Show hidden" (or
`/?show_hidden=1`) adds a Hidden group.

Each row has Edit and Hide buttons. Edits are stored as annotations.

### Annotations

Annotations live in the SQLite table `annotations`, keyed by an identity:

- `system:<unit>`
- `user:<uid>:<unit>`
- `docker:<project>/<service>`
- `manual:<name>`
- `process:<name>`

An annotation can set a display name, description, hidden flag (unset means the
default), link override, health path and primary port. On first start, the
hand-approved rows of the old `services` table are imported once.

### Page edits win over registrations

A description or health path set with Edit is not overwritten when the
service registers again through `POST /api/services`. If the registration
carries a different value, it is held in the `registration_attempts` table and
shown at the top of the page under "Registrations held for review", with the
values it sent next to the current ones. "Use these values" applies the sent
values (and the field stops being protected); "Dismiss" discards them. Only
the latest held registration per service is kept. Clearing a field with Edit
removes its protection.

## API

Interactive docs are at `/docs` and `/redoc`. `GET /api/v1/health` is the
registry's own health check.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/services` | list annotations |
| POST | `/api/services` | register a service (below) |
| PUT | `/api/services/annotation` | create or update an annotation; JSON body with `identity_key` and any of `display_name`, `description`, `hidden`, `link_override`, `health_path`, `primary_port`. An empty string clears a text field. |
| DELETE | `/api/services/annotation?identity_key=...` | remove an annotation |
| POST | `/api/services/registrations/{id}/apply` | use a held registration's values |
| DELETE | `/api/services/registrations/{id}` | dismiss a held registration |

`POST /api/services` takes `{name, description, base_url, port?, health_endpoint?}`.
`base_url` must start with http:// or https://, and `health_endpoint` must start
with `/`. If `name` matches a discovered unit, container or compose service,
only the description and health path are stored. Otherwise a `manual:<name>`
row is created and `base_url` becomes its link.

Page edits win: a description or health path set on the page (with `PUT`) is
kept, and a registration that sends a different value for it is held for
review on the landing page. The response is still `201` with the annotation.

Write requests (POST, PUT, PATCH, DELETE) are answered with `403` unless they
come through one of the server's own addresses; see [Security](#security).

See [docs/SERVICE_INTEGRATION_GUIDE.md](docs/SERVICE_INTEGRATION_GUIDE.md).

## Security

There is no login: anyone who can reach port 80 can edit annotations. nginx
passes every Host to the app, so that the page answers on any address. To stop
a malicious web page from rebinding its own domain name to the Z2's address
and sending writes from the visitor's browser, write requests (POST, PUT,
PATCH, DELETE) get `403` unless the `Host` header names a trusted host:

- an IP address (IPv4, or IPv6 in brackets)
- a name without dots, such as `z2` or `localhost`
- a name ending in `.local`
- the tailnet MagicDNS name, as found by `tailscale serve` discovery (not
  trusted while that source fails)
- a name listed in the `TRUSTED_HOSTS` setting (comma-separated, from the
  environment or `.env`; empty by default)

Ports are ignored and names are compared case-insensitively.

A page on another site could still send writes to a trusted address from the
visitor's browser, so a write request also gets `403` when:

- it has an `Origin` header whose host is not the `Host` header's host (ports
  ignored), or
- it has a `Sec-Fetch-Site` header other than `same-origin` or `none`.

A POST, PUT or PATCH with a body gets `415` unless its `Content-Type` is
`application/json` (parameters such as `; charset=utf-8` are allowed): a
cross-site form or simple fetch cannot send that type without a CORS
preflight, which the app does not answer. Tools such as `curl` send neither
`Origin` nor `Sec-Fetch-Site` and are not affected beyond the `Content-Type`
rule.

Reads (GET, HEAD, OPTIONS) work under any Host.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn src.api.main:app --reload
.venv/bin/pytest
```

Discovery needs `ss`, `docker`, `tailscale`, `ufw` and `systemctl`, and root
for the full picture. Without them the page still loads and reports the
failed sources.

`pytest` uses a temporary database set up in `tests/conftest.py`, so it never
touches `service_registry.db`. Discovery tests run against captured command
output in `tests/fixtures/z2/`.

## Project structure

```
src/
  api/
    main.py                  FastAPI app
    routes/                  pages.py (landing page), services.py, health.py
    schemas/service_schema.py
    dependencies/            services.py, trusted_host.py (write Host/Origin/type check)
    templates/               base.html, index.html
  services/
    discovery/               sockets, cgroups, units, docker_ports,
                             tailscale_serve, firewall, inventory, cache
    health_check.py          HTTP and health-path probes
  models/                    annotation.py, registration_attempt.py,
                             service.py (legacy), base.py
  repositories/              annotation_repository.py,
                             registration_attempt_repository.py
  core/                      database.py, exceptions.py
  config/
deploy/
  nginx/service-registry.conf
  systemd/service-registry.service
tests/                       unit/, integration/, fixtures/z2/
docs/
```

## Deployment

Run these on the Z2.

1. Install the nginx vhost:

   ```bash
   sudo cp deploy/nginx/service-registry.conf /etc/nginx/sites-available/service-registry
   ls -l /etc/nginx/sites-enabled/   # create the service-registry symlink if missing
   sudo rm /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx
   ```

2. Open port 80 to the LAN (tailnet traffic already reaches nginx):

   ```bash
   sudo ufw allow in on eno1 from 192.168.2.0/24 to any port 80 proto tcp
   ```

3. Update the live checkout in `/home/cpeddle/service-registry`:

   ```bash
   cd /home/cpeddle/service-registry
   git pull --ff-only origin master
   ```

   Untracked files (`service_registry.db`, `.venv`) are not touched.

4. If the unit file changed, install it, then restart:

   ```bash
   sudo cp deploy/systemd/service-registry.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl restart service-registry
   ```

5. Check:

   ```bash
   for h in 192.168.2.48 z2 z2.local; do
     curl -s -H "Host: $h" http://127.0.0.1/ | grep -o '<title>[^<]*'
   done
   ```

   Each should print the registry title. Then open http://192.168.2.48/ from
   a phone on the LAN and http://z2/ from a tailnet device.

Use http://z2/ as the tailnet entry point. HTTPS (443) on the bare MagicDNS
name (`z2.<tailnet-name>.ts.net`) belongs to another service, and browsers that
upgrade to HTTPS automatically would land there.

Logs: `sudo journalctl -u service-registry -f`.
