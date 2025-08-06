#!/usr/bin/env python3
"""
Pie chart visualization using Unicode characters (Braille, blocks) and true color.
Creates circular visualizations for proportional data.
"""

from typing import List, Dict, Any, Optional, Tuple
import math
import os


def render_pie_chart(
    values: List[float],
    labels: Optional[List[str]] = None,
    title: Optional[str] = None,
    radius: int = 10,
    show_legend: bool = True,
    show_percentages: bool = True,
    color_scheme: str = "distinct",
    use_braille: bool = True,
    custom_colors: Optional[List[Tuple[int, int, int]]] = None,
    auto_size: bool = True
) -> str:
    """
    Render a pie chart using Unicode characters and true color.

    Args:
        values: List of values to display
        labels: Optional labels for each value
        title: Optional title for the chart
        radius: Radius of the pie chart in characters
        show_legend: Whether to show the legend
        show_percentages: Whether to show percentages in the legend
        color_scheme: Color scheme to use
        use_braille: Whether to use Braille characters for smoother edges
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

    # Calculate angles for each segment
    angles = []
    current_angle = -math.pi / 2  # Start at top
    for value in values:
        angle = (value / total) * 2 * math.pi
        angles.append((current_angle, current_angle + angle))
        current_angle += angle

    # Generate colors
    colors = generate_colors(len(values), color_scheme, custom_colors)

    # Calculate radius based on terminal size if auto_size is enabled
    if auto_size:
        # Try to get terminal size
        try:
            # Try environment variables first
            term_height = int(os.environ.get('LINES', 0))
            term_width = int(os.environ.get('COLUMNS', 0))

            # If not set, try using os.get_terminal_size()
            if term_height == 0 or term_width == 0:
                size = os.get_terminal_size()
                term_height = size.lines
                term_width = size.columns
        except (ValueError, TypeError, OSError):
            # Fallback to standard terminal size
            term_height = 24
            term_width = 80

        # Reserve space for title (2 lines), legend (len(values) + 3 lines), and margins (2 lines)
        reserved_height = 2 + len(values) + 3 + 2 if show_legend else 4
        available_height = max(8, term_height - reserved_height)

        # Calculate maximum radius that fits
        # Height = radius * 1.4 (for actual circle height with margin)
        max_radius_from_height = int(available_height / 1.33)

        # Width = radius * 4 + 3 (doubled horizontal stretch)
        max_radius_from_width = int((term_width - 2) / 3.5)

        # Use the smaller of the two to ensure it fits
        radius = min(max_radius_from_height, max_radius_from_width, 7)  # Cap at 12
        radius = max(radius, 2.2)  # Minimum radius of 4

    # Create the canvas with aspect ratio correction
    # Terminal chars are ~2:1 (height:width), half-blocks help with vertical resolution
    # We need to make the circle wider in character space to appear round visually
    radius_x = int(radius * 2.0)  # Double horizontal for terminal aspect ratio
    radius_y = radius              # Vertical radius (normal in calculation space)
    width = radius_x * 2 + 5
    height = int(radius_y * 1.5) + 6  # Reduce height to fit better
    canvas = [[' ' for _ in range(width)] for _ in range(height)]
    canvas_colors = [[None for _ in range(width)] for _ in range(height)]

    # Center of the circle
    cx = width // 2
    cy = height // 1.9

    # Draw the pie chart
    if use_braille:
        draw_pie_braille(canvas, canvas_colors, cx, cy, radius_x, radius_y, angles, colors)
    else:
        draw_pie_blocks(canvas, canvas_colors, cx, cy, radius_x, radius_y, angles, colors)

    # Build output
    lines = []

    # Title
    if title:
        lines.append(f"\033[1m{title.center(width)}\033[0m")
        lines.append("")

    # Render canvas
    for y in range(height):
        row = []
        for x in range(width):
            if canvas_colors[y][x] is not None:
                r, g, b = canvas_colors[y][x]
                row.append(f"\033[38;2;{r};{g};{b}m{canvas[y][x]}\033[0m")
            else:
                row.append(canvas[y][x])
        lines.append(''.join(row))

    # Legend
    if show_legend and labels:
        lines.append("")
        lines.append("─" * min(50, width))

        for i, (label, value) in enumerate(zip(labels, values)):
            if value > 0:
                r, g, b = colors[i]
                percentage = value / total * 100

                # Use block character for legend
                legend_parts = [f"\033[38;2;{r};{g};{b}m██\033[0m"]
                legend_parts.append(f"{label}")

                if show_percentages:
                    legend_parts.append(f"({percentage:.1f}%)")

                # Add actual value
                if value >= 1000000:
                    value_str = f"{value / 1000000:.1f}M"
                elif value >= 1000:
                    value_str = f"{value / 1000:.1f}K"
                else:
                    value_str = f"{value:,.0f}"
                legend_parts.append(f"= {value_str}")

                lines.append(" ".join(legend_parts))

    return "\n".join(lines)


def draw_pie_blocks(canvas, canvas_colors, cx, cy, radius_x, radius_y, angles, colors):
    """Draw pie chart using half-block characters with aspect ratio correction."""
    # Use half blocks for better aspect ratio
    # Upper half block: ▀, Lower half block: ▄, Full block: █

    for y in range(len(canvas)):
        for x in range(len(canvas[0])):
            # Calculate distance and angle from center with aspect correction
            dx = (x - cx) / 2.0  # Compress horizontal since we stretched canvas
            dy = y - cy          # Normal vertical
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= radius_y:
                # Calculate angle (atan2 returns -π to π)
                angle = math.atan2(dy, dx)

                # Find which segment this point belongs to
                for i, (start_angle, end_angle) in enumerate(angles):
                    # Normalize angle to be in the same range as our segments
                    # Our segments go from -π/2 and wrap around to > π
                    test_angle = angle
                    if test_angle < start_angle:
                        test_angle += 2 * math.pi

                    # Also check if end wrapped around
                    test_end = end_angle
                    if test_end < start_angle:
                        test_end += 2 * math.pi

                    # Now simple comparison works
                    in_segment = (start_angle <= test_angle <= test_end)

                    if in_segment:
                        # Fill with full blocks (no half-blocks to avoid gaps)
                        canvas[y][x] = '█'
                        canvas_colors[y][x] = colors[i]
                        break


def draw_pie_braille(canvas, canvas_colors, cx, cy, radius_x, radius_y, angles, colors):
    """Draw pie chart using Braille characters for smoother edges with aspect correction."""
    # First pass: draw filled segments
    for y in range(len(canvas)):
        for x in range(len(canvas[0])):
            dx = (x - cx) / 1.8  # Compress horizontal since we stretched canvas
            dy = y - cy          # Normal vertical
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= radius_y:  # Fill entire circle
                angle = math.atan2(dy, dx)

                for i, (start_angle, end_angle) in enumerate(angles):
                    # Normalize angle to be in the same range as our segments
                    test_angle = angle
                    if test_angle < start_angle:
                        test_angle += 2 * math.pi

                    # Also check if end wrapped around
                    test_end = end_angle
                    if test_end < start_angle:
                        test_end += 2 * math.pi

                    # Now simple comparison works
                    in_segment = (start_angle <= test_angle <= test_end)

                    if in_segment:
                        # Fill with solid blocks
                        canvas[y][x] = '█'
                        canvas_colors[y][x] = colors[i]
                        break

    # Second pass: Add Braille edges for aesthetic effect
    braille_base = 0x2800
    for y in range(len(canvas)):
        for x in range(len(canvas[0])):
            # Only process edge positions that are empty
            if canvas[y][x] != ' ':
                continue

            # Check if this position is near the edge of the circle
            dx = (x - cx) / 1.85
            dy = y - cy
            dist = math.sqrt(dx * dx + dy * dy)

            # Only process points near the edge
            if radius_y - 1.0 <= dist <= radius_y + 0.9:
                # Build Braille pattern for this position
                pattern = 0
                edge_color = None

                # Sample 2x4 sub-positions for Braille
                for sub_x in range(7):
                    for sub_y in range(9):
                        # Calculate sub-position
                        px = x + sub_x * 0.35
                        py = y + sub_y * 0.25

                        # Check distance and angle for this sub-position
                        sub_dx = (px - cx) / 2.0
                        sub_dy = py - cy
                        sub_dist = math.sqrt(sub_dx * sub_dx + sub_dy * sub_dy)

                        if sub_dist <= radius_y:
                            # This sub-pixel is inside the circle
                            angle = math.atan2(sub_dy, sub_dx)

                            # Find which segment this belongs to
                            for i, (start_angle, end_angle) in enumerate(angles):
                                test_angle = angle
                                if test_angle < start_angle:
                                    test_angle += 2 * math.pi

                                test_end = end_angle
                                if test_end < start_angle:
                                    test_end += 2.6 * math.pi

                                if start_angle <= test_angle <= test_end:
                                    # Set the Braille dot
                                    if sub_x == 0:
                                        if sub_y == 0:
                                            pattern |= 0x01
                                        elif sub_y == 1:
                                            pattern |= 0x02
                                        elif sub_y == 2:
                                            pattern |= 0x04
                                        elif sub_y == 3:
                                            pattern |= 0x40
                                    else:
                                        if sub_y == 0:
                                            pattern |= 0x08
                                        elif sub_y == 1:
                                            pattern |= 0x10
                                        elif sub_y == 2:
                                            pattern |= 0x20
                                        elif sub_y == 3:
                                            pattern |= 0x80
                                    edge_color = colors[i]
                                    break

                # Place the Braille character if we have a pattern
                if pattern > 0 and edge_color:
                    canvas[y][x] = chr(braille_base + pattern)
                    canvas_colors[y][x] = edge_color


def generate_colors(
    n: int,
    scheme: str = "distinct",
    custom_colors: Optional[List[Tuple[int, int, int]]] = None
) -> List[Tuple[int, int, int]]:
    """Generate colors for the pie chart."""

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
        ]
        return palette[:n] if n <= len(palette) else palette * (n // len(palette) + 1)[:n]

    elif scheme == "gradient":
        # Rainbow gradient
        colors = []
        for i in range(n):
            hue = i / n
            r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
            colors.append((int(r * 255), int(g * 255), int(b * 255)))
        return colors

    elif scheme == "pastel":
        # Pastel colors
        colors = []
        for i in range(n):
            hue = i / n
            r, g, b = hsv_to_rgb(hue, 0.5, 0.95)
            colors.append((int(r * 255), int(g * 255), int(b * 255)))
        return colors

    else:
        return generate_colors(n, "distinct")


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert HSV to RGB color space."""
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)

    i = i % 6
    if i == 0:
        return v, t, p
    elif i == 1:
        return q, v, p
    elif i == 2:
        return p, v, t
    elif i == 3:
        return p, q, v
    elif i == 4:
        return t, p, v
    else:
        return v, p, q


def extract_pie_data(results: List[Dict[str, Any]]) -> Tuple[List[float], List[str]]:
    """Extract data for pie chart from query results."""
    if not results:
        return [], []

    # Same as waffle chart extraction
    first_row = results[0]
    keys = list(first_row.keys())

    label_col = None
    value_col = None

    for key in keys:
        key_lower = key.lower()
        if not label_col and any(word in key_lower for word in ['name', 'label', 'category', 'type', 'group', 'x']):
            label_col = key
        elif not value_col and any(word in key_lower for word in ['value', 'count', 'sum', 'total', 'amount', 'y']):
            value_col = key

    if not label_col and len(keys) >= 1:
        label_col = keys[0]
    if not value_col and len(keys) >= 2:
        value_col = keys[1]
    elif not value_col and len(keys) >= 1:
        value_col = keys[0]

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
    # Test the pie chart
    print("Pie Chart Examples")
    print("=" * 60)

    # Example 1: Simple pie chart
    print("\n1. MARKET SHARE (Block style):")
    print("-" * 60)
    values1 = [35, 25, 20, 15, 5]
    labels1 = ["Company A", "Company B", "Company C", "Company D", "Others"]
    print(render_pie_chart(
        values1, labels1,
        title="Market Share Distribution",
        radius=8,
        use_braille=False,
        show_percentages=True
    ))

    # Example 2: Braille edges for smoother appearance
    print("\n2. SALES BY REGION (Braille edges):")
    print("-" * 60)
    values2 = [120, 98, 77, 45]
    labels2 = ["North", "South", "East", "West"]
    print(render_pie_chart(
        values2, labels2,
        title="Regional Sales",
        radius=10,
        use_braille=True,
        show_percentages=True,
        color_scheme="gradient"
    ))

    # Example 3: Small pie chart
    print("\n3. TASK STATUS (Compact):")
    print("-" * 60)
    values3 = [65, 25, 10]
    labels3 = ["Completed", "In Progress", "Pending"]
    print(render_pie_chart(
        values3, labels3,
        title="Project Status",
        radius=6,
        use_braille=True,
        color_scheme="pastel"
    ))

    # Example 4: Many segments
    print("\n4. BUDGET ALLOCATION:")
    print("-" * 60)
    values4 = [30, 25, 15, 12, 8, 5, 5]
    labels4 = ["Engineering", "Sales", "Marketing", "Support", "HR", "Admin", "Other"]
    print(render_pie_chart(
        values4, labels4,
        title="Department Budget",
        radius=10,
        use_braille=True
    ))

    print("\n" + "=" * 60)
    print("Pie Chart Features:")
    print("- Unicode block and Braille characters for smooth curves")
    print("- True color support for clear segment distinction")
    print("- Automatic angle calculation for proportional segments")
    print("- Multiple rendering styles (blocks vs Braille edges)")
    print("- Perfect for low cardinality categorical data")
    print("=" * 60)
