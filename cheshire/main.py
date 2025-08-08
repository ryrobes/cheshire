#!/usr/bin/env python3

import os
import sys

# Force color output for subprocess compatibility BEFORE importing plotext
# This must happen before plotext is imported because it caches TTY status at import time
if not sys.stdout.isatty() or os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'):
    # Monkey-patch stdout to always report as TTY for color support
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    class ForcedColorStream:
        def __init__(self, stream):
            self._stream = stream
            
        def __getattr__(self, name):
            return getattr(self._stream, name)
        
        def isatty(self):
            return True
            
        def write(self, text):
            return self._stream.write(text)
            
        def flush(self):
            return self._stream.flush()
    
    sys.stdout = ForcedColorStream(sys.stdout)
    sys.stderr = ForcedColorStream(sys.stderr)

import time
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import json
import click
import duckdb
import plotext as plt
import yaml
import pyfiglet
from rich.console import Console
from rich.table import Table
from rich import box
from .db_connectors import create_connector, execute_query_compat, is_osquery_available
import termgraph.termgraph as tg
from .map_renderer import render_map
from .matrix_heatmap import render_matrix_heatmap, extract_matrix_data


def parse_dimension(value: Optional[str], terminal_size: int) -> Optional[int]:
    """Parse a dimension value that can be a number or percentage.
    
    Args:
        value: String value like "100", "80%", or None
        terminal_size: The terminal dimension to use for percentage calculation
        
    Returns:
        Parsed integer value or None
    """
    if not value:
        return None
    
    value = value.strip()
    
    # Check if it's a percentage
    if value.endswith('%'):
        try:
            percentage = float(value[:-1])
            if 0 < percentage <= 100:
                return int(terminal_size * percentage / 100)
            else:
                print(f"Warning: Percentage must be between 0 and 100, got {percentage}%", file=sys.stderr)
                return None
        except ValueError:
            print(f"Warning: Invalid percentage value: {value}", file=sys.stderr)
            return None
    else:
        # Try to parse as integer
        try:
            size = int(value)
            if size > 0:
                return size
            else:
                print(f"Warning: Size must be positive, got {size}", file=sys.stderr)
                return None
        except ValueError:
            print(f"Warning: Invalid size value: {value}", file=sys.stderr)
            return None


def detect_and_load_json_stdin():
    """Check if there's JSON data on stdin and return it if valid."""
    import select
    
    # Check if stdin has data (non-blocking check)
    if not sys.stdin.isatty():
        try:
            # Read stdin data
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                # Try to parse as JSON
                json_data = json.loads(stdin_data)
                
                # Validate it's an array of objects
                if isinstance(json_data, list) and len(json_data) > 0:
                    # Check if it's an array of objects
                    if all(isinstance(item, dict) for item in json_data):
                        return json_data
                    else:
                        print("Error: JSON input must be an array of objects")
                        sys.exit(1)
                elif isinstance(json_data, dict):
                    # Single object - wrap in array
                    return [json_data]
                else:
                    print("Error: JSON input must be an array of objects or a single object")
                    sys.exit(1)
        except json.JSONDecodeError as e:
            # Not JSON or invalid JSON - return None to proceed normally
            return None
    return None


def load_json_to_duckdb(json_data, conn):
    """Load JSON data into a DuckDB table named 'data'."""
    # Convert JSON data to a format DuckDB can work with
    # Create a table from the JSON data
    conn.execute("DROP TABLE IF EXISTS data")
    
    # Register the JSON data as a table
    # DuckDB can read JSON directly
    import tempfile
    import os
    
    # Write JSON to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(json_data, f)
        temp_file = f.name
    
    try:
        # Load JSON file into DuckDB
        conn.execute(f"""
            CREATE TABLE data AS 
            SELECT * FROM read_json_auto('{temp_file}')
        """)
        
        # Get row count for confirmation
        result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
        row_count = result[0] if result else 0
        
        # Get column info
        columns = conn.execute("DESCRIBE data").fetchall()
        col_names = [col[0] for col in columns]
        
        print(f"✓ Loaded {row_count} rows with columns: {', '.join(col_names)}", file=sys.stderr)
        
        return True
    finally:
        # Clean up temp file
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    return False


def display_logo():
    """Display the Cheshire ANSI art logo."""
    try:
        # Try multiple methods to find the logo file
        logo_path = None
        logo_data = None
        
        # Method 1: Try importlib.resources first (modern approach)
        try:
            import importlib.resources as resources
            # For Python 3.9+
            if hasattr(resources, 'files'):
                logo_file = resources.files('cheshire') / 'logo.ans'
                if logo_file.is_file():
                    logo_data = logo_file.read_bytes()
            else:
                # For Python 3.7-3.8
                with resources.open_binary('cheshire', 'logo.ans') as f:
                    logo_data = f.read()
        except:
            pass
        
        # Method 2: Try relative to this file (works for editable installs)
        if not logo_data:
            current_dir = Path(__file__).parent
            possible_path = current_dir / 'logo.ans'
            if possible_path.exists():
                with open(possible_path, 'rb') as f:
                    logo_data = f.read()
        
        # If we have logo data, process and display it
        if logo_data:
            # Decode the data
            logo_text = logo_data.decode('utf-8', errors='ignore')
            
            # Replace literal \e with actual escape character (ASCII 27)
            # The file contains literal "\e" instead of the escape character
            logo_text = logo_text.replace('\\e', '\x1b')
            
            # Print the processed ANSI art
            print(logo_text)
    except Exception as e:
        # Silently fail - logo is nice to have but not critical
        pass


def load_config(config_path: str = "cheshire.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
            # Ensure backward compatibility
            if 'databases' not in config and 'database' in config:
                # Convert old format to new format
                default_db = config['database'].get('default', ':memory:')
                config['databases'] = {
                    'default': {'type': 'duckdb', 'path': default_db}
                }
                config['default_database'] = 'default'
    else:
        config = {
            "databases": {
                "default": {"type": "duckdb", "path": ":memory:"}
            },
            "default_database": "default",
            "chart_defaults": {
                "theme": "matrix",
                "markers": "braille",
                "width": None,
                "height": None
            }
        }
    
    # Auto-detect osquery and add it as a persistent database if available
    if is_osquery_available():
        if 'databases' not in config:
            config['databases'] = {}
        # Only add if not already configured
        if 'osquery' not in config['databases']:
            config['databases']['osquery'] = {'type': 'osquery'}
    
    return config


def execute_query(query: str, db_identifier: Any, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute SQL query and return results as list of dictionaries.

    Args:
        query: SQL query to execute
        db_identifier: Either a database name from config, a file path, or a config dict
        config: Full configuration (needed if db_identifier is a name)
    """
    # Check if query is reading from CSV/TSV/Parquet files directly
    # This handles the case where suggestions include read_csv_auto() or read_parquet() calls
    if isinstance(query, str) and ('read_csv_auto(' in query.lower() or 'read_parquet(' in query.lower()):
        # Use in-memory DuckDB for file-based queries
        # The query already contains the full path to the file
        return execute_query_compat(query, ':memory:')
    
    # Handle different types of db_identifier
    if isinstance(db_identifier, dict):
        # Direct config dict
        return execute_query_compat(query, db_identifier)
    elif isinstance(db_identifier, str):
        # Could be a database name or file path
        if config and 'databases' in config and db_identifier in config['databases']:
            # It's a named database from config
            db_config = config['databases'][db_identifier]
            return execute_query_compat(query, db_config)
        else:
            # Assume it's a file path (backward compatibility)
            return execute_query_compat(query, db_identifier)
    else:
        raise ValueError(f"Invalid db_identifier type: {type(db_identifier)}")


def extract_chart_data(results: List[Dict[str, Any]]) -> Tuple[List, List, Optional[List]]:
    """Extract x, y, and optionally color data from query results."""
    if not results:
        return [], [], None

    # Check if this is geographic data (lat/lon columns)
    if 'lat' in results[0] and 'lon' in results[0]:
        # For map charts, x=lon, y=lat
        x_values = [float(row.get('lon', 0)) for row in results]
        y_values = [float(row.get('lat', 0)) for row in results]
    else:
        # Convert x values - handle dates/datetimes
        x_values = []
        for row in results:
            x_val = row.get('x', '')
            # Convert date/datetime objects to string
            # Don't try to force a specific format for line/scatter charts
            if hasattr(x_val, 'isoformat'):
                x_val = str(x_val)
            x_values.append(x_val)

        # Convert y values to float to handle DuckDB decimal types
        y_values = []
        for row in results:
            y_val = row.get('y', 0)
            try:
                y_values.append(float(y_val))
            except (ValueError, TypeError):
                # Keep string values as-is for figlet display
                y_values.append(y_val)

    if 'color' in results[0]:
        color_values = [row.get('color', '') for row in results]
        return x_values, y_values, color_values
    elif 'value' in results[0]:
        # For heatmaps, use value column
        value_values = [float(row.get('value', 0)) for row in results]
        return x_values, y_values, value_values

    return x_values, y_values, None


def group_by_color(x_values: List, y_values: List, color_values: List) -> Dict[str, Tuple[List, List]]:
    """Group x and y values by color."""
    groups = {}
    for x, y, color in zip(x_values, y_values, color_values):
        if color not in groups:
            groups[color] = ([], [])
        groups[color][0].append(x)
        groups[color][1].append(y)
    return groups


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def get_color_for_series(index: int, total: int) -> str:
    """Get a color for a data series based on its index."""
    # Use plotext's color names for better compatibility
    colors = ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
              'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'lime']
    return colors[index % len(colors)]


def render_rich_table(results: List[Dict[str, Any]], title: Optional[str] = None,
                      table_color: Optional[str] = None) -> None:
    """Render query results as a Rich table with all columns."""
    # Force terminal colors even when not running in a TTY (e.g., embedded terminals)
    console = Console(force_terminal=True, color_system="standard")

    # Clear terminal using ANSI escape sequences (preserves color state)
    print('\033[2J\033[H', end='', flush=True)

    if not results:
        console.print("[dim]No results to display[/dim]")
        return

    # Create table with title
    table = Table(title=title if title else "Query Results", box=box.ROUNDED)

    # Determine color style
    style = None
    if table_color:
        if isinstance(table_color, tuple) and len(table_color) == 3:
            # RGB tuple
            r, g, b = table_color
            style = f"rgb({r},{g},{b})"
        elif isinstance(table_color, str) and table_color != 'default':
            style = table_color

    # Add index column
    table.add_column("#", style="dim", width=4)

    # Add all columns from the first result row
    columns = list(results[0].keys())
    for col in columns:
        # Use custom style or default colors for specific column names
        col_style = style
        if not style:
            if col.lower() in ['x', 'date', 'time', 'timestamp']:
                col_style = "cyan"
            elif col.lower() in ['y', 'value', 'amount', 'total', 'sum', 'count']:
                col_style = "green"
            elif col.lower() in ['color', 'category', 'type', 'status']:
                col_style = "yellow"
            else:
                col_style = "white"
        table.add_column(str(col), style=col_style, overflow="fold")

    # Add rows
    for i, row in enumerate(results):
        row_data = [str(i + 1)]  # 1-based index
        for col in columns:
            value = row.get(col, "")
            # Format numbers nicely
            if isinstance(value, (int, float)):
                if isinstance(value, float):
                    row_data.append(f"{value:.2f}")
                else:
                    row_data.append(str(value))
            else:
                row_data.append(str(value))
        table.add_row(*row_data)

    # Add summary footer
    footer_row = [""] * (len(columns) + 1)
    table.add_row(*footer_row, style="dim italic")
    footer_row[0] = "Total"
    footer_row[1] = f"{len(results)} rows"
    table.add_row(*footer_row, style="bold")

    console.print(table)


def render_figlet(value: str, title: Optional[str] = None, color: Optional[str] = None, font: str = "ansi_regular") -> None:
    """Render a large figlet text display for callout values."""
    # Clear terminal using ANSI escape sequences (preserves color state)
    print('\033[2J\033[H', end='', flush=True)

    # Generate figlet text with a very wide width to prevent wrapping
    fig = pyfiglet.Figlet(font=font, width=1000)
    figlet_text = fig.renderText(str(value).strip())

    # Color mapping for ANSI codes
    ansi_colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'orange': '\033[38;5;208m',
        'purple': '\033[38;5;141m',
        'brown': '\033[38;5;130m',
        'pink': '\033[38;5;213m',
        'gray': '\033[90m',
        'olive': '\033[38;5;142m',
        'lime': '\033[38;5;154m',
    }

    # Apply color if specified
    color_code = ansi_colors.get(color, '') if color else '\033[92m'  # Default to green
    reset_code = '\033[0m'

    # Center the content on screen
    try:
        terminal_width = os.get_terminal_size().columns
        terminal_height = os.get_terminal_size().lines
    except:
        # Fallback for non-terminal environments
        terminal_width = 480
        terminal_height = 14

    # terminal_width = 480
    # terminal_height = 14

    # Print title if provided
    if title:
        title_centered = title.center(terminal_width)
        print(f"\n{title_centered}\n")
        lines_used = 3
    else:
        lines_used = 1

    # Print figlet text with color
    figlet_lines = figlet_text.strip().split('\n')

    # Calculate vertical padding
    content_height = len(figlet_lines)
    vertical_padding = 0  # max(0, (terminal_height - content_height - lines_used - 2) // 2)

    # Print top padding
    print('\n' * vertical_padding)

    # Print figlet with horizontal centering
    for line in figlet_lines:
        # Calculate padding for centering
        line_length = len(line)
        padding = 0  # max(0, (terminal_width - line_length) // 2)
        print(' ' * padding + color_code + line + reset_code)

    # Print bottom padding
    print('\n' * vertical_padding)


def format_value(value):
    if isinstance(value, (int, float)):
        return f"{value:,}"
    else:
        return str(value)


def render_termgraph(chart_type: str, x_values: List, y_values: List, 
                    color_values: Optional[List], title: Optional[str] = None,
                    default_color: Optional[str] = None, return_string: bool = False) -> Optional[str]:
    """Render charts using termgraph library."""
    import io
    import sys
    
    # Save original stdout if we need to capture output
    old_stdout = sys.stdout if return_string else None
    string_buffer = io.StringIO() if return_string else None
    
    if return_string:
        sys.stdout = string_buffer
    else:
        # Clear terminal using ANSI escape sequences (preserves color state)
        print('\033[2J\033[H', end='', flush=True)
    
    # Print title if provided
    if title:
        if return_string:
            print(f"\n{title}\n")
        else:
            console = Console()
            console.print(f"\n[bold cyan]{title}[/bold cyan]\n")
    
    # Prepare data for termgraph
    if color_values:
        # Group by color for multi-series
        groups = group_by_color(x_values, y_values, color_values)
        # Reorganize data for termgraph format
        labels = []
        data = []
        seen_x = set()
        
        # First pass: collect all unique x values
        for x in x_values:
            if x not in seen_x:
                seen_x.add(x)
                labels.append(str(x))
        
        # Second pass: build data matrix
        for label in labels:
            row_data = []
            for color_name, (x_group, y_group) in groups.items():
                # Find y value for this x and color
                y_val = 0
                for i, x in enumerate(x_group):
                    if str(x) == label:
                        y_val = float(y_group[i])
                        break
                row_data.append(y_val)
            data.append(row_data)
        
        # Legend labels are the color values
        legend_labels = list(groups.keys())
    else:
        # Single series
        labels = [str(x) for x in x_values]
        data = [[float(y)] for y in y_values]
        legend_labels = []
    
    # Configure termgraph args
    args = {
        'filename': '-',
        'title': None,
        'width': 50,
        'format': '{:<.2f}',
        'suffix': '',
        'no_labels': False,
        'no_values': False,
        'color': None,
        'vertical': False,
        'stacked': chart_type == 'tg_stacked',
        'histogram': chart_type == 'tg_histogram',
        'bins': 5,
        'different_scale': False,
        'calendar': chart_type == 'tg_calendar',
        'start_dt': labels[0] if chart_type == 'tg_calendar' and labels else None,
        'custom_tick': '',
        'delim': '',
        'verbose': False,
        'label_before': False,
        'version': False
    }
    
    # Set color for calendar heatmap
    if chart_type == 'tg_calendar' and default_color:
        # Handle hex colors by converting to nearest basic color
        if isinstance(default_color, str) and default_color.startswith('#'):
            try:
                # Convert hex to RGB
                r = int(default_color[1:3], 16)
                g = int(default_color[3:5], 16)
                b = int(default_color[5:7], 16)
                
                # Find nearest basic color based on RGB values
                # Simple heuristic: check which component is dominant
                if r > g and r > b:
                    if r > 200 and g > 100:
                        args['color'] = ['yellow']  # Orange-ish
                    else:
                        args['color'] = ['red']
                elif g > r and g > b:
                    args['color'] = ['green']
                elif b > r and b > g:
                    args['color'] = ['blue']
                elif r > 200 and g > 200 and b < 100:
                    args['color'] = ['yellow']
                elif r > 200 and b > 200 and g < 100:
                    args['color'] = ['magenta']
                elif g > 200 and b > 200 and r < 100:
                    args['color'] = ['cyan']
                elif r > 200 and g > 200 and b > 200:
                    args['color'] = ['white']
                else:
                    args['color'] = ['blue']  # Default
            except:
                args['color'] = ['blue']  # Fallback on error
        # termgraph expects color as a list with the color name
        elif default_color in ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']:
            args['color'] = [default_color]
        elif default_color == 'orange':
            args['color'] = ['red']  # Use red for orange
        elif default_color in ['purple', 'pink']:
            args['color'] = ['magenta']  # Use magenta for purple/pink
        elif default_color == 'gray':
            args['color'] = ['white']  # Use white for gray
        # If no match, default to blue
        elif default_color != 'default':
            args['color'] = ['blue']
    
    # Map color names to termgraph color codes
    color_map = {
        'red': 91,
        'green': 92,
        'yellow': 93,
        'blue': 94,
        'magenta': 95,
        'cyan': 96,
        'white': 97,
        'orange': 91,  # Use red for orange
        'purple': 95,  # Use magenta for purple
        'pink': 95,    # Use magenta for pink
        'gray': 90,
        'default': 0
    }
    
    # Set colors based on series or default
    if legend_labels:
        # Multi-series - use different colors
        colors = []
        for i, _ in enumerate(legend_labels):
            colors.append(color_map.get(get_color_for_series(i, len(legend_labels)), 94))
    else:
        # Single series - use specified color or default
        if default_color and default_color in color_map:
            colors = [color_map[default_color]]
        else:
            colors = [92]  # Default to green
    
    # Render the chart
    if chart_type == 'tg_calendar':
        # For calendar heatmap, we need a different approach
        # Convert x (dates) and y (values) to the format calendar_heatmap expects
        if not x_values or not y_values:
            print("No data for calendar heatmap")
            if return_string:
                output = string_buffer.getvalue()
                sys.stdout = old_stdout
                return output
            return None
            
        # Create a dictionary mapping dates to values
        date_dict = {}
        for i in range(len(x_values)):
            date_str = str(x_values[i])
            # Try to parse and format date properly for termgraph
            try:
                # Handle various date formats
                from datetime import datetime
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        dt = datetime.strptime(date_str.split('.')[0], fmt)
                        date_str = dt.strftime('%Y-%m-%d')
                        break
                    except:
                        continue
            except:
                pass  # Use original if parsing fails
            value = float(y_values[i])
            date_dict[date_str] = value
        
        # termgraph calendar_heatmap expects specific format:
        # - data: list of [value] lists
        # - labels: list of date strings
        # Sort by date to ensure proper ordering
        sorted_dates = sorted(date_dict.items())
        calendar_labels = [date for date, _ in sorted_dates]
        calendar_data = [[value] for _, value in sorted_dates]
        
        try:
            tg.calendar_heatmap(calendar_data, calendar_labels, args)
        except Exception as e:
            # Fallback to regular chart if calendar fails
            print(f"Calendar heatmap failed: {e}")
            print("Falling back to regular bar chart with dates")
            args['calendar'] = False
            tg.chart(colors, data, args, labels)
    else:
        tg.chart(colors, data, args, labels)
    
    # Print legend for multi-series
    if legend_labels:
        print("\nLegend:")
        for i, label in enumerate(legend_labels):
            color_code = colors[i % len(colors)]
            print(f"\033[{color_code}m▇▇ {label}\033[0m")
    
    # Return captured output if requested
    if return_string:
        output = string_buffer.getvalue()
        sys.stdout = old_stdout
        return output
    
    return None


def render_chart(chart_type: str, x_values: List, y_values: List,
                 color_values: Optional[List], config: Dict[str, Any],
                 default_color: Optional[str] = None, title: Optional[str] = None,
                 font: Optional[str] = None, results: Optional[List[Dict[str, Any]]] = None) -> None:
    """Render chart using plotext, termgraph, or map renderer based on chart type."""
    # Check if this is JSON output type
    if chart_type == 'json':
        import json
        # Clear terminal
        print('\033[2J\033[H', end='', flush=True)
        if title:
            print(f"# {title}\n")
        # Output formatted JSON of the results
        if results:
            print(json.dumps(results, indent=2, default=str))
        else:
            # Reconstruct from x/y/color if results not provided
            reconstructed = []
            for i in range(len(x_values) if x_values else 0):
                row = {}
                if x_values and i < len(x_values):
                    row['x'] = x_values[i]
                if y_values and i < len(y_values):
                    row['y'] = y_values[i]
                if color_values and i < len(color_values):
                    row['color'] = color_values[i]
                reconstructed.append(row)
            print(json.dumps(reconstructed, indent=2, default=str))
        return
    
    # Check if this is a map chart type
    map_types = ['map', 'map_points', 'map_density', 'map_clusters', 'map_heatmap', 'map_blocks', 'map_blocks_heatmap', 'map_braille_heatmap']
    if chart_type in map_types:
        render_map_chart(chart_type, x_values, y_values, color_values, title, results, config)
        return
    
    # Check if this is a pie chart  
    if chart_type == 'pie':
        from .pie_chart import extract_pie_data, render_pie_chart
        # If we have results, use them directly
        if results:
            values, labels = extract_pie_data(results)
            output = render_pie_chart(
                values, labels,
                title=title,
                use_braille=True,
                show_percentages=True,
                auto_size=True
            )
            print(output)
            return
        else:
            # Otherwise, construct from x_values and y_values
            # x_values = labels, y_values = values
            if x_values and y_values:
                output = render_pie_chart(
                    y_values, x_values,  # Note: reversed for pie (values, labels)
                    title=title,
                    use_braille=True,
                    show_percentages=True,
                    auto_size=True
                )
                print(output)
            else:
                print("No data to display")
        return
    
    # Check if this is a waffle chart
    if chart_type == 'waffle':
        # If we have results, use them directly
        if results:
            render_waffle_chart(results, title)
        else:
            # Otherwise, construct from x_values and y_values
            # x_values = labels, y_values = values
            if x_values and y_values:
                from .waffle_chart import render_waffle_chart
                # Debug: Check the data types
                # print(f"DEBUG: y_values type: {type(y_values)}, first few: {y_values[:5] if y_values else []}", file=sys.stderr)
                # print(f"DEBUG: x_values type: {type(x_values)}, first few: {x_values[:5] if x_values else []}", file=sys.stderr)
                output = render_waffle_chart(
                    y_values, x_values,  # Note: reversed for waffle (values, labels)
                    title=title,
                    show_percentages=True
                )
                print(output)
            else:
                print("No data to display")
        return
    
    # Check if this is a matrix heatmap
    if chart_type == 'matrix_heatmap':
        # If we have results, use them directly
        if results:
            render_matrix_heatmap_chart(results, title)
        else:
            # Otherwise, construct results from x_values, y_values, color_values
            # This happens when called from TUI
            if x_values and y_values:
                from .matrix_heatmap import render_matrix_heatmap
                output = render_matrix_heatmap(
                    x_values, y_values, color_values,
                    title=title,
                    show_values=True
                )
                print(output)
            else:
                print("No data to display")
        return
    
    # Check if this is a termgraph chart type
    termgraph_types = ['tg_bar', 'tg_hbar', 'tg_multi', 'tg_stacked', 'tg_histogram', 'tg_calendar']
    if chart_type in termgraph_types:
        render_termgraph(chart_type, x_values, y_values, color_values, title, default_color)
        return
    
    # Special handling for rich_table type
    if chart_type == 'rich_table':
        # For rich table, we need the full results, not just x/y/color
        if results:
            render_rich_table(results, title, default_color)
        else:
            # Fallback to reconstructing from x/y/color if results not provided
            reconstructed = []
            for i in range(len(x_values)):
                row = {'x': x_values[i], 'y': y_values[i]}
                if color_values and i < len(color_values):
                    row['color'] = color_values[i]
                reconstructed.append(row)
            render_rich_table(reconstructed, title, default_color)
        return

    # Special handling for figlet type
    if chart_type == 'figlet':
        # Use first value from results
        if y_values and len(y_values) > 0:
            value = y_values[0]
        elif x_values and len(x_values) > 0:
            value = x_values[0]
        else:
            value = "No Data"

        # Use specified font or determine based on value length
        if not font:
            font = "ansi_regular"
            # if len(str(value)) > 10:
            #     font = "small"
            # elif len(str(value)) > 15:
            #     font = "mini"

        render_figlet(format_value(value), title, default_color, font)
        return

    # Regular chart rendering
    # Use ANSI escape sequences instead of plt.clear_terminal() to preserve color state
    print('\033[2J\033[H', end='', flush=True)
    plt.clear_data()
    plt.clear_figure()

    chart_config = config.get("chart_defaults", {})

    if chart_config.get("theme"):
        plt.theme(chart_config["theme"])

    # Set all backgrounds to transparent to preserve terminal effects
    plt.canvas_color("default")     # Chart canvas background
    plt.axes_color("default")       # Axes area background
    plt.ticks_color("default")      # Tick marks area background

    width = chart_config.get("width") or plt.terminal_width()
    height = chart_config.get("height") or plt.terminal_height()

    plt.plotsize(width, height)

    # Set title if provided
    if title:
        plt.title(title)

    # For bar charts with colors where x equals color, we want individual colored bars
    if color_values and chart_type in ['bar', 'simple_bar'] and len(set(zip(x_values, color_values))) == len(x_values):
        # Each x value has its own color
        # Plot as a simple bar chart without individual colors (plotext limitation)
        # The legend will show via labels
        plt.bar(x_values, y_values)
        plt.show()
        return
    elif color_values and chart_type == 'bar':
        # For bar charts with color grouping, create a stacked bar chart
        groups = group_by_color(x_values, y_values, color_values)
        
        # Get all unique x values (maintaining order)
        unique_x = []
        seen = set()
        for x in x_values:
            if x not in seen:
                unique_x.append(x)
                seen.add(x)
        
        # Build the Y matrix for stacked bars
        Y = []
        labels = []
        colors = []
        
        for idx, (color_label, (x_group, y_group)) in enumerate(groups.items()):
            y_series = []
            for x in unique_x:
                # Find the y value for this x and color
                value = 0
                for i, xg in enumerate(x_group):
                    if xg == x:
                        value = y_group[i]
                        break
                y_series.append(value)
            Y.append(y_series)
            labels.append(color_label)
            colors.append(get_color_for_series(idx, len(groups)))
        
        # Create stacked bar chart
        plt.stacked_bar(unique_x, Y, labels=labels, color=colors, width=0.8)
        plt.show()
        return
    elif color_values:
        groups = group_by_color(x_values, y_values, color_values)
        group_items = list(groups.items())
        for idx, (label, (x_group, y_group)) in enumerate(group_items):
            series_color = get_color_for_series(idx, len(group_items))
            render_single_series(chart_type, x_group, y_group, label, chart_config, series_color)
    else:
        # Debug: Print default_color being passed
        # if default_color is not None:
        #     print(f"DEBUG: Passing default_color={repr(default_color)} to render_single_series", file=sys.stderr)
        render_single_series(chart_type, x_values, y_values, None, chart_config, default_color)

    plt.show()


def render_single_series(chart_type: str, x_values: List, y_values: List,
                         label: Optional[str], chart_config: Dict[str, Any],
                         color: Optional[str] = None) -> None:
    """Render a single data series based on chart type."""
    # Debug: Print color parameter
    # if color is not None:
    #     print(f"DEBUG: render_single_series called with color={repr(color)}", file=sys.stderr)
    chart_funcs = {
        'bar': plt.bar,
        'scatter': plt.scatter,
        'line': plt.plot,
        'braille': lambda x, y, **kwargs: plt.scatter(x, y, marker='braille', **kwargs),
        'histogram': lambda x, y, **kwargs: plt.hist(y, **kwargs),
        'candlestick': plt.candlestick,
        'box': plt.box,
        'simple_bar': plt.simple_bar,
        'simple_stacked_bar': plt.simple_stacked_bar,
        'multiple_bar': plt.multiple_bar,
        'stacked_bar': plt.stacked_bar,
        'rich_table': lambda x, y, **kwargs: None,  # Handled separately
    }

    if chart_type not in chart_funcs:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    # Define which chart types support which parameters
    supports_color = ['bar', 'line', 'scatter', 'histogram', 'braille', 'simple_bar']
    supports_label = ['bar', 'line', 'scatter', 'histogram', 'braille', 'candlestick']

    kwargs = {}
    if label and chart_type in supports_label:
        kwargs['label'] = label

    if color and chart_type in supports_color:
        # Convert hex colors to RGB tuples since plotext doesn't handle them properly
        if isinstance(color, str) and color.startswith('#'):
            try:
                color = hex_to_rgb(color)
            except:
                pass  # Fall back to original if conversion fails
        kwargs['color'] = color

    if chart_config.get("markers") and chart_type in ['scatter', 'line']:
        kwargs['marker'] = chart_config["markers"]

    if chart_type == 'histogram':
        chart_funcs[chart_type](None, y_values, **kwargs)
    else:
        chart_funcs[chart_type](x_values, y_values, **kwargs)


def render_pie_chart(results: Optional[List[Dict[str, Any]]], title: Optional[str] = None) -> None:
    """Render a pie chart from query results."""
    if not results:
        print("No data to display")
        return
    
    from .pie_chart import extract_pie_data, render_pie_chart
    
    values, labels = extract_pie_data(results)
    
    if not values:
        print("No data to display")
        return
    
    output = render_pie_chart(
        values, labels,
        title=title,
        radius=10,
        use_braille=True,
        show_percentages=True
    )
    print(output)


def render_waffle_chart(results: Optional[List[Dict[str, Any]]], title: Optional[str] = None) -> None:
    """Render a waffle chart from query results."""
    if not results:
        print("No data to display")
        return
    
    from .waffle_chart import extract_waffle_data, render_waffle_chart
    
    values, labels = extract_waffle_data(results)
    
    if not values:
        print("No data to display")
        return
    
    output = render_waffle_chart(
        values, labels,
        title=title,
        show_percentages=True
    )
    print(output)


def render_matrix_heatmap_chart(results: Optional[List[Dict[str, Any]]], title: Optional[str] = None) -> None:
    """Render a matrix heatmap from query results."""
    if not results:
        print("No data to display")
        return
    
    # Extract x, y, and value columns from results
    x_values, y_values, cell_values = extract_matrix_data(results)
    
    if not x_values or not y_values:
        print("Matrix heatmap requires at least two dimensions (x and y columns)")
        return
    
    # Get the column names for labels
    first_row = results[0]
    keys = list(first_row.keys())
    x_label = keys[0] if len(keys) > 0 else "X"
    y_label = keys[1] if len(keys) > 1 else "Y"
    
    # Render the matrix heatmap
    output = render_matrix_heatmap(
        x_values, y_values, cell_values,
        title=title,
        x_label=x_label,
        y_label=y_label,
        show_values=False  # Use color blocks by default
    )
    
    print(output)

def render_map_chart(chart_type: str, lons: List, lats: List,
                     color_values: Optional[List], title: Optional[str],
                     results: Optional[List[Dict[str, Any]]] = None,
                     config: Optional[Dict[str, Any]] = None) -> None:
    """Render geographic data as a map."""
    # Clear terminal using ANSI escape sequences
    print('\033[2J\033[H', end='', flush=True)
    
    # Determine map visualization type
    if chart_type == 'map_density':
        map_type = 'density'
    elif chart_type == 'map_clusters':
        map_type = 'clusters'
    elif chart_type == 'map_heatmap':
        map_type = 'heatmap'
    elif chart_type == 'map_blocks':
        map_type = 'blocks'
    elif chart_type == 'map_blocks_heatmap':
        map_type = 'blocks_heatmap'
    elif chart_type == 'map_braille_heatmap':
        map_type = 'braille_heatmap'
    else:
        map_type = 'points'
    
    # Get dimensions from config or terminal
    chart_config = config.get("chart_defaults", {}) if config else {}
    
    try:
        import os
        terminal_width = os.get_terminal_size().columns
        terminal_height = os.get_terminal_size().lines - 2  # Leave space for command prompt
    except:
        terminal_width = 80
        terminal_height = 24
    
    # Use config width/height if provided, otherwise use terminal size
    width = chart_config.get("width") or terminal_width
    height = chart_config.get("height") or terminal_height
    
    # Extract values if present (for heatmap/density)
    values = None
    if results and 'value' in results[0]:
        values = [float(row.get('value', 0)) for row in results]
    elif color_values and all(isinstance(v, (int, float)) for v in color_values):
        values = color_values
        color_values = None  # Use values instead of colors
    
    # Render the map
    map_output = render_map(
        lats=lats,
        lons=lons,
        values=values,
        colors=color_values if isinstance(color_values, list) and all(isinstance(c, str) for c in color_values) else None,
        width=width,
        height=height,
        title=title,
        map_type=map_type
    )
    
    print(map_output)


def parse_interval(interval: str) -> float:
    """Parse interval string to seconds (e.g., '5s', '1m', '0.5h')."""
    if not interval:
        return 0

    unit_multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
    }

    unit = interval[-1].lower()
    if unit not in unit_multipliers:
        try:
            return float(interval)
        except ValueError:
            raise ValueError(f"Invalid interval format: {interval}")

    try:
        value = float(interval[:-1])
        return value * unit_multipliers[unit]
    except ValueError:
        raise ValueError(f"Invalid interval format: {interval}")


def refresh_loop(query: str, chart_type: str, db_identifier: Any,
                 interval_seconds: float, config: Dict[str, Any],
                 default_color: Optional[str] = None, title: Optional[str] = None,
                 font: Optional[str] = None, json_data: Optional[List[Dict]] = None) -> None:
    """Main refresh loop for updating charts."""
    stop_event = threading.Event()

    def signal_handler():
        stop_event.set()

    import signal
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())

    # If we have JSON data, load it once before the loop
    json_conn = None
    if json_data is not None and db_identifier == ':memory:':
        json_conn = duckdb.connect(':memory:')
        if not load_json_to_duckdb(json_data, json_conn):
            print("Error: Failed to load JSON data into DuckDB")
            return

    try:
        while not stop_event.is_set():
            try:
                if json_conn:
                    # Use the pre-loaded JSON connection
                    result = json_conn.execute(query).fetchall()
                    columns = [desc[0] for desc in json_conn.description]
                    results = [dict(zip(columns, row)) for row in result]
                else:
                    results = execute_query(query, db_identifier, config)
                x_values, y_values, color_values = extract_chart_data(results)
                # Pass full results for rich_table
                render_chart(chart_type, x_values, y_values, color_values, config,
                             default_color, title, font, results=results)

                if interval_seconds <= 0:
                    break

                stop_event.wait(interval_seconds)
            except Exception as e:
                print('\033[2J\033[H', end='', flush=True)
                print(f"Error: {e}")
                if interval_seconds <= 0:
                    break
                stop_event.wait(interval_seconds)
    except KeyboardInterrupt:
        print('\033[2J\033[H', end='', flush=True)
        print("\nExiting...")
    finally:
        if json_conn:
            json_conn.close()


class CheshireCommand(click.Command):
    """Custom command class that displays logo in help."""
    def format_help(self, ctx, formatter):
        """Format help with logo."""
        # Display logo at the top
        display_logo()
        # Then show normal help
        super().format_help(ctx, formatter)


@click.command(cls=CheshireCommand)
@click.argument('query', required=False)
@click.argument('chart_type', default='bar')
@click.argument('interval', default='0')
@click.option('--db', '-d', help='Database path or name from config')
@click.option('--database', '-D', help='Named database from config file')
@click.option('--config', '-c', default='cheshire.yaml', help='Config file path')
@click.option('--color', help='Default chart color (e.g., "red", "blue", "#FF5733")')
@click.option('--theme', help='Chart theme (e.g., "matrix", "dark", "clear", "pro")')
@click.option('--title', help='Chart title')
@click.option('--font', help='Font for figlet chart type (e.g., "ansi_regular", "colossal", "big")')
@click.option('--list-databases', is_flag=True, help='List available databases from config')
@click.option('--sniff', is_flag=True, help='Analyze database and generate chart recommendations')
@click.option('--csv', help='CSV file to analyze with --sniff or query directly')
@click.option('--tsv', help='TSV file to analyze with --sniff or query directly')
@click.option('--parquet', help='Parquet file or folder to analyze with --sniff or query directly')
@click.option('--json-input', is_flag=True, help='Read JSON array from stdin and load as table "data"')
@click.option('--width', help='Chart width in characters (e.g., 60) or percentage of terminal (e.g., "80%")')
@click.option('--height', help='Chart height in lines (e.g., 20) or percentage of terminal (e.g., "50%")')
@click.option('--version', is_flag=True, is_eager=True, expose_value=False, callback=lambda ctx, param, value: (display_logo(), click.echo("cheshire, version 0.1.0"), ctx.exit()) if value else None, help='Show the version and exit.')
def main(query: Optional[str], chart_type: str, interval: str, db: Optional[str], database: Optional[str], config: str, color: Optional[str], theme: Optional[str], title: Optional[str], font: Optional[str], list_databases: bool, sniff: bool, csv: Optional[str], tsv: Optional[str], parquet: Optional[str], json_input: bool, width: Optional[str], height: Optional[str]):
    """Terminal-based SQL visualization tool.

    QUERY: SQL query to execute (must select 'x', 'y', and optionally 'color' columns)
    CHART_TYPE: Type of chart to render (bar, line, scatter, json, etc.)
    INTERVAL: Refresh interval (e.g., '5s', '1m', '0.5h', or 0 for no refresh)

    Chart types include: bar, line, scatter, pie, waffle, map, rich_table, figlet, json
    
    If no query is provided, launches an interactive TUI mode.
    
    JSON Input: Pipe JSON data directly or use --json-input flag:
      echo '[{"name": "Alice", "score": 90}, {"name": "Bob", "score": 85}]' | cheshire "SELECT name as x, score as y FROM data" bar
      cat data.json | cheshire "SELECT * FROM data WHERE score > 80" json --json-input
    """
    config_data = load_config(config)

    # Handle --list-databases flag first (before TUI check)
    if list_databases:
        if 'databases' in config_data:
            print("Available databases:")
            for name, db_config in config_data['databases'].items():
                db_type = db_config.get('type', 'unknown')
                if db_type == 'duckdb':
                    path = db_config.get('path', '')
                    print(f"  {name:<20} ({db_type}) - {path}")
                elif db_type == 'osquery':
                    print(f"  {name:<20} ({db_type}) - System stats via osqueryi")
                else:
                    print(f"  {name:<20} ({db_type})")
        else:
            print("No databases configured")
        return

    # Handle --sniff flag for database analysis or file analysis
    if sniff or (csv and not query) or (tsv and not query) or (parquet and not query):
        # Check if analyzing CSV/TSV/Parquet file
        if csv or tsv or parquet:
            if parquet:
                file_path = parquet
                file_type = 'parquet'
                # For Parquet, could be file or folder
                if not Path(file_path).exists():
                    print(f"Error: Path not found: {file_path}")
                    sys.exit(1)
                print(f"🔍 Analyzing Parquet: {file_path}")
                from .database_analyzer import analyze_parquet_file
                analyze_parquet_file(file_path)
            else:
                file_path = csv or tsv
                file_type = 'csv' if csv else 'tsv'
                
                # Check if file exists
                if not Path(file_path).exists():
                    print(f"Error: File not found: {file_path}")
                    sys.exit(1)
                    
                print(f"🔍 Analyzing {file_type.upper()} file: {file_path}")
                from .database_analyzer import analyze_csv_tsv_file
                analyze_csv_tsv_file(file_path, file_type)
            return
            
        # Need a database to analyze
        elif database:
            # Named database from config
            if 'databases' in config_data and database in config_data['databases']:
                db_config = config_data['databases'][database]
                db_type = db_config.get('type', 'duckdb')
                print(f"🔍 Analyzing database: {database}")
                from .database_analyzer import analyze_database
                analyze_database(db_config, db_type, db_name=database)
            else:
                print(f"Error: Database '{database}' not found in config")
                sys.exit(1)
        elif db:
            # Database path
            if Path(db).exists() or db == ':memory:':
                # Determine database type from file extension
                db_type = 'duckdb'  # Default
                if db.endswith('.db') or db.endswith('.sqlite'):
                    db_type = 'sqlite'
                print(f"🔍 Analyzing database: {db}")
                from .database_analyzer import analyze_database
                analyze_database(db, db_type)
            else:
                print(f"Error: Database file not found: {db}")
                sys.exit(1)
        else:
            # Try default database
            default_db_name = config_data.get('default_database', 'default')
            if 'databases' in config_data and default_db_name in config_data['databases']:
                db_config = config_data['databases'][default_db_name]
                db_type = db_config.get('type', 'duckdb')
                print(f"🔍 Analyzing default database: {default_db_name}")
                from .database_analyzer import analyze_database
                analyze_database(db_config, db_type, db_name=default_db_name)
            else:
                print("Error: No database specified. Use --db or --database option.")
                sys.exit(1)
        return

    # Check for JSON input from stdin (either with --json-input flag or auto-detect)
    json_data = None
    json_loaded = False
    if json_input or not sys.stdin.isatty():
        json_data = detect_and_load_json_stdin()
        if json_data:
            json_loaded = True
            # If no query provided, set a default one
            if not query:
                query = "SELECT * FROM data LIMIT 100"
    
    # Launch TUI mode if no query provided (and no JSON input)
    if not query and not json_loaded:
        from .tui_mode import main as tui_main
        tui_main()
        return

    # Handle CSV/TSV/Parquet files for direct querying
    if csv or tsv or parquet:
        if parquet:
            file_path = parquet
            
            # Check if path exists
            if not Path(file_path).exists():
                print(f"Error: Path not found: {file_path}")
                sys.exit(1)
            
            # Get absolute path
            abs_file_path = str(Path(file_path).resolve())
            
            # Determine if it's a file or directory
            if Path(abs_file_path).is_dir():
                # Directory - use glob pattern for all parquet files
                from_clause = f"read_parquet('{abs_file_path}/*.parquet')"
            else:
                # Single file
                from_clause = f"read_parquet('{abs_file_path}')"
        else:
            file_path = csv or tsv
            file_type = 'csv' if csv else 'tsv'
            
            # Check if file exists
            if not Path(file_path).exists():
                print(f"Error: File not found: {file_path}")
                sys.exit(1)
            
            # Get absolute path for the file
            abs_file_path = str(Path(file_path).resolve())
            
            # Modify query to read from CSV/TSV file
            table_name = Path(file_path).stem  # Use filename without extension as table name
            if file_type == 'csv':
                from_clause = f"read_csv_auto('{abs_file_path}')"
            else:
                from_clause = f"read_csv_auto('{abs_file_path}', delim='\\t')"
        
        # Replace table references in query with the read_csv_auto function
        # Simple replacement - assumes query uses the table name or 'data'
        if query:
            # If query contains FROM keyword, replace the table reference
            import re
            # This is a simple approach - might need refinement for complex queries
            query = re.sub(r'\bFROM\s+(\w+)', f'FROM {from_clause}', query, flags=re.IGNORECASE)
            # If no FROM clause found, assume they want to query the file directly
            if 'from' not in query.lower():
                query = f"SELECT * FROM {from_clause} LIMIT 100"
        
        # Use in-memory DuckDB for CSV/TSV queries
        db_identifier = ':memory:'
    # Handle JSON input data
    elif json_loaded:
        # Use in-memory DuckDB for JSON data
        db_identifier = ':memory:'
    # Determine which database to use
    elif database:
        # Explicit database name from --database flag
        db_identifier = database
    elif db:
        # Database path or name from --db flag
        db_identifier = db
    else:
        # Use default database from config
        default_db_name = config_data.get('default_database', 'default')
        if 'databases' in config_data and default_db_name in config_data['databases']:
            db_identifier = default_db_name
        else:
            # Fallback to in-memory database
            db_identifier = ':memory:'

    # Override theme if specified on command line
    if theme:
        config_data.setdefault("chart_defaults", {})["theme"] = theme
    
    # Process width/height arguments
    if width or height:
        import os
        try:
            terminal_width = os.get_terminal_size().columns
            terminal_height = os.get_terminal_size().lines
        except:
            terminal_width = 80
            terminal_height = 24
        
        # Parse and apply width
        if width:
            parsed_width = parse_dimension(width, terminal_width)
            if parsed_width:
                config_data.setdefault("chart_defaults", {})["width"] = parsed_width
        
        # Parse and apply height
        if height:
            parsed_height = parse_dimension(height, terminal_height)
            if parsed_height:
                config_data.setdefault("chart_defaults", {})["height"] = parsed_height

    # Only check for file existence if using a file-based database
    if isinstance(db_identifier, str) and db_identifier not in config_data.get('databases', {}):
        # It's a file path, not a named database
        if db_identifier != ':memory:' and db_identifier:
            # Check if query is reading from external sources like parquet files
            query_lower = query.lower()
            is_external_read = any(keyword in query_lower for keyword in [
                'read_parquet', 'read_csv', 'read_json', 'from parquet', 'from csv', 'from json'
            ])

            # Only check file existence if it's a regular database file and not reading external data
            if not is_external_read and not Path(db_identifier).exists():
                print(f"Error: Database file not found: {db_identifier}")
                sys.exit(1)

    # Process color argument
    default_color = None
    if color:
        # print(f"DEBUG: Processing color argument: {repr(color)}", file=sys.stderr)
        if color.startswith('#'):
            # Convert hex to RGB tuple - plotext doesn't handle hex properly
            try:
                default_color = hex_to_rgb(color)
            except:
                print(f"Warning: Invalid hex color {color}, using default")
                default_color = None
        elif color.isdigit():
            # Integer color code (0-255)
            color_code = int(color)
            if 0 <= color_code <= 255:
                default_color = color_code
            else:
                print(f"Warning: Color code must be 0-255, got {color_code}")
                default_color = None
        else:
            # Named color or 'default'
            default_color = color

    try:
        interval_seconds = parse_interval(interval)
        refresh_loop(query, chart_type, db_identifier, interval_seconds, config_data, default_color, title, font, json_data=json_data if json_loaded else None)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
