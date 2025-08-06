#!/usr/bin/env python3
"""
True color matrix heatmap for dimension x dimension analysis.
Creates a grid/matrix visualization with color-coded cells based on aggregate values.
"""

from typing import List, Dict, Any, Optional, Tuple
import math

def render_matrix_heatmap(
    x_values: List[Any],
    y_values: List[Any], 
    cell_values: Optional[List[float]] = None,
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    value_format: str = ".0f",
    show_values: bool = False,
    color_scheme: str = "green_yellow_red"
) -> str:
    """
    Render a matrix heatmap with true color gradients.
    
    Args:
        x_values: Values for X axis (columns)
        y_values: Values for Y axis (rows)
        cell_values: Values for each cell (same length as x_values and y_values)
        title: Optional title for the heatmap
        x_label: Label for X axis
        y_label: Label for Y axis
        width: Width in characters (auto-sizes if None)
        height: Height in characters (auto-sizes if None)
        value_format: Format string for displaying values
        show_values: Whether to show numeric values in cells
        color_scheme: Color gradient scheme
    """
    
    if not x_values or not y_values:
        return "No data to display"
    
    # Create a pivot table structure
    pivot_data = {}
    for i, (x, y) in enumerate(zip(x_values, y_values)):
        if y not in pivot_data:
            pivot_data[y] = {}
        
        value = cell_values[i] if cell_values and i < len(cell_values) else 1
        
        # Aggregate (sum) values for same x,y pairs
        if x in pivot_data[y]:
            pivot_data[y][x] += value
        else:
            pivot_data[y][x] = value
    
    # Get unique sorted dimensions
    unique_x = sorted(list(set(x_values)), key=lambda x: (x is None, str(x)))
    unique_y = sorted(list(set(y_values)), key=lambda y: (y is None, str(y)))
    
    # Limit dimensions for reasonable display
    max_cols = 20
    max_rows = 20
    
    if len(unique_x) > max_cols:
        # Take top N by total value
        x_totals = {}
        for y in unique_y:
            for x in unique_x:
                val = pivot_data.get(y, {}).get(x, 0)
                x_totals[x] = x_totals.get(x, 0) + val
        unique_x = sorted(x_totals.keys(), key=lambda x: x_totals[x], reverse=True)[:max_cols]
        
    if len(unique_y) > max_rows:
        # Take top N by total value
        y_totals = {}
        for y in unique_y:
            total = sum(pivot_data.get(y, {}).values())
            y_totals[y] = total
        unique_y = sorted(y_totals.keys(), key=lambda y: y_totals[y], reverse=True)[:max_rows]
    
    # Calculate cell dimensions
    # X labels need to be rotated or truncated
    max_x_label_len = max(len(str(x)) for x in unique_x) if unique_x else 5
    max_y_label_len = max(len(str(y)) for y in unique_y) if unique_y else 5
    
    # Cell width should accommodate values if shown
    cell_width = max(6, max_x_label_len + 1)
    if show_values:
        cell_width = max(cell_width, 8)
    
    # Auto-size based on terminal if not specified
    if width is None:
        try:
            import os
            term_width = os.get_terminal_size().columns
            width = min(term_width - 4, max_y_label_len + 2 + len(unique_x) * cell_width)
        except:
            width = max_y_label_len + 2 + min(len(unique_x), 15) * cell_width
    
    if height is None:
        try:
            import os
            term_height = os.get_terminal_size().lines
            height = min(term_height - 10, len(unique_y) + 5)
        except:
            height = min(30, len(unique_y) + 5)
    
    # Find min/max values for color scaling
    all_values = []
    for y in unique_y:
        for x in unique_x:
            val = pivot_data.get(y, {}).get(x, 0)
            if val > 0:
                all_values.append(val)
    
    if not all_values:
        return "No data to display"
    
    min_val = min(all_values)
    max_val = max(all_values)
    
    # Build the output
    lines = []
    
    # Title
    if title:
        lines.append(f"\033[1m{title.center(width)}\033[0m")
        lines.append("")
    
    # Column headers (X axis labels)
    header_line = " " * (max_y_label_len + 2)
    for x in unique_x:
        x_str = str(x)[:cell_width-1]
        header_line += x_str.center(cell_width)
    lines.append(header_line)
    
    # Separator
    lines.append("─" * (max_y_label_len + 1) + "┬" + "─" * (len(unique_x) * cell_width))
    
    # Data rows with Y labels
    for y in unique_y:
        row_line = str(y)[:max_y_label_len].rjust(max_y_label_len) + " │"
        
        for x in unique_x:
            value = pivot_data.get(y, {}).get(x, 0)
            
            if value > 0:
                # Calculate color based on value
                if max_val > min_val:
                    normalized = (value - min_val) / (max_val - min_val)
                else:
                    normalized = 0.5
                
                # Color gradient
                if color_scheme == "green_yellow_red":
                    if normalized <= 0.5:
                        # Green to Yellow
                        r = int(normalized * 2 * 255)
                        g = 255
                        b = 0
                    else:
                        # Yellow to Red
                        r = 255
                        g = int((1 - (normalized - 0.5) * 2) * 255)
                        b = 0
                elif color_scheme == "blue_white_red":
                    if normalized <= 0.5:
                        # Blue to White
                        r = int(normalized * 2 * 255)
                        g = int(normalized * 2 * 255)
                        b = 255
                    else:
                        # White to Red
                        r = 255
                        g = int((1 - (normalized - 0.5) * 2) * 255)
                        b = int((1 - (normalized - 0.5) * 2) * 255)
                else:  # cool_warm
                    if normalized <= 0.5:
                        # Blue to White
                        r = int(normalized * 2 * 255)
                        g = int(normalized * 2 * 220)
                        b = 255 - int(normalized * 2 * 55)
                    else:
                        # White to Red
                        r = 255
                        g = 220 - int((normalized - 0.5) * 2 * 140)
                        b = 200 - int((normalized - 0.5) * 2 * 200)
                
                # Create colored cell
                color = f'\033[38;2;{r};{g};{b}m'
                reset = '\033[0m'
                
                if show_values:
                    # Show value in cell with comma formatting for integers
                    if value_format == ".0f":
                        val_str = f"{value:,.0f}"[:cell_width-1]
                    else:
                        val_str = f"{value:{value_format}}"[:cell_width-1]
                    cell = color + val_str.center(cell_width) + reset
                else:
                    # Use block characters for pure color cells
                    cell = color + ("█" * (cell_width - 1)).center(cell_width) + reset
                
                row_line += cell
            else:
                # Empty cell
                row_line += " " * cell_width
        
        lines.append(row_line)
    
    # Add axis labels if provided
    if x_label or y_label:
        lines.append("")
        if x_label:
            lines.append(" " * (max_y_label_len + 2) + f"← {x_label} →".center(len(unique_x) * cell_width))
        if y_label:
            lines.append(f"↑ {y_label} ↓".center(max_y_label_len))
    
    # Add legend with comma formatting
    lines.append("")
    lines.append("Scale: " + 
                 f"\033[38;2;0;255;0m█\033[0m {min_val:,.0f} " +
                 f"\033[38;2;128;255;0m█\033[0m " +
                 f"\033[38;2;255;255;0m█\033[0m {(min_val + max_val)/2:,.0f} " +
                 f"\033[38;2;255;128;0m█\033[0m " +
                 f"\033[38;2;255;0;0m█\033[0m {max_val:,.0f}")
    
    return "\n".join(lines)


def extract_matrix_data(results: List[Dict[str, Any]]) -> Tuple[List, List, List]:
    """Extract x, y, and value data from query results for matrix heatmap."""
    if not results:
        return [], [], []
    
    # Look for x, y, and optionally value columns
    first_row = results[0]
    keys = list(first_row.keys())
    
    x_col = None
    y_col = None
    value_col = None
    
    # Try to identify columns
    for key in keys:
        key_lower = key.lower()
        if not x_col and 'x' in key_lower:
            x_col = key
        elif not y_col and 'y' in key_lower:
            y_col = key
        elif not value_col and ('value' in key_lower or 'count' in key_lower or 'sum' in key_lower):
            value_col = key
    
    # Fallback to first two columns for x and y
    if not x_col and len(keys) >= 1:
        x_col = keys[0]
    if not y_col and len(keys) >= 2:
        y_col = keys[1]
    if not value_col and len(keys) >= 3:
        value_col = keys[2]
    
    if not x_col or not y_col:
        return [], [], []
    
    # Extract data
    x_values = []
    y_values = []
    cell_values = []
    
    for row in results:
        x_values.append(row.get(x_col))
        y_values.append(row.get(y_col))
        if value_col:
            cell_values.append(float(row.get(value_col, 1)))
        else:
            cell_values.append(1)  # Count records
    
    return x_values, y_values, cell_values


if __name__ == "__main__":
    # Test the matrix heatmap
    import random
    
    # Generate sample data
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    categories = ['A', 'B', 'C', 'D', 'E']
    
    x_vals = []
    y_vals = []
    values = []
    
    for _ in range(200):
        month = random.choice(months)
        category = random.choice(categories)
        value = random.randint(1, 100)
        
        x_vals.append(month)
        y_vals.append(category)
        values.append(value)
    
    # Test different display modes
    print("Matrix Heatmap Examples")
    print("=" * 100)
    
    print("\n1. BASIC MATRIX (blocks only):")
    print("-" * 100)
    output1 = render_matrix_heatmap(
        x_vals, y_vals, values,
        title="Sales by Month and Category",
        x_label="Month",
        y_label="Category",
        show_values=False
    )
    print(output1)
    
    print("\n2. MATRIX WITH VALUES:")
    print("-" * 100)
    output2 = render_matrix_heatmap(
        x_vals, y_vals, values,
        title="Sales by Month and Category (with values)",
        x_label="Month",
        y_label="Category",
        show_values=True
    )
    print(output2)