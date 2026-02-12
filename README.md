# oodle-onboarding

Demo repository showcasing working examples of various integrations supported by the Oodle platform.

## Purpose

This repository serves as:
- Demonstration ground for Oodle platform integrations
- Working examples for different vendor alternatives
- Reference implementations across multiple languages/environments
- Onboarding resource for new integrations

## Available Integrations

### [opensearch-alternative](./opensearch-alternative)
Log aggregation and search with OpenSearch, including Fluent Bit log collection and OpenSearch Dashboards.

## Structure

Each top-level folder represents a specific integration or vendor alternative:
- Self-contained examples (no shared dependencies)
- Multiple implementation approaches (docker-compose, kubernetes, language-specific, etc.)
- Complete setup with documentation

## Getting Started

1. Navigate to the integration you want to explore
2. Follow the README in that folder
3. Each setup is self-contained and can be run independently

## Development

### Prerequisites

- Go 1.25+
- Docker & Docker Compose
- [pre-commit](https://pre-commit.com/#install) (for git hooks)
- [golangci-lint](https://golangci-lint.run/usage/install/) (for Go linting)

### Setup

Install pre-commit hooks:
```bash
make setup-hooks
```

### Linting and Formatting

```bash
make lint    # Run all linters
make fmt     # Format all Go code
make check   # Run all pre-commit checks
```

Pre-commit hooks will automatically run on `git commit` to ensure code quality.

## Adding New Integrations

When adding a new integration:
1. Create a top-level folder named `{vendor/tool}-alternative`
2. Organize by setup type (e.g., `docker-compose/`, `kubernetes/`, language folders)
3. Include a README explaining what the integration demonstrates
4. Keep each setup completely self-contained
