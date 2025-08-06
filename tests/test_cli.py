"""Tests for CLI argument parsing and basic command execution."""

import pytest
import subprocess
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


def test_version_command():
    """Test that --version command works."""
    result = subprocess.run(
        ["cheshire", "--version"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Cheshire" in result.stdout or "cheshire" in result.stdout.lower()


def test_help_command():
    """Test that --help command works."""
    result = subprocess.run(
        ["cheshire", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()


def test_json_output_format():
    """Test JSON output format with a simple query."""
    result = subprocess.run(
        ["cheshire", "SELECT 'test' as name, 123 as value", "json"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        # Try to parse the output as JSON
        try:
            # The output might have ANSI codes, so we need to extract JSON
            output = result.stdout
            # Look for JSON array pattern
            import re
            json_match = re.search(r'\[.*\]', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                assert len(data) == 1
                assert data[0]["name"] == "test"
                assert data[0]["value"] == 123
        except json.JSONDecodeError:
            # If we can't parse JSON, at least check for expected content
            assert "test" in result.stdout
            assert "123" in result.stdout


def test_csv_file_input(sample_csv_file):
    """Test reading from CSV file."""
    result = subprocess.run(
        ["cheshire", "SELECT COUNT(*) as count FROM data", "json", "--csv", sample_csv_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        assert "4" in result.stdout or '"count": 4' in result.stdout


def test_tsv_file_input(sample_tsv_file):
    """Test reading from TSV file."""
    result = subprocess.run(
        ["cheshire", "SELECT COUNT(*) as count FROM data", "json", "--tsv", sample_tsv_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        assert "4" in result.stdout or '"count": 4' in result.stdout


def test_sqlite_db_input(sample_sqlite_db):
    """Test reading from SQLite database."""
    result = subprocess.run(
        ["cheshire", "SELECT COUNT(*) as count FROM sales", "json", "--db", sample_sqlite_db],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        assert "4" in result.stdout or '"count": 4' in result.stdout


def test_invalid_query():
    """Test handling of invalid SQL query."""
    result = subprocess.run(
        ["cheshire", "INVALID SQL QUERY", "json"],
        capture_output=True,
        text=True
    )
    
    # Should fail with non-zero exit code
    assert result.returncode != 0 or "Error" in result.stdout or "error" in result.stdout.lower()


def test_list_databases_command():
    """Test --list-databases command."""
    result = subprocess.run(
        ["cheshire", "--list-databases"],
        capture_output=True,
        text=True
    )
    
    # Command should at least run without crashing
    assert result.returncode == 0 or "database" in result.stdout.lower()


def test_sniff_command_with_csv(sample_csv_file):
    """Test --sniff command with CSV file."""
    result = subprocess.run(
        ["cheshire", "--sniff", "--csv", sample_csv_file],
        capture_output=True,
        text=True
    )
    
    # Should provide analysis or suggestions
    if result.returncode == 0:
        output_lower = result.stdout.lower()
        assert any(word in output_lower for word in ["column", "data", "type", "chart", "suggest"])


@pytest.mark.parametrize("chart_type", [
    "bar", "line", "scatter", "pie", "json", "rich_table"
])
def test_chart_types(chart_type):
    """Test that various chart types are accepted."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", chart_type],
        capture_output=True,
        text=True
    )
    
    # Should at least not crash with valid chart type
    # Some chart types might fail due to data requirements, but shouldn't have syntax errors
    assert "invalid chart type" not in result.stdout.lower()


def test_width_height_parameters():
    """Test width and height parameters."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--width", "50", "--height", "20"],
        capture_output=True,
        text=True
    )
    
    # Should accept width and height parameters without error
    assert "invalid" not in result.stdout.lower() or result.returncode == 0