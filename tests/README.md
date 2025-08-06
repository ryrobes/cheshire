# Cheshire Test Suite

This directory contains the test suite for Cheshire, a terminal-based SQL visualization tool.

## Running Tests

### Quick Start

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=cheshire --cov-report=html

# Run specific test file
pytest tests/test_cli.py

# Run specific test
pytest tests/test_cli.py::test_json_output_format
```

### Using Make

```bash
# Run all tests
make test

# Run tests in parallel
make test-fast

# Run with coverage report
make test-cov

# Run full CI pipeline (format, lint, type-check, test)
make all
```

## Test Organization

- `conftest.py` - Shared fixtures and utilities
- `test_cli.py` - Command-line interface tests
- `test_data_processing.py` - Data loading and SQL processing tests
- `test_visualization.py` - Chart generation and visualization tests

## Test Fixtures

Common fixtures available in all tests:

- `temp_dir` - Temporary directory for test files
- `sample_csv_file` - Sample CSV file with test data
- `sample_tsv_file` - Sample TSV file with test data
- `sample_parquet_file` - Sample Parquet file (requires DuckDB)
- `sample_sqlite_db` - Sample SQLite database
- `mock_config_file` - Mock configuration file

## Testing ANSI Output

Since Cheshire generates ANSI-colored terminal output, we use the `strip_ansi_codes()` helper function to remove color codes when comparing text output:

```python
from tests.conftest import strip_ansi_codes

output = run_command()
clean_output = strip_ansi_codes(output)
assert "expected text" in clean_output
```

## Coverage Reports

Generate HTML coverage reports:

```bash
pytest --cov=cheshire --cov-report=html
open htmlcov/index.html
```

## Continuous Integration

Tests run automatically on:
- Push to main/develop branches
- Pull requests
- Multiple Python versions (3.8-3.12)
- Multiple OS (Ubuntu, macOS, Windows)

See `.github/workflows/test.yml` for CI configuration.

## Writing New Tests

1. Add test file to `tests/` directory with `test_` prefix
2. Use pytest fixtures for common setup
3. Group related tests in classes or modules
4. Use parametrize for testing multiple inputs
5. Mock external dependencies when appropriate

Example:

```python
import pytest
from unittest.mock import Mock

def test_new_feature(sample_csv_file):
    """Test description."""
    # Arrange
    data = load_data(sample_csv_file)
    
    # Act
    result = process_data(data)
    
    # Assert
    assert result.status == "success"
    assert len(result.data) > 0

@pytest.mark.parametrize("input,expected", [
    ("test1", "result1"),
    ("test2", "result2"),
])
def test_with_parameters(input, expected):
    assert transform(input) == expected
```

## Test Markers

Custom markers for organizing tests:

- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.requires_db` - Tests requiring database
- `@pytest.mark.requires_network` - Tests requiring network

Run specific markers:

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"
```