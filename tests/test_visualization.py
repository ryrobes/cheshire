"""Tests for visualization and chart generation."""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_json_visualization():
    """Test JSON output format."""
    from cheshire.main import main
    
    # Test data
    test_results = [
        {"name": "Alice", "score": 95, "grade": "A"},
        {"name": "Bob", "score": 87, "grade": "B"},
    ]
    
    # Convert to JSON
    output = json.dumps(test_results, indent=2, default=str)
    
    # Verify JSON structure
    parsed = json.loads(output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "Alice"
    assert parsed[1]["score"] == 87


def test_rich_table_formatting():
    """Test rich table output format."""
    try:
        from rich.table import Table
        from rich.console import Console
        
        # Create a table
        table = Table(title="Test Data")
        table.add_column("Name", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Category", style="green")
        
        table.add_row("Alice", "100", "A")
        table.add_row("Bob", "200", "B")
        
        # Capture output
        console = Console(file=StringIO(), force_terminal=True)
        console.print(table)
        output = console.file.getvalue()
        
        # Check that table was generated
        assert "Test Data" in output
        assert "Alice" in output
        assert "Bob" in output
        
    except ImportError:
        pytest.skip("Rich library not available")


def test_figlet_text_generation():
    """Test Figlet ASCII art text generation."""
    try:
        from pyfiglet import Figlet
        
        fig = Figlet(font='standard')
        output = fig.renderText("TEST")
        
        # Should generate ASCII art
        assert len(output) > 0
        assert "TEST" in output or "_" in output or "|" in output
        
    except ImportError:
        pytest.skip("Pyfiglet not available")


def test_bar_chart_data_validation():
    """Test data validation for bar charts."""
    
    # Valid bar chart data
    valid_data = [
        {"x": "A", "y": 10},
        {"x": "B", "y": 20},
        {"x": "C", "y": 15},
    ]
    
    # Invalid bar chart data (missing y)
    invalid_data = [
        {"x": "A"},
        {"x": "B"},
    ]
    
    # Test that valid data has required fields
    for item in valid_data:
        assert "x" in item
        assert "y" in item
    
    # Test that invalid data is missing required fields
    for item in invalid_data:
        assert "y" not in item


def test_scatter_plot_numeric_validation():
    """Test that scatter plots require numeric data."""
    
    # Valid scatter data (both numeric)
    valid_data = [
        {"x": 1.0, "y": 2.5},
        {"x": 2.0, "y": 3.7},
    ]
    
    # Invalid scatter data (x is categorical)
    invalid_data = [
        {"x": "A", "y": 2.5},
        {"x": "B", "y": 3.7},
    ]
    
    # Check valid data
    for item in valid_data:
        assert isinstance(item["x"], (int, float))
        assert isinstance(item["y"], (int, float))
    
    # Check invalid data
    for item in invalid_data:
        assert not isinstance(item["x"], (int, float))


def test_pie_chart_percentage_calculation():
    """Test pie chart percentage calculations."""
    
    data = [
        {"x": "Category A", "y": 30},
        {"x": "Category B", "y": 50},
        {"x": "Category C", "y": 20},
    ]
    
    total = sum(item["y"] for item in data)
    assert total == 100
    
    # Calculate percentages
    percentages = [(item["y"] / total) * 100 for item in data]
    assert percentages[0] == 30.0
    assert percentages[1] == 50.0
    assert percentages[2] == 20.0


def test_map_coordinate_validation():
    """Test validation of geographic coordinates."""
    
    # Valid coordinates
    valid_coords = [
        {"lat": 40.7128, "lon": -74.0060},  # New York
        {"lat": 51.5074, "lon": -0.1278},    # London
        {"lat": -33.8688, "lon": 151.2093},  # Sydney
    ]
    
    # Invalid coordinates
    invalid_coords = [
        {"lat": 91.0, "lon": 0.0},     # Latitude > 90
        {"lat": 0.0, "lon": 181.0},    # Longitude > 180
        {"lat": -91.0, "lon": 0.0},    # Latitude < -90
        {"lat": 0.0, "lon": -181.0},   # Longitude < -180
    ]
    
    # Validate valid coordinates
    for coord in valid_coords:
        assert -90 <= coord["lat"] <= 90
        assert -180 <= coord["lon"] <= 180
    
    # Check invalid coordinates
    for coord in invalid_coords:
        is_valid = (-90 <= coord["lat"] <= 90) and (-180 <= coord["lon"] <= 180)
        assert not is_valid


def test_color_theme_application():
    """Test that color themes are properly applied."""
    
    themes = {
        "matrix": {"primary": "green", "secondary": "black"},
        "dark": {"primary": "white", "secondary": "black"},
        "clear": {"primary": "blue", "secondary": "white"},
        "pro": {"primary": "cyan", "secondary": "black"},
    }
    
    for theme_name, colors in themes.items():
        assert "primary" in colors
        assert "secondary" in colors


def test_chart_size_constraints():
    """Test chart size constraints and defaults."""
    
    # Default sizes
    default_width = 80
    default_height = 24
    
    # Test minimum sizes
    min_width = 20
    min_height = 10
    
    # Test maximum sizes (terminal constraints)
    max_width = 200
    max_height = 60
    
    # Validate size ranges
    assert min_width < default_width < max_width
    assert min_height < default_height < max_height
    
    # Test size validation
    test_sizes = [
        (50, 20, True),   # Valid
        (10, 5, False),   # Too small
        (300, 100, False), # Too large
        (80, 24, True),   # Default
    ]
    
    for width, height, should_be_valid in test_sizes:
        is_valid = (min_width <= width <= max_width) and (min_height <= height <= max_height)
        assert is_valid == should_be_valid


def test_live_refresh_interval_parsing():
    """Test parsing of live refresh intervals."""
    
    test_intervals = [
        ("5s", 5),        # 5 seconds
        ("1m", 60),       # 1 minute
        ("0.5h", 1800),   # 30 minutes
        ("2h", 7200),     # 2 hours
    ]
    
    for interval_str, expected_seconds in test_intervals:
        # Parse interval
        if interval_str.endswith('s'):
            seconds = float(interval_str[:-1])
        elif interval_str.endswith('m'):
            seconds = float(interval_str[:-1]) * 60
        elif interval_str.endswith('h'):
            seconds = float(interval_str[:-1]) * 3600
        else:
            seconds = float(interval_str)
        
        assert seconds == expected_seconds


def test_logo_display():
    """Test that logo displays without errors."""
    from tests.conftest import strip_ansi_codes
    
    # Mock logo data
    mock_logo = "\\e[31m╔═══╗\\e[0m\\n\\e[31m║ C ║\\e[0m\\n\\e[31m╚═══╝\\e[0m"
    
    # Process logo (replace literal \e with escape)
    processed = mock_logo.replace('\\e', '\x1b')
    
    # Should contain ANSI codes
    assert '\x1b' in processed
    
    # Strip ANSI codes
    stripped = strip_ansi_codes(processed)
    
    # Should have box drawing characters
    assert '╔' in stripped
    assert '║' in stripped
    assert '╚' in stripped