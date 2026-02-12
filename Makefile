.PHONY: setup-hooks lint fmt test clean

# Install pre-commit hooks
setup-hooks:
	@command -v pre-commit >/dev/null 2>&1 || { echo "Installing pre-commit..."; pip install pre-commit; }
	pre-commit install
	@echo "Pre-commit hooks installed successfully"

# Run all linters
lint:
	@command -v golangci-lint >/dev/null 2>&1 || { echo "golangci-lint not found. Install from https://golangci-lint.run/usage/install/"; exit 1; }
	@find . -name "go.mod" -execdir golangci-lint run ./... \;

# Format all Go code
fmt:
	@find . -name "*.go" -exec gofmt -w {} \;
	@find . -name "go.mod" -execdir go mod tidy \;

# Run pre-commit on all files
check:
	pre-commit run --all-files

# Clean up
clean:
	@find . -name "*.test" -delete
	@find . -name "*.out" -delete
