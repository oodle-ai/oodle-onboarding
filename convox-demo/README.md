# convox-demo

A sample **Ruby on Rails** application deployed to a **Convox v2 (generation 2)** rack on AWS.

This is the baseline deploy — a minimal, stateless Rails 7.1 app (no database) running as a
single Convox web service. It exists as the foundation for shipping Rails telemetry
(logs, metrics, traces) to [Oodle](https://oodle.ai) in a later pass.

## What it demonstrates

- Packaging a Rails app for Convox with the standard Rails 7.1 production `Dockerfile`
- A generation-2 `convox.yml` manifest: one `web` service, health-checked on Rails' `/up`
- The full deploy loop via `convox deploy`

## Layout

| File | Purpose |
|------|---------|
| `convox.yml` | Convox v2 manifest — the `web` service, env, health check, scale |
| `Dockerfile` | Rails 7.1 production image (multi-stage, non-root) |
| `Makefile` | `up` / `deploy` / `logs` / `down` / `clean` wrappers around the `convox` CLI |
| `.env.example` | Rack + app name overrides |
| `app/`, `config/`, `bin/`, … | The generated Rails application |

## Prerequisites

- The [`convox` CLI](https://docs.convox.com/) installed and logged in (`convox version`)
- A running generation-2 rack (`convox racks`) — this demo targets `org-team-i4e/gm-test`
- Docker running locally (Convox builds the image before promoting)

## Deploy

```bash
cd convox-demo
cp .env.example .env      # optional — edit RACK / APP if different
make up                   # create app, set SECRET_KEY_BASE, build, deploy, print URL
```

`make up` runs:

1. `convox apps create` — creates the app on the rack (skipped if it exists)
2. `convox env set SECRET_KEY_BASE=…` — required by Rails in production
3. `convox deploy` — builds the Docker image, pushes it, and promotes a release
4. `convox services` — prints the public HTTPS endpoint

Open the printed endpoint in a browser to see the welcome page. Health check is at `/up`.

## Common commands

```bash
make logs     # tail application logs
make down     # scale web to 0 (stop compute, keep the app)
make deploy   # redeploy after changes
make clean    # delete the app entirely
```

## Notes

- **SSL**: `config.force_ssl` is off by default so Convox's internal HTTP health check on `/up`
  returns 200 instead of a 301 redirect. The Convox router still serves the app over HTTPS
  externally. Set `RAILS_FORCE_SSL=true` in the app env to re-enable in-app SSL enforcement.
- **Stateless**: the app is generated with `--skip-active-record`, so there is no database and
  nothing to migrate.
