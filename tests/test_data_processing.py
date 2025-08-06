"""Tests for data processing and transformation functions."""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_sql_result_to_json():
    """Test converting SQL results to JSON format."""
    from cheshire.main import main
    
    # Mock the DuckDB connection and results
    with patch('cheshire.main.duckdb.connect') as mock_connect:
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        # Mock query results
        mock_conn.execute.return_value.fetchall.return_value = [
            ('Alice', 100, 'A'),
            ('Bob', 200, 'B'),
        ]
        mock_conn.execute.return_value.description = [
            ('name',), ('value',), ('category',)
        ]
        
        # Test would require refactoring main to be more testable
        # For now, we're documenting what should be tested
        pass


def test_csv_data_loading(sample_csv_file):
    """Test loading and querying CSV data."""
    try:
        import duckdb
        
        conn = duckdb.connect(':memory:')
        
        # Load CSV file
        result = conn.execute(f"""
            SELECT COUNT(*) as count 
            FROM read_csv_auto('{sample_csv_file}')
        """).fetchall()
        
        assert result[0][0] == 4  # Should have 4 rows
        
        # Test column names
        result = conn.execute(f"""
            SELECT * 
            FROM read_csv_auto('{sample_csv_file}')
            LIMIT 1
        """)
        
        columns = [desc[0] for desc in result.description]
        assert 'name' in columns
        assert 'value' in columns
        assert 'category' in columns
        
        conn.close()
    except ImportError:
        pytest.skip("DuckDB not available")


def test_tsv_data_loading(sample_tsv_file):
    """Test loading and querying TSV data."""
    try:
        import duckdb
        
        conn = duckdb.connect(':memory:')
        
        # Load TSV file
        result = conn.execute(f"""
            SELECT COUNT(*) as count 
            FROM read_csv_auto('{sample_tsv_file}', delim='\\t')
        """).fetchall()
        
        assert result[0][0] == 4  # Should have 4 rows
        
        conn.close()
    except ImportError:
        pytest.skip("DuckDB not available")


def test_parquet_data_loading(sample_parquet_file):
    """Test loading and querying Parquet data."""
    try:
        import duckdb
        
        conn = duckdb.connect(':memory:')
        
        # Load Parquet file
        result = conn.execute(f"""
            SELECT COUNT(*) as count 
            FROM read_parquet('{sample_parquet_file}')
        """).fetchall()
        
        assert result[0][0] == 3  # Should have 3 rows
        
        # Test data types
        result = conn.execute(f"""
            SELECT item, price, category
            FROM read_parquet('{sample_parquet_file}')
            WHERE item = 'Item1'
        """).fetchall()
        
        assert len(result) == 1
        assert result[0][0] == 'Item1'
        assert result[0][1] == 10.5
        assert result[0][2] == 'Category1'
        
        conn.close()
    except ImportError:
        pytest.skip("DuckDB not available")


def test_sqlite_connection(sample_sqlite_db):
    """Test connecting to and querying SQLite database."""
    try:
        import sqlite3
        
        conn = sqlite3.connect(sample_sqlite_db)
        cursor = conn.cursor()
        
        # Test basic query
        result = cursor.execute("SELECT COUNT(*) FROM sales").fetchone()
        assert result[0] == 4
        
        # Test aggregation
        result = cursor.execute("""
            SELECT product, SUM(amount) as total
            FROM sales
            GROUP BY product
            ORDER BY total DESC
        """).fetchall()
        
        assert len(result) == 3  # 3 unique products
        assert result[0][0] == 'Product A'  # Most sales
        assert result[0][1] == 300.0  # Total for Product A
        
        conn.close()
    except ImportError:
        pytest.skip("SQLite not available")


def test_ansi_stripping():
    """Test ANSI code stripping utility."""
    from tests.conftest import strip_ansi_codes
    
    # Test various ANSI codes
    text_with_ansi = "\x1b[31mRed Text\x1b[0m Normal \x1b[1;32mBold Green\x1b[0m"
    cleaned = strip_ansi_codes(text_with_ansi)
    
    assert cleaned == "Red Text Normal Bold Green"
    assert "\x1b" not in cleaned
    assert "[31m" not in cleaned


def test_data_type_detection():
    """Test automatic data type detection for chart suggestions."""
    # This would test the logic for detecting numeric vs categorical columns
    # and suggesting appropriate chart types
    
    test_data = [
        {"name": "Alice", "age": 30, "score": 95.5, "grade": "A"},
        {"name": "Bob", "age": 25, "score": 87.3, "grade": "B"},
    ]
    
    # Numeric columns: age, score
    # Categorical columns: name, grade
    
    # The actual implementation would need to be extracted to be testable
    pass


def test_chart_data_preparation():
    """Test data preparation for different chart types."""
    
    # Test data for bar chart (needs x and y)
    bar_data = [
        {"x": "A", "y": 10},
        {"x": "B", "y": 20},
        {"x": "C", "y": 15},
    ]
    
    # Test data for scatter plot (needs x and y, both numeric)
    scatter_data = [
        {"x": 1.0, "y": 2.5},
        {"x": 2.0, "y": 3.7},
        {"x": 3.0, "y": 4.2},
    ]
    
    # Test data for pie chart (needs labels and values)
    pie_data = [
        {"x": "Category1", "y": 30},
        {"x": "Category2", "y": 45},
        {"x": "Category3", "y": 25},
    ]
    
    # The actual implementation would need to be extracted to be testable
    pass


@pytest.mark.parametrize("query,expected_columns", [
    ("SELECT name as x, value as y FROM data", ["x", "y"]),
    ("SELECT * FROM data", None),  # All columns
    ("SELECT COUNT(*) as count FROM data", ["count"]),
    ("SELECT name, SUM(value) as total FROM data GROUP BY name", ["name", "total"]),
])
def test_query_column_extraction(query, expected_columns):
    """Test extracting column names from SQL queries."""
    # This would test the logic for determining output columns
    # from SQL queries to validate chart requirements
    pass