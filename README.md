# Cheshire

Simple terminal-based SQL visualization tool - turn SQL into ANSI charts, maps, tables, and more. Analyze your data and browse the results in a builder UI, and then copy and paste the command to use in your shell scripts, etc. Build an easy auto-refreshing dashboard out of TMUX panels, etc. Unhide your data from the terminal.

> “Well! I've often seen a cat without a grin,' thought Alice 'but a grin without a cat! It's the most curious thing i ever saw in my life!”

![Alt text](https://raw.githubusercontent.com/ryrobes/cheshire/refs/heads/main/cheshire_snap1.jpg "We're all mad here.")

## Features

### Multiple Data Sources
- **DuckDB** - Primary SQL engine with extensive format support
- **SQLite** - Direct database file queries
- **PostgreSQL** - Via DuckDB postgres_scanner extension
- **MySQL** - Via DuckDB mysql_scanner extension
- **Clickhouse** - Via clickhouse_driver
- **osquery** - System statistics as SQL (processes, network, hardware) **if installed
- **CSV/TSV Files** - Query delimited files directly with SQL
- **Parquet Files** - Analyze single files or entire directories
- **JSON Input** - Pipe JSON arrays directly and query with SQL
- **Remote Databases** - Connect to external SQL servers

### ANSI Visualizations
- **Charts**: Bar, line, scatter, histogram, pie, waffle, and more
- **Geographic Maps**: Point maps, heatmaps, density maps, cluster maps
- **Tables**: Rich formatted tables with colors and styling
- **Figlet**: Large ASCII art text for KPI callouts
- **Matrix Heatmaps**: 2D data visualization with color gradients
- **Termgraph Charts**: Alternative chart renderer with calendar heatmaps

### Chart 'Suggestions'
- **Sniff Database**: Generate a number of basic charts of all kinds based on your data
- **Browse and Modify**: Look through the suggestions to use or adapt

### Powerful Features
- **Interactive TUI**: Browse databases, preview queries, select charts
- **Live Refresh**: Auto-refresh charts at specified intervals
- **Smart Analysis**: Search your database and suggest appropriate charts
- **Multiple Databases**: Configure and switch between multiple data sources
- **Export Support**: Save visualizations or pipe to other tools

![Alt text](https://raw.githubusercontent.com/ryrobes/cheshire/refs/heads/main/cheshire_snap2.jpg "We're all mad here.")
(optional interactive CLI builder)

## Installation

```bash
pip install cheshire-sql
```

## Quick Start

### Basic Usage

```bash
# Launch interactive TUI mode
cheshire

# Simple bar chart from SQLite
cheshire "SELECT product as x, SUM(sales) as y FROM sales GROUP BY product" bar --db sales.db

# Line chart with live refresh every 5 seconds
cheshire "SELECT time as x, cpu_usage as y FROM metrics ORDER BY time" line 5s --db metrics.db

# Geographic map from latitude/longitude data
cheshire "SELECT latitude as lat, longitude as lon FROM locations" map --db geo.db
```

### Working with Files

```bash
# Query CSV files directly
cheshire "SELECT * FROM data WHERE sales > 1000" bar --csv sales.csv

# Analyze TSV file and generate suggestions for the TUI to browse
cheshire --sniff --tsv data.tsv

# Query Parquet files or folders
cheshire "SELECT category as x, AVG(price) as y FROM data GROUP BY category" bar --parquet /path/to/parquet/
```

### Working with JSON Data

```bash
# Pipe JSON data directly into Cheshire
echo '[{"name": "Alice", "score": 90}, {"name": "Bob", "score": 85}]' | \
  cheshire "SELECT name as x, score as y FROM data" bar

# Read JSON from a file
cat sales.json | cheshire "SELECT product as x, SUM(amount) as y FROM data GROUP BY product" bar

# Use explicit --json-input flag
curl -s https://api.example.com/data | \
  cheshire "SELECT * FROM data WHERE value > 100" json --json-input

# Aggregate JSON data
echo '[
  {"category": "A", "value": 10},
  {"category": "B", "value": 20},
  {"category": "A", "value": 15}
]' | cheshire "SELECT category as x, SUM(value) as y FROM data GROUP BY category" pie

# Complex queries on JSON data
cat events.json | cheshire "
  SELECT 
    DATE(timestamp) as x,
    COUNT(*) as y 
  FROM data 
  WHERE status = 'success'
  GROUP BY DATE(timestamp)
  ORDER BY x
" line
```

### System Monitoring with osquery

```bash
# View running processes
cheshire "SELECT name as x, resident_size/1024/1024 as y FROM processes ORDER BY y DESC LIMIT 10" bar --database osquery

# Monitor CPU usage by process
cheshire "SELECT name as x, user_time + system_time as y FROM processes ORDER BY y DESC LIMIT 10" bar 5s --database osquery
```

## Configuration

Create a `cheshire.yaml` file to configure databases and defaults:

```yaml
databases:
  sales:
    type: duckdb
    path: /path/to/sales.db
  
  metrics:
    type: sqlite
    path: /path/to/metrics.db
  
  postgres_prod:
    type: postgres
    host: localhost
    port: 5432
    database: production
    user: readonly
    password: secret
  
  osquery:
    type: osquery  # Auto-detected if osqueryi is installed

default_database: sales

chart_defaults:
  theme: matrix
  markers: braille
  width: null  # Auto-detect
  height: null  # Auto-detect
```

## Chart Types

### Plotext Charts (Default)
Plotext is the primary charting library, providing colorful ANSI charts:
- `bar` - Vertical bar chart (automatically stacks when color column provided)
- `line` - Line chart with optional markers
- `scatter` - Scatter plot with various marker styles
- `histogram` - Distribution histogram
- `braille` - Braille character scatter plot (high resolution)
- `box` - Box plot for statistical distributions
- `simple_bar` - Simplified bar chart
- `multiple_bar` - Multiple bar series side-by-side
- `stacked_bar` - Explicitly stacked bar chart

### Custom Implementations
These are custom-built visualizations unique to Cheshire:
- `pie` - Pie chart with percentages (custom implementation)
- `waffle` - Waffle/square chart for proportions (custom implementation)
- `matrix_heatmap` - 2D matrix visualization with color gradients (custom implementation)

### Geographic Maps (Custom)
Custom map renderer for geographic data (requires lat/lon columns):
- `map` or `map_points` - Point map with Braille characters
- `map_blocks` - Block-based point map
- `map_density` - Density heatmap overlay
- `map_clusters` - Clustered point aggregation
- `map_heatmap` - Geographic heatmap with color gradients
- `map_blocks_heatmap` - True color block heatmap
- `map_braille_heatmap` - Braille character heatmap

### Termgraph Charts
Alternative chart renderer using the termgraph library:
- `tg_bar` - Horizontal bar chart
- `tg_hbar` - Horizontal bar variant
- `tg_multi` - Multi-series bar chart
- `tg_stacked` - Stacked bar chart
- `tg_histogram` - Histogram with customizable bins
- `tg_calendar` - Calendar heatmap for time series data

### Tables and Text
- `rich_table` - Formatted table with colors (uses Rich library)
- `figlet` - Large ASCII art text for KPIs (uses pyfiglet library)
- `json` - Raw JSON output of query results (built-in)

## SQL Query Format

Queries must return specific column names depending on the chart type:

### Standard Charts
```sql
SELECT 
  category as x,      -- X-axis values
  SUM(amount) as y,   -- Y-axis values
  status as color     -- Optional: color grouping
FROM sales
GROUP BY category, status
```

### Geographic Maps
```sql
SELECT 
  latitude as lat,    -- Latitude
  longitude as lon,   -- Longitude
  sales as value      -- Optional: heat value
FROM store_locations
```

### Pie/Waffle Charts
```sql
SELECT 
  category as x,      -- Category labels
  COUNT(*) as y       -- Values
FROM products
GROUP BY category
```

## Advanced Features

### Live Refresh
Add an interval to auto-refresh charts:
```bash
cheshire "SELECT ..." bar 5s    # Refresh every 5 seconds
cheshire "SELECT ..." line 1m    # Refresh every minute
cheshire "SELECT ..." scatter 0.5h  # Refresh every 30 minutes
```

### Database Analysis
Analyze a database to generate chart suggestions:
```bash
# Analyze configured database
cheshire --sniff --database sales

# Analyze SQLite file
cheshire --sniff --db mydata.db

# Analyze CSV file
cheshire --sniff --csv data.csv

# Analyze Parquet folder
cheshire --sniff --parquet /data/parquet/
```

### Chart Size Control
```bash
# Set explicit width and height in characters
cheshire "SELECT ..." bar --width 60 --height 20

# Use percentage of terminal size
cheshire "SELECT ..." line --width "80%" --height "50%"

# Mix absolute and percentage
cheshire "SELECT ..." scatter --width "75%" --height 15

# Small inline charts
cheshire "SELECT ..." bar --width 40 --height 8
```

### Color Customization
```bash
# Named colors
cheshire "SELECT ..." bar --color red

# Hex colors
cheshire "SELECT ..." line --color "#FF5733"

# Themes
cheshire "SELECT ..." scatter --theme matrix
```

## Interactive TUI Mode

Launch without arguments to enter the interactive TUI:

```bash
cheshire
```

Features:
- Database browser with table listings
- SQL query editor with syntax highlighting
- Live preview of query results
- Chart type selector with recommendations
- Keyboard navigation and shortcuts

### TUI Keyboard Shortcuts
- `Tab` - Switch between panels
- `Enter` - Execute query/select item
- `Esc` - Exit/cancel
- `Ctrl+Q` - Quit application
- `Ctrl+C` - Copy current chart's CLI

## Examples

### Sales Dashboard
```bash
# Top products by revenue
cheshire "SELECT product as x, SUM(revenue) as y FROM sales GROUP BY product ORDER BY y DESC LIMIT 10" bar --db sales.db

# Sales trend over time
cheshire "SELECT DATE(order_date) as x, SUM(amount) as y FROM orders GROUP BY 1 ORDER BY 1" line --db sales.db

# Geographic distribution
cheshire "SELECT store_lat as lat, store_lon as lon, SUM(sales) as value FROM stores GROUP BY lat, lon" map_heatmap --db sales.db
```

### System Monitoring
```bash
# Memory usage by process
cheshire "SELECT name as x, resident_size/1024/1024 as y FROM processes WHERE resident_size > 0 ORDER BY y DESC LIMIT 15" bar --database osquery

# Network connections
cheshire "SELECT remote_address as x, COUNT(*) as y FROM process_open_sockets GROUP BY remote_address ORDER BY y DESC LIMIT 10" bar --database osquery

# CPU time distribution
cheshire "SELECT name as x, (user_time + system_time) as y FROM processes ORDER BY y DESC LIMIT 20" pie --database osquery
```

### Data Analysis
```bash
# Analyze CSV and view suggestions
cheshire --sniff --csv sales_data.csv

# Query Parquet files with complex aggregations
cheshire "WITH monthly AS (SELECT DATE_TRUNC('month', date) as month, SUM(sales) as total FROM data GROUP BY 1) SELECT month as x, total as y FROM monthly ORDER BY month" line --parquet /data/

# Join multiple data sources using DuckDB
cheshire "SELECT c.name as x, SUM(s.amount) as y FROM read_csv_auto('customers.csv') c JOIN sales s ON c.id = s.customer_id GROUP BY c.name" bar --db sales.db

# Export query results as JSON for further processing
cheshire "SELECT * FROM sales WHERE date >= '2024-01-01'" json --db sales.db > sales_2024.json
```

## Troubleshooting

### Common Issues

**No color output**: Force color mode with environment variable:
```bash
FORCE_COLOR=1 cheshire "SELECT ..." bar
```

**Database not found**: Check file path or configure in cheshire.yaml:
```bash
cheshire --list-databases  # Show configured databases
```

**osquery not detected**: Ensure osqueryi is installed and in PATH:
```bash
which osqueryi  # Should show path to osqueryi
```

**Chart too large/small**: Adjust terminal size or set explicit dimensions:
```yaml
# In cheshire.yaml
chart_defaults:
  width: 80
  height: 24
```

![Alt text](https://raw.githubusercontent.com/ryrobes/cheshire/refs/heads/main/cheshire_snap0.jpg "We're all mad here.")

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## Acknowledgments

Built with amazing open-source libraries including DuckDB, plotext, Rich, and many others.