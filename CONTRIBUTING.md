# Contributing to qbrix-python

Thanks for your interest in contributing to the Qbrix Python SDK! This guide will help you get started.

## Getting Started

1. **Fork** the repository and clone your fork
2. **Install dependencies** using [uv](https://docs.astral.sh/uv/):
   ```bash
   uv sync
   ```
3. **Create a branch** for your change:
   ```bash
   git checkout -b my-feature
   ```

## Development

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=qbrix

# Single test file
uv run pytest tests/test_resource_pool.py

# Single test by name
uv run pytest tests/test_resource_pool.py -k "test_create_pool"
```

### Formatting

```bash
uv run black .
```

### Type Checking

```bash
uv run mypy qbrix/
```

## Submitting Changes

1. Make sure all tests pass and code is formatted
2. Write clear, concise commit messages
3. Open a pull request against `main`
4. Describe **what** changed and **why** in the PR description

## Pull Request Guidelines

- Keep PRs focused — one logical change per PR
- Add tests for new functionality
- Update type annotations for any new or changed public APIs
- Don't break backward compatibility without discussion first

## Reporting Bugs

Open a [GitHub issue](https://github.com/optiq-io/qbrix-python/issues) with:

- Python version and OS
- SDK version (`pip show qbrix`)
- Minimal reproduction steps
- Expected vs actual behavior

## Security Vulnerabilities

Please **do not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).