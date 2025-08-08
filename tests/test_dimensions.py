"""Tests for width and height dimension settings."""

import pytest
import subprocess
import os


def count_output_lines(output):
    """Count non-empty lines in output, excluding ANSI escape sequences."""
    from tests.conftest import strip_ansi_codes
    clean = strip_ansi_codes(output)
    # Split and count non-empty lines
    lines = [l for l in clean.split('\n') if l.strip()]
    return len(lines)


def measure_output_width(output):
    """Measure the maximum width of output lines."""
    from tests.conftest import strip_ansi_codes
    clean = strip_ansi_codes(output)
    lines = clean.split('\n')
    max_width = 0
    for line in lines:
        # Strip trailing whitespace but keep internal spacing
        line = line.rstrip()
        if len(line) > max_width:
            max_width = len(line)
    return max_width


def test_absolute_width_height():
    """Test setting absolute width and height values."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y UNION ALL SELECT 'B', 20", "bar", 
         "--width", "40", "--height", "10"],
        capture_output=True,
        text=True
    )
    
    # Output should be constrained to roughly the specified dimensions
    width = measure_output_width(result.stdout)
    lines = count_output_lines(result.stdout)
    
    # Width should be around 40 (allowing for some variance)
    assert 35 <= width <= 45, f"Width was {width}, expected around 40"
    
    # Height should be around 10 lines
    assert 8 <= lines <= 12, f"Height was {lines}, expected around 10"


def test_percentage_width():
    """Test setting width as a percentage."""
    # Get terminal width
    try:
        terminal_width = os.get_terminal_size().columns
    except:
        terminal_width = 80
    
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--width", "50%"],
        capture_output=True,
        text=True
    )
    
    width = measure_output_width(result.stdout)
    expected_width = terminal_width * 0.5
    
    # Check that width is roughly 50% of terminal
    assert abs(width - expected_width) < 10, f"Width was {width}, expected around {expected_width}"


def test_percentage_height():
    """Test setting height as a percentage."""
    # Get terminal height
    try:
        terminal_height = os.get_terminal_size().lines
    except:
        terminal_height = 24
    
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--height", "50%"],
        capture_output=True,
        text=True
    )
    
    lines = count_output_lines(result.stdout)
    expected_height = terminal_height * 0.5
    
    # Check that height is roughly 50% of terminal
    assert abs(lines - expected_height) < 5, f"Height was {lines}, expected around {expected_height}"


def test_combined_width_height():
    """Test setting both width and height together."""
    result = subprocess.run(
        ["cheshire", "SELECT 'Test' as x, 100 as y", "bar", 
         "--width", "60", "--height", "15"],
        capture_output=True,
        text=True
    )
    
    width = measure_output_width(result.stdout)
    lines = count_output_lines(result.stdout)
    
    assert 55 <= width <= 65, f"Width was {width}, expected around 60"
    assert 13 <= lines <= 17, f"Height was {lines}, expected around 15"


def test_invalid_width():
    """Test handling of invalid width values."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--width", "invalid"],
        capture_output=True,
        text=True
    )
    
    # Should get a warning about invalid width
    assert "Invalid size value" in result.stderr or "Warning" in result.stderr


def test_invalid_percentage():
    """Test handling of invalid percentage values."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--width", "150%"],
        capture_output=True,
        text=True  
    )
    
    # Should get a warning about percentage out of range
    assert "Percentage must be between" in result.stderr or "Warning" in result.stderr


def test_negative_dimensions():
    """Test handling of negative dimension values."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "bar", "--width", "-50"],
        capture_output=True,
        text=True
    )
    
    # Should get a warning about negative size
    assert "must be positive" in result.stderr or "Warning" in result.stderr


def test_width_height_with_json():
    """Test that width/height don't affect JSON output."""
    result = subprocess.run(
        ["cheshire", "SELECT 'A' as x, 10 as y", "json", 
         "--width", "40", "--height", "10"],
        capture_output=True,
        text=True
    )
    
    # JSON output should not be affected by width/height
    assert '"x": "A"' in result.stdout
    assert '"y": 10' in result.stdout


def test_width_height_applies_to_scatter():
    """Test that width/height applies to scatter charts."""
    result = subprocess.run(
        ["cheshire", "SELECT 1 as x, 10 as y UNION ALL SELECT 2, 20", "scatter",
         "--width", "45", "--height", "12"],
        capture_output=True,
        text=True
    )
    
    width = measure_output_width(result.stdout)
    lines = count_output_lines(result.stdout)
    
    # Scatter plot should respect dimensions
    assert 40 <= width <= 50
    assert 10 <= lines <= 14


def test_width_height_applies_to_line():
    """Test that width/height applies to line charts."""
    result = subprocess.run(
        ["cheshire", "SELECT 1 as x, 10 as y UNION ALL SELECT 2, 20 UNION ALL SELECT 3, 15", "line",
         "--width", "50", "--height", "10"],
        capture_output=True,
        text=True
    )
    
    width = measure_output_width(result.stdout)
    lines = count_output_lines(result.stdout)
    
    # Line chart should respect dimensions  
    assert 45 <= width <= 55
    assert 8 <= lines <= 12