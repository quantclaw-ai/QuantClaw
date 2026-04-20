# Contributing to QuantClaw

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/quantclaw.git
cd quantclaw
pip install -e ".[dev]"
pytest tests/ -v
```

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Write tests for any new functionality
3. Run `pytest tests/ -v` and ensure all tests pass
4. Run `ruff check quantclaw/` for linting
5. Update documentation if needed
6. Submit a PR with a clear description

## Code Style

- Python 3.12+ features welcome
- Type hints on all public functions
- Docstrings on all modules and classes
- Follow existing patterns in the codebase

## Adding a Strategy Template

1. Create a file in `quantclaw/strategy/templates/<category>/`
2. Implement the `Strategy` class with `signals()` and `allocate()` methods
3. Add a docstring with name, description, and difficulty
4. Test it works with the built-in backtest engine

## Building a Plugin

1. Create a new package named `quantclaw-<type>-<name>`
2. Implement the appropriate interface from `quantclaw.plugins.interfaces`
3. Register via entry point in your `pyproject.toml`:

```toml
[project.entry-points."quantclaw.plugins"]
data_mydata = "quantclaw_mydata:MyDataPlugin"
```

4. Publish to PyPI

## Reporting Issues

Use the GitHub issue templates:
- Bug Report -- for something broken
- Feature Request -- for new ideas
- Strategy Request -- for new template ideas
