"""Pytest configuration and shared fixtures for Cheshire tests."""

import pytest
import tempfile
import os
import json
import csv
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_csv_file(temp_dir):
    """Create a sample CSV file for testing."""
    csv_path = temp_dir / "test_data.csv"
    data = [
        ["name", "value", "category"],
        ["Alice", "100", "A"],
        ["Bob", "200", "B"],
        ["Charlie", "150", "A"],
        ["David", "300", "B"],
    ]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(data)
    return str(csv_path)


@pytest.fixture
def sample_tsv_file(temp_dir):
    """Create a sample TSV file for testing."""
    tsv_path = temp_dir / "test_data.tsv"
    data = [
        ["product", "sales", "region"],
        ["Widget", "1000", "North"],
        ["Gadget", "1500", "South"],
        ["Doohickey", "800", "East"],
        ["Thingamajig", "1200", "West"],
    ]
    with open(tsv_path, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerows(data)
    return str(tsv_path)


@pytest.fixture
def sample_parquet_file(temp_dir):
    """Create a sample Parquet file for testing."""
    try:
        import duckdb
        parquet_path = temp_dir / "test_data.parquet"
        
        # Create a simple parquet file using DuckDB
        conn = duckdb.connect(':memory:')
        conn.execute("""
            CREATE TABLE test_data AS 
            SELECT * FROM (VALUES 
                ('Item1', 10.5, 'Category1'),
                ('Item2', 20.3, 'Category2'),
                ('Item3', 15.7, 'Category1')
            ) AS t(item, price, category)
        """)
        conn.execute(f"COPY test_data TO '{parquet_path}' (FORMAT PARQUET)")
        conn.close()
        
        return str(parquet_path)
    except ImportError:
        pytest.skip("DuckDB not available")


@pytest.fixture
def sample_sqlite_db(temp_dir):
    """Create a sample SQLite database for testing."""
    import sqlite3
    db_path = temp_dir / "test.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create a simple table with data
    cursor.execute("""
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY,
            product TEXT,
            amount REAL,
            date TEXT
        )
    """)
    
    data = [
        (1, 'Product A', 100.0, '2024-01-01'),
        (2, 'Product B', 150.0, '2024-01-02'),
        (3, 'Product A', 200.0, '2024-01-03'),
        (4, 'Product C', 75.0, '2024-01-04'),
    ]
    
    cursor.executemany("INSERT INTO sales VALUES (?, ?, ?, ?)", data)
    conn.commit()
    conn.close()
    
    return str(db_path)


@pytest.fixture
def mock_config_file(temp_dir):
    """Create a mock configuration file."""
    config_path = temp_dir / "cheshire.yaml"
    config = {
        "databases": {
            "test_db": {
                "type": "duckdb",
                "path": ":memory:"
            }
        },
        "default_database": "test_db",
        "chart_defaults": {
            "theme": "matrix",
            "width": 80,
            "height": 24
        }
    }
    
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    
    return str(config_path)


def strip_ansi_codes(text):
    """Remove ANSI escape codes from text for testing."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)