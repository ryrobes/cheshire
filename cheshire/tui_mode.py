#!/usr/bin/env python3

import os
import subprocess
import tempfile
import io
import sys
import re
import json
import glob
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import redirect_stdout

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, TextArea, Select, Static, Button, 
    Label, RichLog, Input, Tree, TabbedContent, TabPane
)
from textual.reactive import reactive
from textual.css.query import NoMatches
from rich.ansi import AnsiDecoder

import duckdb
import plotext as plt
from .main import (
    load_config, execute_query, extract_chart_data, 
    render_chart, parse_interval, render_single_series,
    group_by_color, get_color_for_series, hex_to_rgb,
    render_termgraph
)


class ChartPreview(RichLog):
    """Widget to display chart preview or status messages with ANSI support."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.markup = True  # Enable markup for Rich formatting
        self._ansi_decoder = AnsiDecoder()  # For rendering ANSI escape sequences
        self.write("Chart preview will appear here after running a query")
    
    def write_ansi(self, content: str) -> None:
        """Write content with ANSI escape sequences properly rendered."""
        # Use Rich's AnsiDecoder to convert ANSI codes to Rich Text
        for line in self._ansi_decoder.decode(content):
            self.write(line)


class cheshireTUI(App):
    """Interactive TUI for cheshire."""
    
    # Initialize class variables
    databases = {'default': {'type': 'duckdb', 'path': ':memory:'}}
    default_database = 'default'
    db_path = ':memory:'
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        height: 80%;
    }
    
    #left-column {
        width: 60%;
        overflow: hidden;
    }
    
    #sql-container {
        height: 35%;
        padding: 1;
    }
    
    #sql-input {
        height: 100%;
        border: solid $primary;
    }
    
    #chart-container {
        height: 65%;
        padding: 1;
        border: solid $secondary;
    }
    
    #chart-preview {
        width: 100%;
        height: 100%;
        overflow: hidden;
    }
    
    RichLog {
        background: $panel;
        padding: 0;
    }
    
    #right-panel {
        width: 40%;
        border: solid $accent;
        overflow: hidden;
    }
    
    #schema-tree {
        height: 35;  /* Fixed height that should fit in the panel */
        width: 100%;
        overflow-y: scroll;
        overflow-x: hidden;
    }
    
    #suggestions-tree {
        height: 35;  /* Fixed height that should fit in the panel */
        width: 100%;
        overflow-y: scroll;
        overflow-x: auto;  /* Allow horizontal scroll for nested items */
    }
    
    Tree {
        background: $panel;
        height: 100%;
    }
    
    TabbedContent {
        height: 100%;
    }
    
    TabPane {
        padding: 1;
    }
    
    #command-container {
        height: 20%;
        padding: 1;
        border: solid $accent;
    }
    
    #command-row {
        height: 100%;
    }
    
    .command-box {
        width: 1fr;
        padding: 0 1;
        border-right: solid $secondary;
    }
    
    .command-box:last-child {
        border-right: none;
    }
    
    #command-display, #command-display-double, #command-display-single {
        width: 100%;
        height: 1fr;
        overflow: scroll;
        margin-bottom: 1;
    }
    
    #run-button {
        dock: bottom;
        width: 100%;
        margin-top: 1;
    }
    
    .copy-btn {
        width: 100%;
        height: 3;
    }
    
    #custom-db-row {
        display: none;
        height: 3;
        margin-top: 1;
    }
    
    #custom-db-row.visible {
        display: block;
    }
    
    #db-selector {
        width: 100%;
        margin-bottom: 0;
    }
    
    #browse-button {
        width: 10;
        margin-left: 1;
    }
    
    #db-input {
        width: 1fr;
    }
    
    .db-row {
        height: 3;
        margin-bottom: 1;
    }
    
    #chart-selector {
        width: 100%;
        margin: 1 0;
    }
    
    #color-selector {
        width: 60%;
        margin-right: 1;
    }
    
    Select {
        width: 100%;
    }
    
    SelectOverlay {
        layer: overlay;
        constrain: inside;
        max-height: 10;
    }
    
    #hex-input {
        width: 40%;
        display: none;
    }
    
    #hex-input.visible {
        display: block;
    }
    
    #interval-input {
        width: 100%;
        margin: 1 0;
    }
    
    #title-input {
        width: 100%;
        margin: 1 0;
    }
    
    #font-input {
        width: 100%;
        margin: 1 0;
    }
    
    #controls-container Label {
        margin-top: 1;
        margin-bottom: 0;
    }
    
    #controls-container Input {
        margin-bottom: 1;
    }
    
    #controls-container Select {
        margin-bottom: 1;
    }
    
    .control-row {
        height: auto;
        align: center middle;
    }
    
    Label {
        margin: 1;
        width: auto;
    }
    """
    
    BINDINGS = [
        ("ctrl+r", "run_query", "Run Query"),
        ("ctrl+c", "copy_command", "Copy Raw Command"),
        ("ctrl+d", "copy_double", "Copy Double-Quoted"),
        ("ctrl+s", "copy_single", "Copy Single-Quoted"),
        ("ctrl+q", "quit", "Quit"),
    ]
    
    def __init__(self):
        super().__init__()
        self.config = load_config()
        
        # Load databases from config
        if 'databases' in self.config:
            self.databases = self.config['databases']
            self.default_database = self.config.get('default_database', 'default')
        else:
            # Fallback for old config format or no config
            self.databases = {'default': {'type': 'duckdb', 'path': ':memory:'}}
            self.default_database = 'default'
            
            # Try to convert old format
            if 'database' in self.config:
                old_db_path = self.config['database'].get('default', ':memory:')
                self.databases = {'default': {'type': 'duckdb', 'path': old_db_path}}
        
        # Set db_path for backward compatibility
        if self.default_database in self.databases:
            db_config = self.databases[self.default_database]
            if db_config.get('type') == 'duckdb':
                self.db_path = db_config.get('path', ':memory:')
            else:
                self.db_path = self.default_database
        else:
            self.db_path = ':memory:'
        
        # If no example database exists in config, try to find one
        if 'example' not in self.databases and Path('example.duckdb').exists():
            self.databases['example'] = {'type': 'duckdb', 'path': 'example.duckdb'}
            # Switch to example if default is just memory
            if (self.default_database == 'default' and 
                self.databases.get('default', {}).get('path') == ':memory:'):
                self.default_database = 'example'
                self.db_path = 'example.duckdb'
        
        self.last_command = ""
        
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)
        
        with Vertical():
            # Main container with left column (SQL + Chart) and right column (controls)
            with Horizontal(id="main-container"):
                # Left column: SQL editor and chart
                with Vertical(id="left-column"):
                    # SQL Query Input Section
                    with Container(id="sql-container"):
                        yield Label("SQL Query (must return columns: x, y, and optionally color)")
                        # Set default query based on whether we have example.duckdb
                        default_query = "SHOW TABLES;"
                        if self.db_path == "example.duckdb" or self.db_path.endswith("example.duckdb"):
                            # Use strftime for plotext-compatible date format
                            default_query = """SELECT 
    strftime('%d/%m/%Y', date) as x, 
    SUM(sales) as y,
    product as color
FROM sales_table 
GROUP BY date, product 
ORDER BY date"""
                        yield TextArea(
                            default_query,
                            id="sql-input",
                            language="sql"
                        )
                    
                    # Chart Preview Section
                    with Container(id="chart-container"):
                        yield ChartPreview(id="chart-preview")
                
                # Right column: Tabbed interface
                with TabbedContent(initial="controls-tab", id="right-panel"):
                    with TabPane("Controls", id="controls-tab"):
                        yield Label("Database:")
                        # Create database dropdown options
                        db_options = []
                        databases = getattr(self, 'databases', {'default': {'type': 'duckdb', 'path': ':memory:'}})
                        for name, db_config in databases.items():
                            db_type = db_config.get('type', 'unknown')
                            if db_type == 'duckdb':
                                path = db_config.get('path', '')
                                label = f"{name} ({db_type}: {path})"
                            else:
                                label = f"{name} ({db_type})"
                            db_options.append((label, name))
                        
                        # Add option to use custom path
                        db_options.append(("Custom path...", "__custom__"))
                        
                        # Find current selection
                        current_selection = getattr(self, 'default_database', 'default')
                        if hasattr(self, 'db_path') and self.db_path and self.db_path not in [db.get('path') for db in databases.values()]:
                            current_selection = "__custom__"
                        
                        yield Select(
                            db_options,
                            id="db-selector",
                            value=current_selection,
                            allow_blank=False
                        )
                        
                        # Custom path input (initially hidden)
                        with Horizontal(classes="db-row", id="custom-db-row"):
                            yield Input(value=self.db_path if current_selection == "__custom__" else "", 
                                      id="db-input", placeholder="Path to database file")
                            yield Button("Browse", id="browse-button")
                        
                        yield Label("Chart Type:")
                        chart_types = [
                            ("Bar Chart", "bar"),
                            ("Line Chart", "line"),
                            ("Scatter Plot", "scatter"),
                            ("Histogram", "histogram"),
                            ("Box Plot", "box"),
                            ("Braille Scatter", "braille"),
                            ("Large Text Display", "figlet"),
                            ("Rich Data Table", "rich_table"),
                            ("Simple Bar", "simple_bar"),
                            ("Multiple Bar", "multiple_bar"),
                            ("Stacked Bar", "stacked_bar"),
                            ("Termgraph Bar", "tg_bar"),
                            ("Termgraph Multi-Bar", "tg_multi"),
                            ("Termgraph Stacked", "tg_stacked"),
                            ("Termgraph Histogram", "tg_histogram"),
                            ("Termgraph Calendar", "tg_calendar"),
                            ("Map - Points (Braille)", "map_points"),
                            ("Map - Points (Blocks)", "map_blocks"),
                            ("Map - Density", "map_density"),
                            ("Map - Clusters", "map_clusters"),
                            ("Map - Heatmap", "map_heatmap"),
                            ("Map - True Color Heatmap", "map_blocks_heatmap"),
                            ("Map - Braille Heatmap", "map_braille_heatmap"),
                            ("Matrix Heatmap", "matrix_heatmap"),
                            ("Waffle Chart", "waffle"),
                            ("Pie Chart", "pie"),
                        ]
                        yield Select(
                            chart_types,
                            id="chart-selector",
                            allow_blank=False
                        )
                        
                        yield Label("Interval:")
                        yield Input(value="0", id="interval-input", placeholder="e.g., 5s, 1m, 0")
                        
                        yield Label("Title:")
                        yield Input(value="", id="title-input", placeholder="Optional chart title")
                        
                        yield Label("Color: [dim](appears in CLI output only)[/dim]")
                        with Horizontal():
                            color_options = [
                                ("Terminal Default", "default"),
                                ("Red", "red"),
                                ("Green", "green"),
                                ("Blue", "blue"),
                                ("Yellow", "yellow"),
                                ("Cyan", "cyan"),
                                ("Magenta", "magenta"),
                                ("Orange", "orange"),
                                ("Purple", "purple"),
                                ("Pink", "pink"),
                                ("Gray", "gray"),
                                ("White", "white"),
                                ("Custom Hex/Code", "custom")
                            ]
                            yield Select(
                                color_options,
                                id="color-selector",
                                allow_blank=False
                            )
                            yield Input(value="#00FF00", id="hex-input", placeholder="#RRGGBB or 0-255")
                        
                        # Font selection for figlet - initially hidden
                        yield Label("Font:", id="font-label", classes="figlet-only")
                        yield Input(value="", id="font-input", placeholder="e.g., ansi_regular, colossal, big", classes="figlet-only")
                        
                        yield Button("Run Query", variant="primary", id="run-button")
                    
                    # Schema Explorer Tab
                    with TabPane("Schema", id="schema-tab"):
                        yield Label("[bold]Database Schema[/bold] (click to insert)")
                        yield Tree("📚 Database Schema", id="schema-tree")
                    
                    # Suggestions Tab
                    with TabPane("Suggestions", id="suggestions-tab"):
                        yield Label("[bold]Chart Recommendations[/bold] (click to use)")
                        yield Tree("💡 Suggestions", id="suggestions-tree")
            
            # Command Echo Section
            with Container(id="command-container"):
                yield Label("CLI Commands:")
                with Horizontal(id="command-row"):
                    # Original command
                    with Vertical(classes="command-box"):
                        yield Label("[bold]Raw Command:[/bold]")
                        yield Static("[dim]Run a query to generate commands[/dim]", id="command-display")
                        yield Button("Copy", variant="success", id="copy-button", classes="copy-btn")
                    
                    # Double-quoted version
                    with Vertical(classes="command-box"):
                        yield Label('[bold]For Double Quotes ("wrapped"):[/bold]')
                        yield Static("[dim]...[/dim]", id="command-display-double")
                        yield Button("Copy", variant="success", id="copy-button-double", classes="copy-btn")
                    
                    # Single-quoted version
                    with Vertical(classes="command-box"):
                        yield Label("[bold]For Single Quotes ('wrapped'):[/bold]")
                        yield Static("[dim]...[/dim]", id="command-display-single")
                        yield Button("Copy", variant="success", id="copy-button-single", classes="copy-btn")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when the app is mounted."""
        # Load initial schema after a short delay to ensure widgets are ready
        self.set_timer(0.5, self.load_database_schema)
        
        # Also try to load suggestions if any analysis files exist
        self.set_timer(0.7, self._check_and_load_suggestions)
    
    def _check_and_load_suggestions(self) -> None:
        """Check if analysis files exist and notify user."""
        analysis_files = glob.glob('.cheshire_analysis_*.json')
        if analysis_files:
            self.notify(f"Found {len(analysis_files)} analysis file(s). Check Suggestions tab!", severity="info")
    
    def action_run_query(self) -> None:
        """Run the SQL query and display the chart."""
        self.run_query()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "run-button":
            self.run_query()
        elif event.button.id == "copy-button":
            self.copy_command()
        elif event.button.id == "copy-button-double":
            self.copy_command(quote_style="double")
        elif event.button.id == "copy-button-single":
            self.copy_command(quote_style="single")
        elif event.button.id == "browse-button":
            self.browse_database()
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if event.select.id == "color-selector":
            hex_input = self.query_one("#hex-input", Input)
            if event.value == "custom":
                hex_input.styles.display = "block"
            else:
                hex_input.styles.display = "none"
        elif event.select.id == "chart-selector":
            # Show/hide font input based on chart type
            font_label = self.query_one("#font-label", Label)
            font_input = self.query_one("#font-input", Input)
            if event.value == "figlet":
                font_label.add_class("visible")
                font_input.add_class("visible")
            else:
                font_label.remove_class("visible")
                font_input.remove_class("visible")
        elif event.select.id == "db-selector":
            # Handle custom database selection UI
            custom_row = self.query_one("#custom-db-row")
            if event.value == "__custom__":
                custom_row.add_class("visible")
            else:
                custom_row.remove_class("visible")
            
            # When database changes, update schema
            if event.value:
                self.load_database_schema()
    
    def build_cli_command(self) -> str:
        """Build the CLI command from current settings."""
        sql_input = self.query_one("#sql-input", TextArea)
        chart_selector = self.query_one("#chart-selector", Select)
        interval_input = self.query_one("#interval-input", Input)
        title_input = self.query_one("#title-input", Input)
        db_selector = self.query_one("#db-selector", Select)
        db_input = self.query_one("#db-input", Input)
        color_selector = self.query_one("#color-selector", Select)
        hex_input = self.query_one("#hex-input", Input)
        font_input = self.query_one("#font-input", Input)
        
        # Remove newlines and extra spaces from query
        query = sql_input.text.strip().replace("\n", " ").replace("'", "'\\''")  
        # Collapse multiple spaces into single space
        import re
        query = re.sub(r'\s+', ' ', query)
        chart_type = chart_selector.value
        interval = interval_input.value.strip() or "0"
        title = title_input.value.strip()
        
        # Get database selection
        db_selection = db_selector.value
        if db_selection == "__custom__":
            db_path = db_input.value.strip()
        else:
            # Use named database
            db_path = db_selection
        
        cmd = f"cheshire '{query}' {chart_type} {interval}"
        
        if title:
            cmd += f" --title '{title}'"
            
        # Add color option (keep as hex/string for CLI)
        color_value = color_selector.value
        if color_value == "custom":
            color = hex_input.value.strip()
        elif color_value != "default":
            color = color_value
        else:
            color = None
            
        if color:
            cmd += f" --color '{color}'"
            
        # Add font option for figlet charts
        if chart_type == 'figlet':
            font = font_input.value.strip()
            if font:
                cmd += f" --font '{font}'"
            
        # Specify database
        if db_selection == "__custom__" or db_selection not in self.databases:
            # Use --db for file paths
            cmd += f" --db '{db_path}'"
        else:
            # Use --database for named databases
            cmd += f" --database '{db_path}'"
            
        return cmd
    
    def escape_for_double_quotes(self, cmd: str) -> str:
        """Escape command for use within double quotes."""
        # Escape backslashes first, then double quotes, then dollar signs
        escaped = cmd.replace('\\', '\\\\')
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace('$', '\\$')
        escaped = escaped.replace('`', '\\`')
        return escaped
    
    def escape_for_single_quotes(self, cmd: str) -> str:
        """Escape command for use within single quotes."""
        # In single quotes, only single quotes need escaping
        # Replace ' with '\'' (end quote, escaped quote, start quote)
        return cmd.replace("'", "'\\''")
    
    def run_query(self) -> None:
        """Execute the query and display results."""
        try:
            # Get inputs
            sql_input = self.query_one("#sql-input", TextArea)
            chart_selector = self.query_one("#chart-selector", Select)
            interval_input = self.query_one("#interval-input", Input)
            title_input = self.query_one("#title-input", Input)
            db_selector = self.query_one("#db-selector", Select)
            db_input = self.query_one("#db-input", Input)
            color_selector = self.query_one("#color-selector", Select)
            hex_input = self.query_one("#hex-input", Input)
            
            query = sql_input.text.strip()
            chart_type = chart_selector.value
            interval = interval_input.value.strip() or "0"
            title = title_input.value.strip()
            
            # Get database selection
            db_selection = db_selector.value
            if db_selection == "__custom__":
                db_path = db_input.value.strip()
                db_identifier = db_path
            else:
                # Use named database config
                db_identifier = self.databases.get(db_selection, db_selection)
                db_path = db_selection  # For display purposes
            
            # Get color selection
            color_value = color_selector.value
            if color_value == "custom":
                custom_color = hex_input.value.strip()
                if custom_color.startswith('#'):
                    # Convert hex to RGB tuple for plotext
                    try:
                        hex_color = custom_color.lstrip('#')
                        default_color = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                    except:
                        self.notify(f"Invalid hex color: {custom_color}")
                        default_color = None
                elif custom_color.isdigit():
                    # Integer color code (0-255)
                    color_code = int(custom_color)
                    if 0 <= color_code <= 255:
                        default_color = color_code
                    else:
                        self.notify(f"Color code must be 0-255, got: {color_code}")
                        default_color = None
                else:
                    # Try as a color name
                    default_color = custom_color
            elif color_value == "default":
                # Use 'default' to get terminal default color
                default_color = "default"
            else:
                default_color = color_value
            
            if not query:
                self.update_preview("Error: Please enter a SQL query")
                return
                
            if not db_path:
                self.update_preview("Error: Please specify a database file")
                return
                
            # Check database validity
            if db_selection == "__custom__":
                # Check if database file exists (only for file paths)
                if db_path and db_path != ':memory:':
                    # Check if query is reading from external sources
                    query_lower = query.lower()
                    is_external_read = any(keyword in query_lower for keyword in [
                        'read_parquet', 'read_csv', 'read_json', 'from parquet', 'from csv', 'from json'
                    ])
                    
                    # Only check file existence if it's a regular database file and not reading external data
                    if not is_external_read and not Path(db_path).exists():
                        self.update_preview(f"Error: Database file not found: {db_path}")
                        return
            
            # Build and display CLI commands
            self.last_command = self.build_cli_command()
            
            # Update raw command display
            command_display = self.query_one("#command-display", Static)
            command_display.update(f"[bold cyan]{self.last_command}[/bold cyan]")
            
            # Update double-quoted version
            command_display_double = self.query_one("#command-display-double", Static)
            escaped_double = self.escape_for_double_quotes(self.last_command)
            command_display_double.update(f"[bold green]{escaped_double}[/bold green]")
            
            # Update single-quoted version
            command_display_single = self.query_one("#command-display-single", Static)
            escaped_single = self.escape_for_single_quotes(self.last_command)
            command_display_single.update(f"[bold yellow]{escaped_single}[/bold yellow]")
            
            # Execute query with the selected database
            results = execute_query(query, db_identifier, self.config)
            if not results:
                self.update_preview("No results returned from query")
                return
            
            # Extract data
            x_values, y_values, color_values = extract_chart_data(results)
            
            # For figlet type, show large text
            if chart_type == "figlet":
                # Get font input
                font_input = self.query_one("#font-input", Input)
                font = font_input.value.strip() or None
                
                if y_values and len(y_values) > 0:
                    value = str(y_values[0])
                elif x_values and len(x_values) > 0:
                    value = str(x_values[0])
                else:
                    value = "No Data"
                
                # Create ASCII art preview with specified font
                import pyfiglet
                
                # Use specified font or fall back to default
                if font:
                    try:
                        figlet_text = pyfiglet.figlet_format(value, font=font)
                    except pyfiglet.FontNotFound:
                        # Fall back to small font if specified font not found
                        figlet_text = pyfiglet.figlet_format(value, font="small")
                        self.notify(f"Font '{font}' not found, using 'small' instead", severity="warning")
                else:
                    # Default font selection based on value length
                    if len(str(value)) > 10:
                        font = "small"
                    elif len(str(value)) > 15:
                        font = "mini"
                    else:
                        font = "colossal"
                    figlet_text = pyfiglet.figlet_format(value, font=font)
                
                # Apply color if specified
                color_text = figlet_text
                if default_color and default_color != "default":
                    # Map color names to Rich color codes
                    color_map = {
                        'red': 'red',
                        'green': 'green',
                        'yellow': 'yellow',
                        'blue': 'blue',
                        'magenta': 'magenta',
                        'cyan': 'cyan',
                        'white': 'white',
                        'orange': 'orange',
                        'purple': 'purple',
                        'pink': 'pink',
                        'gray': 'gray'
                    }
                    
                    # Handle RGB tuples (from hex conversion)
                    if isinstance(default_color, tuple) and len(default_color) == 3:
                        r, g, b = default_color
                        color_text = f"[rgb({r},{g},{b})]{figlet_text}[/rgb({r},{g},{b})]"
                    elif default_color in color_map:
                        rich_color = color_map[default_color]
                        color_text = f"[{rich_color}]{figlet_text}[/{rich_color}]"
                    else:
                        color_text = f"[bold]{figlet_text}[/bold]"
                else:
                    color_text = f"[bold]{figlet_text}[/bold]"
                
                if title:
                    preview_text = f"[bold cyan]{title}[/bold cyan]\n\n{color_text}"
                else:
                    preview_text = color_text
                
                self.update_preview(preview_text)
            elif chart_type == "rich_table":
                # For Rich table type, create a text preview with all columns
                preview_text = self._create_rich_table_preview(
                    results, title, default_color
                )
                # Rich tables contain ANSI codes, so treat as chart for proper rendering
                self.update_preview(preview_text, is_chart=True)
            else:
                # Check if this is a termgraph chart
                # Check if this is a map chart
                map_types = ['map', 'map_points', 'map_blocks', 'map_density', 'map_clusters', 'map_heatmap']
                if chart_type in map_types:
                    # Render map chart
                    try:
                        from .map_renderer import render_map
                        # Get chart container size for optimal resolution
                        try:
                            chart_container = self.query_one("#chart-container")
                            # Use the container size for maps
                            map_width = max(40, chart_container.size.width - 4)
                            map_height = max(15, chart_container.size.height - 4)
                        except:
                            map_width = 80
                            map_height = 20
                        
                        # For maps, x=lon, y=lat
                        map_output = render_map(
                            lats=y_values,  # y_values are latitudes
                            lons=x_values,  # x_values are longitudes
                            values=color_values if color_values and all(isinstance(v, (int, float)) for v in color_values) else None,
                            colors=color_values if color_values and all(isinstance(c, str) for c in color_values) else None,
                            width=map_width,
                            height=map_height,
                            title=title,
                            map_type=chart_type.replace('map_', '') if chart_type != 'map' else 'points'
                        )
                        if map_output and map_output.strip():
                            self.update_preview(map_output, is_chart=True)
                        else:
                            self.update_preview(self._create_data_preview(
                                chart_type, x_values, y_values, color_values, title
                            ))
                    except Exception as map_error:
                        self.notify(f"Map render error: {str(map_error)}")
                        self.update_preview(self._create_data_preview(
                            chart_type, x_values, y_values, color_values, title
                        ))
                    return
                
                termgraph_types = ['tg_bar', 'tg_hbar', 'tg_multi', 'tg_stacked', 'tg_histogram', 'tg_calendar']
                if chart_type in termgraph_types:
                    # Render termgraph chart
                    try:
                        # render_termgraph is already imported from .main
                        chart_output = render_termgraph(
                            chart_type, x_values, y_values, color_values, 
                            title, default_color, return_string=True
                        )
                        if chart_output and chart_output.strip():
                            self.update_preview(chart_output, is_chart=True)
                        else:
                            self.update_preview(self._create_data_preview(
                                chart_type, x_values, y_values, color_values, title
                            ))
                    except Exception as chart_error:
                        self.notify(f"Termgraph error: {str(chart_error)}")
                        self.update_preview(self._create_data_preview(
                            chart_type, x_values, y_values, color_values, title
                        ))
                else:
                    # Render plotext chart
                    try:
                        chart_output = self.render_chart_to_string(
                            chart_type, x_values, y_values, color_values, title, default_color
                        )
                        if chart_output.strip():
                            self.update_preview(chart_output, is_chart=True)
                        else:
                            # Fallback to data preview if chart rendering fails
                            self.update_preview(self._create_data_preview(
                                chart_type, x_values, y_values, color_values, title
                            ))
                    except Exception as chart_error:
                        # Fallback to data preview
                        self.notify(f"Chart render error: {str(chart_error)}")
                        self.update_preview(self._create_data_preview(
                            chart_type, x_values, y_values, color_values, title
                        ))
                
        except Exception as e:
            self.update_preview(f"[bold red]Error:[/bold red] {str(e)}")
    
    def render_chart_to_string(self, chart_type: str, x_values: List, y_values: List, 
                               color_values: Optional[List], title: Optional[str], 
                               default_color: Optional[str] = None) -> str:
        """Render a chart and capture its output as a string."""
        # Save current stdout
        old_stdout = sys.stdout
        
        try:
            # Create string buffer
            output_buffer = io.StringIO()
            sys.stdout = output_buffer
            
            # Check if this is a map chart type that needs special handling
            map_types = ['map', 'map_points', 'map_density', 'map_clusters', 'map_heatmap', 'map_blocks', 'map_blocks_heatmap', 'map_braille_heatmap']
            matrix_types = ['matrix_heatmap']
            waffle_types = ['waffle']
            pie_types = ['pie']
            
            if chart_type in map_types or chart_type in matrix_types or chart_type in waffle_types or chart_type in pie_types:
                # render_chart is already imported from .main
                
                # Get chart container size for maps
                try:
                    chart_container = self.query_one("#chart-container")
                    width = max(40, chart_container.size.width - 6)
                    height = max(10, chart_container.size.height - 6)
                except:
                    width = 80
                    height = 20
                
                # Create config for render_chart
                config = {
                    'chart': {
                        'width': width,
                        'height': height
                    }
                }
                
                # Call render_chart which will handle map types properly
                render_chart(chart_type, x_values, y_values, color_values, config, 
                           default_color, title, None, None)
                
                # Get the output
                chart_output = output_buffer.getvalue()
                return chart_output
            
            # For plotext charts, continue with existing logic
            # Clear plotext state
            plt.clear_data()
            plt.clear_figure()
            
            # Configure chart size for TUI display
            try:
                chart_container = self.query_one("#chart-container")
                # Use the container size, accounting for padding and borders
                width = max(40, chart_container.size.width - 6)
                height = max(10, chart_container.size.height - 6)
            except:
                width = 80
                height = 20
                
            plt.plotsize(width, height)
            
            # Configure chart theme (keep colors enabled for ANSI rendering)
            plt.theme("clear")
            # Keep canvas transparent but allow colors in the plot
            plt.canvas_color("default")
            plt.axes_color("default")
            plt.ticks_color("default")
            
            # Set title if provided
            if title:
                plt.title(title)
            
            # Handle different chart types
            if color_values:
                # Group data by color for multi-series charts
                groups = group_by_color(x_values, y_values, color_values)
                group_items = list(groups.items())
                for idx, (label, (x_group, y_group)) in enumerate(group_items):
                    series_color = get_color_for_series(idx, len(group_items))
                    self._plot_series(chart_type, x_group, y_group, label, series_color)
            else:
                # Single series
                self._plot_series(chart_type, x_values, y_values, None, default_color)
            
            # Show the plot
            plt.show()
            
            # Get the output
            chart_output = output_buffer.getvalue()
            
            # Clear plotext state
            plt.clear_data()
            plt.clear_figure()
            
            return chart_output
            
        finally:
            # Restore stdout
            sys.stdout = old_stdout
    
    def _plot_series(self, chart_type: str, x_vals: List, y_vals: List, 
                     label: Optional[str], color: Optional[str]) -> None:
        """Plot a single data series based on chart type."""
        # Define which chart types support which parameters
        supports_color = ["bar", "line", "scatter", "histogram", "braille"]
        supports_label = ["bar", "line", "scatter", "histogram", "braille"]
        
        kwargs = {}
        
        # Only add parameters that the chart type supports
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
            
        if chart_type == "bar":
            plt.bar(x_vals, y_vals, **kwargs)
        elif chart_type == "line":
            plt.plot(x_vals, y_vals, **kwargs)
        elif chart_type == "scatter":
            plt.scatter(x_vals, y_vals, **kwargs)
        elif chart_type == "histogram":
            # Histogram only needs y values
            plt.hist(y_vals, **kwargs)
        elif chart_type == "box":
            # Box plot doesn't support color or label
            plt.box(y_vals)
        elif chart_type == "braille":
            plt.scatter(x_vals, y_vals, marker='braille', **kwargs)
        elif chart_type == "simple_bar":
            # Simple bar doesn't support color or label
            plt.simple_bar(x_vals, y_vals)
        elif chart_type == "multiple_bar":
            # Multiple bar doesn't support label parameter
            plt.multiple_bar(x_vals, y_vals)
        elif chart_type == "stacked_bar":
            # Stacked bar doesn't support label parameter
            plt.stacked_bar(x_vals, y_vals)
        else:
            # Default to bar chart
            plt.bar(x_vals, y_vals, **kwargs)
    
    def _create_rich_table_preview(self, results: List[Dict[str, Any]], title: Optional[str],
                                   table_color: Optional[str] = None) -> str:
        """Create a Rich table preview for the TUI with all columns."""
        from rich.console import Console
        from rich.table import Table
        from rich import box
        import io
        
        if not results:
            return "[dim]No results to display[/dim]"
        
        # Create a string buffer to capture Rich output
        string_buffer = io.StringIO()
        console = Console(file=string_buffer, force_terminal=True, width=80)
        
        # Create table
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
            table.add_column(str(col), style=col_style)
        
        # Add rows (limit to 15 for preview)
        display_rows = min(15, len(results))
        for i in range(display_rows):
            row_data = [str(i + 1)]  # 1-based index
            for col in columns:
                value = results[i].get(col, "")
                # Format numbers nicely
                if isinstance(value, (int, float)):
                    if isinstance(value, float):
                        row_data.append(f"{value:.2f}")
                    else:
                        row_data.append(str(value))
                else:
                    row_data.append(str(value))
            table.add_row(*row_data)
        
        if len(results) > display_rows:
            dots_row = ["..."] * (len(columns) + 1)
            table.add_row(*dots_row, style="dim italic")
        
        # Add summary
        footer_row = [""] * (len(columns) + 1)
        table.add_row(*footer_row, style="dim")
        footer_row[0] = "Total"
        footer_row[1] = f"{len(results)} rows"
        table.add_row(*footer_row, style="bold")
        
        console.print(table)
        
        # Get the rendered output
        output = string_buffer.getvalue()
        string_buffer.close()
        
        return output
    
    def _create_data_preview(self, chart_type: str, x_values: List, y_values: List,
                            color_values: Optional[List], title: Optional[str]) -> str:
        """Create a text preview of the data."""
        preview_text = f"[bold green]Chart Type:[/bold green] {chart_type}\n"
        preview_text += f"[bold green]Data Points:[/bold green] {len(x_values)}\n\n"
        
        if title:
            preview_text += f"[bold yellow]Title:[/bold yellow] {title}\n\n"
        
        # Show sample data
        preview_text += "[bold cyan]Sample Data:[/bold cyan]\n"
        for i in range(min(10, len(x_values))):
            if color_values:
                preview_text += f"  x={x_values[i]}, y={y_values[i]}, color={color_values[i]}\n"
            else:
                preview_text += f"  x={x_values[i]}, y={y_values[i]}\n"
        
        if len(x_values) > 10:
            preview_text += f"  ... and {len(x_values) - 10} more rows\n"
        
        return preview_text
    
    def strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI escape sequences from text."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def update_preview(self, content: str, is_chart: bool = False) -> None:
        """Update the chart preview widget."""
        preview = self.query_one("#chart-preview", ChartPreview)
        preview.clear()
        
        if is_chart:
            # For charts, use ANSI rendering to preserve colors
            preview.write_ansi(content)
        else:
            # For other content, use Rich markup
            preview.write(content)
    
    def copy_command(self, quote_style: Optional[str] = None) -> None:
        """Copy the CLI command to clipboard."""
        if self.last_command:
            # Determine which version to copy
            if quote_style == "double":
                command_to_copy = self.escape_for_double_quotes(self.last_command)
                style_name = "double-quoted"
            elif quote_style == "single":
                command_to_copy = self.escape_for_single_quotes(self.last_command)
                style_name = "single-quoted"
            else:
                command_to_copy = self.last_command
                style_name = "raw"
            
            try:
                # Try different clipboard commands
                for cmd in ["pbcopy", "xclip -selection clipboard", "xsel --clipboard --input"]:
                    try:
                        subprocess.run(cmd.split(), input=command_to_copy.encode(), check=True)
                        self.notify(f"{style_name.capitalize()} command copied to clipboard!")
                        return
                    except:
                        continue
                self.notify("Could not copy to clipboard - command displayed above", severity="warning")
            except Exception as e:
                self.notify(f"Copy failed: {str(e)}", severity="error")
        else:
            self.notify("No command to copy - run a query first", severity="warning")
    
    def action_copy_command(self) -> None:
        """Copy the CLI command to clipboard (keyboard shortcut)."""
        self.copy_command()
    
    def action_copy_double(self) -> None:
        """Copy the double-quoted command to clipboard."""
        self.copy_command(quote_style="double")
    
    def action_copy_single(self) -> None:
        """Copy the single-quoted command to clipboard."""
        self.copy_command(quote_style="single")
    
    def browse_database(self) -> None:
        """Browse for database files."""
        # Find all .duckdb files in current directory and subdirectories
        import glob
        
        current_dir = Path.cwd()
        duckdb_files = []
        
        # Search for .duckdb files
        for pattern in ["*.duckdb", "*.db", "*.duck"]:
            duckdb_files.extend(glob.glob(f"**/{pattern}", recursive=True))
            duckdb_files.extend(glob.glob(pattern))
        
        # Remove duplicates and sort
        duckdb_files = sorted(set(duckdb_files))
        
        if not duckdb_files:
            self.notify("No DuckDB files found in current directory", severity="warning")
            return
        
        # Create a simple list of options
        options_text = "Found database files:\n"
        for i, file in enumerate(duckdb_files[:10], 1):
            options_text += f"{i}. {file}\n"
        
        if len(duckdb_files) > 10:
            options_text += f"... and {len(duckdb_files) - 10} more\n"
        
        self.notify(options_text)
        
        # Set the first one found and switch to custom mode
        if duckdb_files:
            db_selector = self.query_one("#db-selector", Select)
            db_input = self.query_one("#db-input", Input)
            custom_row = self.query_one("#custom-db-row")
            
            # Switch to custom path mode
            db_selector.value = "__custom__"
            custom_row.add_class("visible")
            
            # Set the path
            db_input.value = duckdb_files[0]
            self.notify(f"Selected: {duckdb_files[0]}")
    
    
    def load_database_schema(self) -> None:
        """Load and display the database schema in the tree widget."""
        try:
            tree = self.query_one("#schema-tree", Tree)
            
            # Clear existing nodes except root
            tree.root.remove_children()
            tree.root.expand()  # Ensure root is expanded
            
            # Add a loading indicator
            loading_node = tree.root.add_leaf("[dim italic]Loading schema...[/dim italic]")
            
            # Get current database selection
            db_selector = self.query_one("#db-selector", Select)
            db_input = self.query_one("#db-input", Input)
            
            db_selection = db_selector.value
            if db_selection == "__custom__":
                db_identifier = db_input.value.strip()
            else:
                db_identifier = self.databases.get(db_selection, db_selection)
            
            
            # Remove loading node - use remove_children and re-add after
            tree.root.remove_children()
            
            if not db_identifier:
                tree.root.add_leaf("[dim]No database selected[/dim]")
                tree.refresh()
                return
            
            # Check if this is a CSV/TSV file (by checking if it's a path with .csv/.tsv extension)
            if isinstance(db_identifier, str) and (db_identifier.endswith('.csv') or db_identifier.endswith('.tsv')):
                tree.root.add_leaf("[dim]CSV/TSV file - no schema to display[/dim]")
                tree.refresh()
                return
                
            # Get table list based on database type
            if isinstance(db_identifier, dict):
                db_type = db_identifier.get('type', 'duckdb')
            else:
                # Check if it's a named database
                if db_selection in self.databases:
                    db_type = self.databases[db_selection].get('type', 'duckdb')
                else:
                    db_type = 'duckdb'  # Default for file paths
            
            # Query to get tables (varies by database type)
            if db_type == 'duckdb':
                tables_query = "SHOW TABLES"
            elif db_type in ['postgres', 'mysql']:
                tables_query = "SELECT table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'mysql', 'performance_schema')"
            elif db_type == 'sqlite':
                # For SQLite via DuckDB, the connector already handles the schema prefix
                tables_query = "SELECT name FROM sqlite_master WHERE type='table'"
            elif db_type == 'clickhouse':
                tables_query = "SHOW TABLES"
            else:
                tables_query = "SHOW TABLES"
            
            # Execute query to get tables
            tables = execute_query(tables_query, db_identifier, self.config)
            
            if not tables:
                tree.root.add_leaf("[dim]No tables found[/dim]")
                tree.refresh()
                return
            
            # Add tables to tree
            for i, table_row in enumerate(tables):
                # Get table name from result
                if isinstance(table_row, dict):
                    table_name = table_row.get('name') or table_row.get('table_name') or table_row.get('Tables_in_database') or list(table_row.values())[0]
                else:
                    table_name = str(table_row)
                
                # Add table node
                # For SQLite, show the table with schema prefix for clarity
                if db_type == 'sqlite':
                    display_name = f"sqlite_db.{table_name}"
                else:
                    display_name = table_name
                table_node = tree.root.add(f"📊 {display_name}", data={"name": display_name, "type": "table"})
                
                # Get columns for this table
                try:
                    if db_type == 'duckdb':
                        columns_query = f"DESCRIBE {table_name}"
                    elif db_type in ['postgres', 'mysql']:
                        columns_query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'"
                    elif db_type == 'sqlite':
                        # For SQLite via DuckDB, the connector handles the schema
                        columns_query = f"PRAGMA table_info({table_name})"
                    elif db_type == 'clickhouse':
                        columns_query = f"DESCRIBE TABLE {table_name}"
                    else:
                        columns_query = f"DESCRIBE {table_name}"
                    
                    columns = execute_query(columns_query, db_identifier, self.config)
                    
                    for col_row in columns:
                        if isinstance(col_row, dict):
                            # Extract column info based on database type
                            if 'column_name' in col_row:
                                col_name = col_row['column_name']
                                col_type = col_row.get('column_type', col_row.get('data_type', ''))
                            elif 'name' in col_row:
                                col_name = col_row['name']
                                col_type = col_row.get('type', '')
                            elif 'column' in col_row:
                                col_name = col_row['column']
                                col_type = col_row.get('column_type', '')
                            else:
                                # Fallback: use first two values
                                values = list(col_row.values())
                                col_name = values[0] if values else 'unknown'
                                col_type = values[1] if len(values) > 1 else ''
                            
                            table_node.add_leaf(f"📄 {col_name} [{col_type}]")
                        
                except Exception as e:
                    table_node.add_leaf(f"[dim]Error loading columns: {str(e)}[/dim]")
            
            # Ensure root is expanded and refresh tree
            tree.root.expand()
            tree.refresh()
                
        except Exception as e:
            tree = self.query_one("#schema-tree", Tree)
            tree.root.remove_children()
            tree.root.add_leaf(f"[red]Error loading schema: {str(e)}[/red]")
            tree.refresh()
            self.notify(f"Schema load error: {str(e)}", severity="error")
    
    def load_suggestions(self) -> None:
        """Load and display chart suggestions from ALL analysis files."""
        try:
            tree = self.query_one("#suggestions-tree", Tree)
            
            # Clear existing nodes except root
            tree.root.remove_children()
            tree.root.expand()
            tree.root.label = "💡 All Suggestions"
            
            # Add a loading indicator
            loading_node = tree.root.add_leaf("[dim italic]Loading all suggestions...[/dim italic]")
            tree.refresh()  # Show loading immediately
            
            # Find all analysis files
            analysis_files = glob.glob('.cheshire_analysis_*.json')
            if not analysis_files:
                # Clear loading and show message
                tree.root.remove_children()
                tree.root.add_leaf("[dim]No analysis files found. Run --sniff on a database first.[/dim]")
                tree.refresh()
                return
            
            # Clear the loading indicator before adding real content
            tree.root.remove_children()
            
            # Load each analysis file
            total_suggestions = 0
            for analysis_file in sorted(analysis_files):
                try:
                    with open(analysis_file, 'r') as f:
                        analysis_data = json.load(f)
                    
                    # Get database info
                    db_info = analysis_data.get('database', {})
                    if not db_info:
                        # Handle older format
                        db_info = {'type': analysis_data.get('db_type', 'unknown')}
                    
                    # Determine database identifier for switching
                    db_identifier = None
                    db_name_display = "Unknown"
                    
                    if 'name' in db_info:
                        # Named database from config
                        db_identifier = db_info['name']
                        db_name_display = db_info['name']
                    elif 'path' in db_info:
                        # File-based database
                        db_identifier = db_info['path']
                        db_name_display = Path(db_info['path']).stem
                    else:
                        # Try to infer from filename
                        db_name_display = Path(analysis_file).stem.replace('.cheshire_analysis_', '')
                    
                    # Add database node
                    db_node = tree.root.add(f"🗄️ {db_name_display}", data={
                        "type": "database",
                        "db_identifier": db_identifier,
                        "db_info": db_info
                    })
                    
                    # Process tables and their recommendations
                    tables = analysis_data.get('tables', {})
                    if not tables:
                        db_node.add_leaf("[dim]No recommendations[/dim]")
                        continue
                    
                    for table_name, table_data in tables.items():
                        recommendations = table_data.get('recommended_charts', [])
                        if recommendations:
                            # Add table node under database
                            table_node = db_node.add(
                                f"📋 {table_name}",
                                data={"name": table_name, "type": "table"}
                            )
                            
                            # Group recommendations by chart type
                            chart_type_groups = {}
                            for rec in recommendations:
                                chart_type = rec.get('chart_type', 'unknown')
                                if chart_type not in chart_type_groups:
                                    chart_type_groups[chart_type] = []
                                chart_type_groups[chart_type].append(rec)
                            
                            # Add chart type nodes
                            for chart_type, recs in sorted(chart_type_groups.items()):
                                # Create chart type label with icon
                                icon = {
                                    'line': '📈',
                                    'bar': '📊',
                                    'scatter': '🔵',
                                    'histogram': '📊',
                                    'figlet': '🔤',
                                    'rich_table': '📋',
                                    'tg_calendar': '📅',
                                    'tg_bar': '▬',
                                    'tg_multi': '▬▬',
                                    'tg_stacked': '▬▬▬',
                                    'tg_histogram': '▬📊',
                                    'matrix_heatmap': '🔥',
                                    'waffle': '⬛',
                                    'pie': '🥧',
                                }.get(chart_type, '📊')
                                
                                chart_type_label = {
                                    'line': 'Line Charts',
                                    'bar': 'Bar Charts',
                                    'scatter': 'Scatter Plots',
                                    'histogram': 'Histograms',
                                    'figlet': 'Large Display',
                                    'rich_table': 'Data Tables',
                                    'tg_calendar': 'Calendar Heatmaps',
                                    'tg_bar': 'Termgraph Bars',
                                    'tg_multi': 'Multi-Series',
                                    'tg_stacked': 'Stacked Charts',
                                    'tg_histogram': 'TG Histograms',
                                    'matrix_heatmap': 'Matrix Heatmaps',
                                    'waffle': 'Waffle Charts',
                                    'pie': 'Pie Charts',
                                }.get(chart_type, chart_type.title())
                                
                                chart_type_node = table_node.add(
                                    f"{icon} {chart_type_label} ({len(recs)})",
                                    data={"type": "chart_type", "chart_type": chart_type}
                                )
                                
                                # Add individual chart recommendations (limit to top 5 per type)
                                for i, rec in enumerate(sorted(recs, key=lambda x: x.get('score', 0), reverse=True)[:5]):
                                    title = rec.get('title', 'Untitled')
                                    score = rec.get('score', 0)
                                    total_suggestions += 1
                                    
                                    # Simplify the title for display
                                    simple_title = title.replace(f'{table_name} ', '').replace(' over time', '')
                                    label = f"{simple_title} [{score:.1f}]"
                                    
                                    # Store the full recommendation data including database info
                                    chart_type_node.add_leaf(label, data={
                                        "type": "suggestion",
                                        "sql": rec.get('sql', ''),
                                        "chart_type": chart_type,
                                        "title": title,
                                        "table": table_name,
                                        "db_identifier": db_identifier,
                                        "db_info": db_info
                                    })
                
                except Exception as e:
                    # Skip files that fail to load
                    self.notify(f"Error loading {analysis_file}: {str(e)}", severity="warning")
                    continue
            
            # Expand only to database level by default (to keep it manageable)
            tree.root.expand()
            # Optionally expand first database
            if tree.root.children:
                tree.root.children[0].expand()
            
            # Force refresh
            tree.refresh()
            
            # Also refresh the app to ensure layout updates
            self.refresh()
            
            self.notify(f"Loaded {total_suggestions} suggestions from {len(analysis_files)} databases", severity="success")
            
        except Exception as e:
            tree = self.query_one("#suggestions-tree", Tree)
            tree.root.remove_children()
            tree.root.add_leaf(f"[red]Error loading suggestions: {str(e)}[/red]")
            tree.refresh()
            self.notify(f"Suggestions load error: {str(e)}", severity="error")
    
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events."""
        if event.pane.id == "schema-tab":
            # Load schema when Schema tab is activated
            self.load_database_schema()
        elif event.pane.id == "suggestions-tab":
            # Load suggestions when Suggestions tab is activated
            # Add a small delay to ensure tab content is ready
            self.set_timer(0.3, self.load_suggestions)
    
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection - insert table/column name into SQL editor or load suggestion."""
        node = event.node
        
        # Check if this is a suggestion node
        if hasattr(node, 'data') and node.data and node.data.get('type') == 'suggestion':
            # Load the suggestion into the TUI
            sql_input = self.query_one("#sql-input", TextArea)
            chart_selector = self.query_one("#chart-selector", Select)
            title_input = self.query_one("#title-input", Input)
            db_selector = self.query_one("#db-selector", Select)
            db_input = self.query_one("#db-input", Input)
            
            # Switch to the appropriate database
            db_identifier = node.data.get('db_identifier')
            db_info = node.data.get('db_info', {})
            
            if db_identifier:
                # Check if it's a named database in config
                if db_identifier in self.databases:
                    # Select the named database
                    db_selector.value = db_identifier
                    self.notify(f"Switched to database: {db_identifier}", severity="info")
                else:
                    # It's a custom path
                    db_selector.value = "__custom__"
                    db_input.value = db_identifier
                    self.notify(f"Switched to database: {Path(db_identifier).name}", severity="info")
                
                # Reload the schema for the new database
                # Skip schema loading for CSV/TSV files (they don't have schemas)
                db_info = node.data.get('db_info', {})
                if db_info.get('type') not in ['csv', 'tsv']:
                    self.load_database_schema()
            
            # Set SQL query
            sql_input.text = node.data.get('sql', '')
            
            # Set chart type
            chart_type = node.data.get('chart_type', 'bar')
            chart_selector.value = chart_type
            
            # Set title
            title_input.value = node.data.get('title', '')
            
            # Don't switch tabs - stay on Suggestions for easier browsing
            # tabbed_content = self.query_one("#right-panel", TabbedContent)
            # tabbed_content.active = "controls-tab"
            
            # Show notification
            self.notify(f"Loaded suggestion: {node.data.get('title', 'Chart')}", severity="success")
            
            # Auto-run the query
            self.run_query()
            
            # Return focus to SQL editor
            sql_input.focus()
        else:
            # Original schema node handling
            sql_input = self.query_one("#sql-input", TextArea)
            
            # Check if node has data with name
            if hasattr(node, 'data') and node.data and 'name' in node.data:
                name = node.data['name']
            else:
                # Extract the actual name from the node label
                label = str(node.label)
                
                # Remove emoji prefix
                if " " in label:
                    name = label.split(" ", 1)[1]
                    # Remove type info from column names
                    if "[" in name:
                        name = name.split("[")[0].strip()
                else:
                    return
            
            # Insert at cursor position
            sql_input.insert(name)
            
            # Return focus to SQL editor
            sql_input.focus()


def main():
    app = cheshireTUI()
    app.run()


if __name__ == "__main__":
    main()