#!/usr/bin/env python3
"""
Waffle chart visualization using Unicode characters and true color.
Perfect for showing proportions, parts-of-whole, and percentages.
"""

from typing import List, Dict, Any, Optional, Tuple
import math

def render_waffle_chart(
    values: List[float],
    labels: Optional[List[str]] = None,
    title: Optional[str] = None,
    total_cells: int = 100,
    cells_per_row: int = 10,
    cell_char: str = "■",
    empty_char: str = "□",
    show_legend: bool = True,
    show_percentages: bool = True,
    color_scheme: str = "distinct",  # distinct, gradient, monochrome
    custom_colors: Optional[List[Tuple[int, int, int]]] = None
) -> str:
    """
    Render a waffle chart using Unicode blocks and true color.
    
    Args:
        values: List of values to display
        labels: Optional labels for each value
        title: Optional title for the chart
        total_cells: Total number of cells in the waffle (default 100 for percentages)
        cells_per_row: Number of cells per row (default 10)
        cell_char: Character to use for filled cells
        empty_char: Character to use for empty cells
        show_legend: Whether to show the legend
        show_percentages: Whether to show percentages in the legend
        color_scheme: Color scheme to use
        custom_colors: Optional list of RGB tuples for custom colors
    """
    
    if not values:
        return "No data to display"
    
    # Ensure all values are numeric and positive
    numeric_values = []
    for v in values:
        try:
            numeric_val = float(v) if v is not None else 0
            numeric_values.append(max(0, numeric_val))
        except (ValueError, TypeError):
            numeric_values.append(0)
    
    values = numeric_values
    total = sum(values)
    
    if total == 0:
        return "No data to display (all values are zero)"
    
    # Calculate cell counts for each value
    cell_counts = []
    remaining_cells = total_cells
    
    for i, value in enumerate(values):
        if i == len(values) - 1:
            # Last value gets remaining cells to avoid rounding errors
            cells = remaining_cells
        else:
            cells = round(value / total * total_cells)
            remaining_cells -= cells
        cell_counts.append(cells)
    
    # Generate colors
    colors = generate_colors(len(values), color_scheme, custom_colors)
    
    # Build the waffle grid
    cells = []
    for i, count in enumerate(cell_counts):
        cells.extend([i] * count)
    
    # Pad with empty cells if needed
    while len(cells) < total_cells:
        cells.append(-1)  # -1 represents empty
    
    # Build output
    lines = []
    
    # Title
    if title:
        lines.append(f"\033[1m{title}\033[0m")
        lines.append("")
    
    # Calculate rows
    num_rows = math.ceil(total_cells / cells_per_row)
    
    # Draw waffle
    for row in range(num_rows):
        row_chars = []
        for col in range(cells_per_row):
            idx = row * cells_per_row + col
            if idx < len(cells):
                cell_value = cells[idx]
                if cell_value == -1:
                    # Empty cell
                    row_chars.append(f"\033[90m{empty_char}\033[0m")
                else:
                    # Colored cell
                    r, g, b = colors[cell_value]
                    row_chars.append(f"\033[38;2;{r};{g};{b}m{cell_char}\033[0m")
            else:
                # Beyond total cells
                row_chars.append(" ")
        
        lines.append(" ".join(row_chars))
    
    # Legend
    if show_legend and labels:
        lines.append("")
        lines.append("─" * (cells_per_row * 2 - 1))
        
        for i, (label, value, count) in enumerate(zip(labels, values, cell_counts)):
            if count > 0:
                r, g, b = colors[i]
                percentage = value / total * 100
                
                legend_parts = [f"\033[38;2;{r};{g};{b}m{cell_char}\033[0m"]
                legend_parts.append(f"{label}")
                
                if show_percentages:
                    legend_parts.append(f"({percentage:.1f}%)")
                
                # Add actual value
                if value >= 1000000:
                    value_str = f"{value/1000000:.1f}M"
                elif value >= 1000:
                    value_str = f"{value/1000:.1f}K"
                else:
                    value_str = f"{value:,.0f}"
                legend_parts.append(f"= {value_str}")
                
                lines.append(" ".join(legend_parts))
    
    # Summary statistics
    if not labels or not show_legend:
        lines.append("")
        lines.append(f"Total: {total:,.0f}")
    
    return "\n".join(lines)


def generate_colors(
    n: int,
    scheme: str = "distinct",
    custom_colors: Optional[List[Tuple[int, int, int]]] = None
) -> List[Tuple[int, int, int]]:
    """Generate colors for the waffle chart."""
    
    if custom_colors and len(custom_colors) >= n:
        return custom_colors[:n]
    
    if scheme == "distinct":
        # Distinct colors that work well together
        palette = [
            (26, 188, 156),   # Turquoise
            (52, 152, 219),   # Blue
            (155, 89, 182),   # Purple
            (231, 76, 60),    # Red
            (230, 126, 34),   # Orange
            (241, 196, 15),   # Yellow
            (46, 204, 113),   # Green
            (149, 165, 166),  # Gray
            (52, 73, 94),     # Dark blue
            (192, 57, 43),    # Dark red
            (142, 68, 173),   # Dark purple
            (39, 174, 96),    # Dark green
            (243, 156, 18),   # Dark yellow
            (211, 84, 0),     # Dark orange
            (41, 128, 185),   # Medium blue
            (127, 140, 141),  # Medium gray
        ]
        return palette[:n] if n <= len(palette) else palette * (n // len(palette) + 1)[:n]
    
    elif scheme == "gradient":
        # Gradient from green to yellow to red
        colors = []
        for i in range(n):
            t = i / max(1, n - 1)
            if t <= 0.5:
                # Green to yellow
                r = int(t * 2 * 255)
                g = 255
                b = 0
            else:
                # Yellow to red
                r = 255
                g = int((1 - (t - 0.5) * 2) * 255)
                b = 0
            colors.append((r, g, b))
        return colors
    
    elif scheme == "monochrome":
        # Shades of blue
        colors = []
        for i in range(n):
            intensity = 0.3 + (0.7 * (i / max(1, n - 1)))
            r = int(52 * intensity)
            g = int(152 * intensity)
            b = int(219 * intensity)
            colors.append((r, g, b))
        return colors
    
    else:
        # Default to distinct
        return generate_colors(n, "distinct")


def render_progress_waffle(
    value: float,
    total: float,
    title: Optional[str] = None,
    width: int = 20,
    height: int = 5,
    filled_char: str = "█",
    empty_char: str = "░",
    color_good: Tuple[int, int, int] = (46, 204, 113),
    color_warning: Tuple[int, int, int] = (241, 196, 15),
    color_danger: Tuple[int, int, int] = (231, 76, 60),
    warning_threshold: float = 0.7,
    danger_threshold: float = 0.3
) -> str:
    """
    Render a progress waffle chart - great for showing completion, capacity, etc.
    """
    if total <= 0:
        return "Invalid total value"
    
    percentage = min(1.0, max(0.0, value / total))
    total_cells = width * height
    filled_cells = round(percentage * total_cells)
    
    # Determine color based on thresholds
    if percentage >= warning_threshold:
        r, g, b = color_good
    elif percentage >= danger_threshold:
        r, g, b = color_warning
    else:
        r, g, b = color_danger
    
    lines = []
    
    # Title
    if title:
        lines.append(f"\033[1m{title}\033[0m")
    
    # Progress bar
    for row in range(height):
        row_chars = []
        for col in range(width):
            idx = row * width + col
            if idx < filled_cells:
                row_chars.append(f"\033[38;2;{r};{g};{b}m{filled_char}\033[0m")
            else:
                row_chars.append(f"\033[90m{empty_char}\033[0m")
        lines.append("".join(row_chars))
    
    # Stats
    lines.append("")
    lines.append(f"{value:,.0f} / {total:,.0f} ({percentage*100:.1f}%)")
    
    return "\n".join(lines)


def extract_waffle_data(results: List[Dict[str, Any]]) -> Tuple[List[float], List[str]]:
    """Extract data for waffle chart from query results."""
    if not results:
        return [], []
    
    # Try to identify label and value columns
    first_row = results[0]
    keys = list(first_row.keys())
    
    label_col = None
    value_col = None
    
    # Look for appropriate columns
    for key in keys:
        key_lower = key.lower()
        if not label_col and any(word in key_lower for word in ['name', 'label', 'category', 'type', 'group']):
            label_col = key
        elif not value_col and any(word in key_lower for word in ['value', 'count', 'sum', 'total', 'amount']):
            value_col = key
    
    # Fallback to first two columns
    if not label_col and len(keys) >= 1:
        label_col = keys[0]
    if not value_col and len(keys) >= 2:
        value_col = keys[1]
    elif not value_col and len(keys) >= 1:
        value_col = keys[0]
    
    # Extract data
    labels = []
    values = []
    
    for row in results:
        if label_col:
            labels.append(str(row.get(label_col, "Unknown")))
        if value_col:
            try:
                values.append(float(row.get(value_col, 0)))
            except (ValueError, TypeError):
                values.append(0)
    
    return values, labels


if __name__ == "__main__":
    # Test the waffle chart
    print("Waffle Chart Examples")
    print("=" * 60)
    
    # Example 1: Market share
    print("\n1. MARKET SHARE:")
    print("-" * 60)
    values1 = [35, 25, 20, 15, 5]
    labels1 = ["Company A", "Company B", "Company C", "Company D", "Others"]
    print(render_waffle_chart(
        values1, labels1,
        title="Market Share Distribution",
        show_percentages=True
    ))
    
    # Example 2: Progress indicator
    print("\n2. STORAGE USAGE:")
    print("-" * 60)
    print(render_progress_waffle(
        750, 1000,
        title="Disk Space Usage",
        warning_threshold=0.8,
        danger_threshold=0.9
    ))
    
    # Example 3: Survey results with gradient
    print("\n3. CUSTOMER SATISFACTION:")
    print("-" * 60)
    values3 = [45, 30, 15, 7, 3]
    labels3 = ["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very Dissatisfied"]
    print(render_waffle_chart(
        values3, labels3,
        title="Customer Satisfaction Survey (n=1000)",
        color_scheme="gradient"
    ))
    
    # Example 4: Small multiples concept
    print("\n4. QUARTERLY BREAKDOWN:")
    print("-" * 60)
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    for q in quarters:
        values = [30 + (ord(q[1]) - ord('1')) * 5, 20 - (ord(q[1]) - ord('1')) * 2, 10]
        print(f"\n{q} Sales by Region:")
        print(render_waffle_chart(
            values,
            ["North", "South", "East"],
            total_cells=50,
            cells_per_row=10,
            show_legend=False
        ))
    
    print("\n" + "=" * 60)
    print("Waffle Chart Features:")
    print("- Unicode block characters for clean appearance")
    print("- True color support for better visualization")
    print("- Configurable grid size and dimensions")
    print("- Multiple color schemes (distinct, gradient, monochrome)")
    print("- Progress/gauge mode for single metrics")
    print("=" * 60)