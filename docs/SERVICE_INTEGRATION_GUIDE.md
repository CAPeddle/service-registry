# Service Integration Guide

The registry lists everything that listens on a TCP port on the Z2. You do not
register a service for it to appear. This guide covers how to make a service
look right on the page, and how to add things the registry cannot discover.

## What shows up automatically

On each page load the registry reads the listening sockets (`ss`), maps each
one to a systemd unit (system or user) or a Docker container, and checks the
ufw rules and `tailscale serve` configuration. A service bound to a port is
listed with its reachability: LAN, blocked by firewall, tailnet only, or
internal only. A link appears only if the port answers HTTP.

## Making a service show up well

### Name it

For a systemd service, set a useful `Description=` in the unit file. It is
shown as the row's description.

```ini
[Unit]
Description=Grafana dashboards

[Service]
ExecStart=/usr/sbin/grafana-server
```

For Docker, compose project and service names are used for the row identity
(`docker:<project>/<service>`).

The description and display name can also be set from the page with the Edit
button on the row.

### Decide who can reach it

- To make it reachable from the LAN, bind to `0.0.0.0` and allow the port in
  ufw on the LAN interface:

  ```bash
  sudo ufw allow in on eno1 from 192.168.2.0/24 to any port <port> proto tcp
  ```

  Without the rule the row is shown as "blocked by firewall".
- Services bound to all addresses are also reachable over the tailnet, because
  tailscaled admits tailnet traffic ahead of ufw.
- To expose a loopback-only service on the tailnet, front it with
  `tailscale serve`. The registry reads the serve configuration and shows the
  tailnet address on that row.
- A service bound to 127.0.0.1 with no `tailscale serve` front-end is listed
  as "internal only" and has no link.

### Add a health endpoint

If the service has an endpoint that returns 2xx when it is healthy, for
example `/health`, set it as the row's health path. Either use the Edit
button, or:

```bash
curl -X POST http://z2/api/services \
  -H 'Content-Type: application/json' \
  -d '{"name": "grafana-server.service", "description": "Grafana dashboards",
       "base_url": "http://127.0.0.1:3000", "health_endpoint": "/api/health"}'
```

If `name` matches a discovered unit, container or compose service, only the
description and health path are stored. `base_url` is required by the API but
is not stored as a link in that case, because links are built from the address
the visitor used.

Page edits win. If the description or health path was set with the Edit
button, a later registration does not overwrite it. When the registration
sends a different value, it is held and shown at the top of the landing page
under "Registrations held for review", next to the current values. From there
you can "Use these values" or "Dismiss" it. The API still answers `201` with
the annotation as stored, so a service that registers on every start keeps
working. Clearing the field with Edit makes it follow registrations again.

## Adding something that is not local

A service on another machine, or one that is not listening on this host, has
nothing to discover. Register it with a name that matches no local unit or
container. This creates a `manual:<name>` row, and `base_url` becomes its link.

```bash
curl -X POST http://z2/api/services \
  -H 'Content-Type: application/json' \
  -d '{"name": "nas", "description": "Network storage admin",
       "base_url": "http://192.168.2.10:5000"}'
```

## API reference

Full schemas are at `/docs` and `/redoc`.

`POST /api/services` body:

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | unit, container or compose service name; or a new name for a manual row |
| `description` | yes | |
| `base_url` | yes | must start with `http://` or `https://` |
| `port` | no | 1 to 65535 |
| `health_endpoint` | no | must start with `/` |

Responses are annotations: `identity_key`, `display_name`, `description`,
`hidden`, `link_override`, `health_path`, `primary_port`.

Other endpoints:

- `GET /api/services` lists all annotations.
- `PUT /api/services/annotation` creates or updates one. The body has
  `identity_key` and any of the annotation fields. Fields you leave out are
  unchanged; an empty string clears a text field. `hidden: null` restores the
  default visibility.
- `DELETE /api/services/annotation?identity_key=<key>` removes one. The
  identity key goes in the query string because it contains `:` and `/`.
- `POST /api/services/registrations/<id>/apply` applies a held registration's
  values to the fields that were held and removes it from the review list.
- `DELETE /api/services/registrations/<id>` dismisses a held registration.

Write requests (POST, PUT, PATCH, DELETE) must be sent to one of the server's
own addresses: an IP address, a name without dots (`z2`), a `.local` name, the
tailnet MagicDNS name, or a name in the `TRUSTED_HOSTS` setting. Anything else
gets `403`, which blocks DNS-rebinding attacks from web pages. `curl
http://z2/...`, `http://192.168.2.48/...` and `http://127.0.0.1/...` all work.
A request body must be sent with `Content-Type: application/json`, or the
request gets `415`. See the README's Security section for the browser checks.

Identity keys look like `system:grafana-server.service`,
`user:1000:myapp.service`, `docker:<project>/<service>`, `manual:<name>` and
`process:<name>`.

```bash
# Give a discovered service a link that differs from the default
curl -X PUT http://z2/api/services/annotation \
  -H 'Content-Type: application/json' \
  -d '{"identity_key": "system:grafana-server.service",
       "link_override": "http://z2:3000/dashboards"}'

# Remove the annotation again
curl -X DELETE 'http://z2/api/services/annotation?identity_key=system:grafana-server.service'
```

## Troubleshooting

- **Service is missing:** it is probably marked as noise (ssh, DNS, nginx,
  tailscaled, unattributed processes). Use "Show hidden" on the page.
- **No link on a row:** the port did not answer HTTP within the probe budget
  (about 1.5 seconds), or the service is internal only. Set a link override
  from the Edit dialog if you want one anyway.
- **"Reachability unknown":** a discovery source failed; the banner at the top
  names it. Check `sudo journalctl -u service-registry`.
- **Stale list:** results are cached for about 10 seconds. Use the Refresh
  link.
