# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is a demo/showcase repository for Oodle platform integrations. It contains working examples of various vendor alternatives (OpenSearch, Datadog, Prometheus, etc.) and different signal types across multiple languages and environments.

## Repository Structure

```
oodle-onboarding/
├── opensearch-alternative/
├── datadog-alternative/
├── prometheus-alternative/
└── ...
```

**Key principles:**
- Each `*-alternative/` folder is a top-level integration that is completely self-contained
- Within each alternative, organize by setup type (e.g., `docker-compose/`, `kubernetes/`) or language (e.g., `go/`, `python/`)
- No shared configurations or dependencies between integrations
- Each setup should be independently runnable

## Working with Docker Compose Setups

Most integrations include a `docker-compose/` setup. Common commands:

```bash
# Start all services
docker-compose up --build

# Start in background
docker-compose up --build -d

# View logs
docker-compose logs -f [service-name]

# Stop services
docker-compose down

# Clean state (remove volumes)
docker-compose down -v
```

## Working with Go Examples

Standard Go tooling applies:

- `go build` - Build the project
- `go run main.go` - Run the application
- `go mod tidy` - Clean up dependencies
- `go fmt ./...` - Format all Go files

## Code Quality

This repository uses pre-commit hooks and linters:

- **Setup hooks**: `make setup-hooks` (run once after cloning)
- **Run linters**: `make lint` (runs golangci-lint on all Go code)
- **Format code**: `make fmt` (formats all Go files)
- **Check all**: `make check` (runs all pre-commit checks)

Pre-commit hooks automatically run on commit. If a hook fails, fix the issues and re-commit.

## Adding New Integrations

When creating a new integration:

1. Create a top-level folder: `{vendor/tool}-alternative/`
2. Add a README.md explaining the integration
3. Organize by setup type or language as appropriate
4. Ensure complete self-containment (all configs, dependencies, docker files)
5. Update the main README.md with the new integration

## Notes

- Each integration demonstrates a specific vendor/tool integration with the Oodle platform
- Setups should be minimalistic and focused on demonstrating the integration
- `.idea/` directory (JetBrains IDE) is present but not tracked in git
