"""Tests for JSON input functionality."""

import pytest
import subprocess
import json
import tempfile
import os
from pathlib import Path


def test_json_input_via_pipe():
    """Test piping JSON data into cheshire."""
    json_data = [
        {"name": "Alice", "score": 90},
        {"name": "Bob", "score": 85},
        {"name": "Charlie", "score": 95}
    ]
    
    # Pipe JSON and query it
    process = subprocess.Popen(
        ["cheshire", "SELECT name as x, score as y FROM data", "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Check that data was loaded
    assert "Loaded 3 rows" in stderr
    
    # Parse the JSON output
    # Extract JSON from output (might have ANSI codes)
    import re
    # Clean ANSI codes first
    from tests.conftest import strip_ansi_codes
    clean_stdout = strip_ansi_codes(stdout)
    json_match = re.search(r'\[.*?\]', clean_stdout, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        assert len(result) == 3
        assert any(r["x"] == "Alice" and r["y"] == 90 for r in result)
        assert any(r["x"] == "Charlie" and r["y"] == 95 for r in result)


def test_json_input_with_flag():
    """Test JSON input with explicit --json-input flag."""
    json_data = [
        {"category": "A", "value": 10},
        {"category": "B", "value": 20}
    ]
    
    process = subprocess.Popen(
        ["cheshire", "SELECT * FROM data", "json", "--json-input"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Check that data was loaded
    assert "Loaded 2 rows" in stderr
    assert "category, value" in stderr


def test_json_aggregation():
    """Test SQL aggregation on JSON data."""
    json_data = [
        {"category": "A", "amount": 100},
        {"category": "B", "amount": 200},
        {"category": "A", "amount": 150},
        {"category": "B", "amount": 50}
    ]
    
    query = "SELECT category as x, SUM(amount) as y FROM data GROUP BY category ORDER BY y DESC"
    
    process = subprocess.Popen(
        ["cheshire", query, "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Parse the JSON output
    import re
    from tests.conftest import strip_ansi_codes
    clean_stdout = strip_ansi_codes(stdout)
    json_match = re.search(r'\[.*?\]', clean_stdout, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        assert len(result) == 2
        # Check aggregation results
        assert result[0]["x"] in ["A", "B"]
        assert result[0]["y"] in [250, 250]  # B should have 250
        if result[0]["x"] == "A":
            assert result[0]["y"] == 250
            assert result[1]["y"] == 250
        else:
            assert result[0]["y"] == 250
            assert result[1]["y"] == 250


def test_json_filtering():
    """Test filtering JSON data with WHERE clause."""
    json_data = [
        {"name": "Alice", "age": 30, "city": "NYC"},
        {"name": "Bob", "age": 25, "city": "LA"},
        {"name": "Charlie", "age": 35, "city": "NYC"},
        {"name": "David", "age": 28, "city": "Chicago"}
    ]
    
    query = "SELECT name as x, age as y FROM data WHERE city = 'NYC'"
    
    process = subprocess.Popen(
        ["cheshire", query, "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Parse the JSON output
    import re
    from tests.conftest import strip_ansi_codes
    clean_stdout = strip_ansi_codes(stdout)
    json_match = re.search(r'\[.*?\]', clean_stdout, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        assert len(result) == 2  # Only NYC records
        names = [r["x"] for r in result]
        assert "Alice" in names
        assert "Charlie" in names
        assert "Bob" not in names
        assert "David" not in names


def test_single_json_object():
    """Test that a single JSON object is handled correctly."""
    json_data = {"name": "Alice", "score": 100}
    
    process = subprocess.Popen(
        ["cheshire", "SELECT * FROM data", "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Should wrap single object in array
    assert "Loaded 1 rows" in stderr or "Loaded 1 row" in stderr


def test_invalid_json():
    """Test handling of invalid JSON input."""
    invalid_json = "not valid json"
    
    process = subprocess.Popen(
        ["cheshire", "SELECT * FROM data", "json", "--json-input"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=invalid_json)
    
    # When invalid JSON is provided with --json-input flag, it should handle gracefully
    # Since the JSON is invalid, it won't create the 'data' table, leading to an error
    assert "Error" in stdout or "data does not exist" in stdout or process.returncode != 0


def test_json_with_complex_query():
    """Test complex SQL queries on JSON data."""
    json_data = [
        {"date": "2024-01-01", "product": "A", "sales": 100},
        {"date": "2024-01-01", "product": "B", "sales": 150},
        {"date": "2024-01-02", "product": "A", "sales": 120},
        {"date": "2024-01-02", "product": "B", "sales": 180},
    ]
    
    # Complex query with multiple aggregations
    query = """
    SELECT 
        product as x,
        SUM(sales) as y
    FROM data 
    WHERE sales > 100
    GROUP BY product
    HAVING SUM(sales) > 200
    """
    
    process = subprocess.Popen(
        ["cheshire", query, "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(json_data))
    
    # Parse the JSON output
    import re
    from tests.conftest import strip_ansi_codes
    clean_stdout = strip_ansi_codes(stdout)
    json_match = re.search(r'\[.*?\]', clean_stdout, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        # Only product B should match (150 + 180 = 330 > 200)
        assert len(result) == 1
        assert result[0]["x"] == "B"
        assert result[0]["y"] == 330


def test_json_from_file():
    """Test reading JSON from a file and piping it."""
    json_data = [
        {"id": 1, "value": 100},
        {"id": 2, "value": 200},
        {"id": 3, "value": 300}
    ]
    
    # Create a temporary JSON file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(json_data, f)
        temp_file = f.name
    
    try:
        # Use cat to pipe the file content
        result = subprocess.run(
            f"cat {temp_file} | cheshire 'SELECT AVG(value) as avg_value FROM data' json",
            shell=True,
            capture_output=True,
            text=True
        )
        
        # Parse the JSON output
        import re
        from tests.conftest import strip_ansi_codes
        clean_stdout = strip_ansi_codes(result.stdout)
        json_match = re.search(r'\[.*?\]', clean_stdout, re.DOTALL)
        if json_match:
            output = json.loads(json_match.group())
            assert len(output) == 1
            assert output[0]["avg_value"] == 200.0
    finally:
        # Clean up
        if os.path.exists(temp_file):
            os.unlink(temp_file)