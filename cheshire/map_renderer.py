#!/usr/bin/env python3
"""
ASCII/Unicode map renderer for geographic data visualization.
Uses Braille characters for precise points and block characters for density.
"""

import math
from typing import List, Tuple, Optional, Dict
from collections import defaultdict

# Braille dot patterns for sub-character resolution
# Each cell can show up to 8 dots in a 2x4 grid
BRAILLE_BASE = 0x2800
BRAILLE_DOTS = [
    [0x01, 0x08],  # Column 0 dots (top-bottom)
    [0x02, 0x10],  # Column 1 dots
    [0x04, 0x20],  # Column 2 dots
    [0x40, 0x80],  # Column 3 dots
]

# Block characters for density visualization
BLOCK_CHARS = [
    ' ',      # 0% density
    '░',      # 25% density
    '▒',      # 50% density
    '▓',      # 75% density
    '█',      # 100% density
]

# Half block characters for more precise density
HALF_BLOCKS = {
    'upper': '▀',
    'lower': '▄',
    'left': '▌',
    'right': '▐',
    'full': '█',
}

# Map boundary characters
MAP_BORDERS = {
    'horizontal': '─',
    'vertical': '│',
    'top_left': '┌',
    'top_right': '┐',
    'bottom_left': '└',
    'bottom_right': '┘',
    'cross': '┼',
}


class MapRenderer:
    """Renders geographic data as ASCII/Unicode maps."""

    def __init__(self, width: int = None, height: int = None, aspect_ratio: float = 2.0):
        """Initialize map renderer with dimensions.

        If width/height not specified, uses terminal size.

        Args:
            width: Canvas width in characters
            height: Canvas height in characters
            aspect_ratio: Character aspect ratio (height/width). Default 2.0 for typical terminals.
                         Adjust to 1.0 for square fonts or 2.5 for tall fonts.
        """
        if width is None or height is None:
            try:
                import os
                term_width = os.get_terminal_size().columns
                term_height = os.get_terminal_size().lines
                # Account for latitude/longitude labels when auto-sizing
                # Subtract 6 from width for longitude labels on the right
                # Subtract 3 from height for title and longitude labels at bottom
                width = width or (term_width - 15)
                height = height or (term_height - 13)
            except:
                width = width or 124
                height = height or 26

        self.width = width - 0  # Account for borders
        self.height = height - 1  # Account for borders and labels
        self.aspect_ratio = aspect_ratio
        self.canvas = [[' ' for _ in range(self.width)] for _ in range(self.height)]
        self.braille_canvas = [[0 for _ in range(self.width)] for _ in range(self.height)]
        self.block_canvas = [[{'upper': False, 'lower': False} for _ in range(self.width)] for _ in range(self.height)]
        self.density_map = [[0 for _ in range(self.width)] for _ in range(self.height)]

    def render_map(self, lats: List[float], lons: List[float],
                   values: Optional[List[float]] = None,
                   colors: Optional[List[str]] = None,
                   title: Optional[str] = None,
                   map_type: str = 'points',
                   center_on_density: bool = True) -> str:
        """Render geographic data as a map.

        Args:
            lats: Latitude values
            lons: Longitude values
            values: Optional values for each point (for heatmap/clustering)
            colors: Optional color categories for points
            title: Optional map title
            map_type: 'points', 'density', 'clusters', 'heatmap', or 'blocks_heatmap'
            center_on_density: Center view on highest concentration of points
        """
        if not lats or not lons:
            return "No data to display"

        # Calculate center and bounds based on density
        if center_on_density and len(lats) > 2:
            center_lat, center_lon, optimal_lat_range, optimal_lon_range = self._find_density_center(
                lats, lons, self.width, self.height, self.aspect_ratio
            )

            # Set bounds based on density center
            min_lat = center_lat - optimal_lat_range / 2
            max_lat = center_lat + optimal_lat_range / 2
            min_lon = center_lon - optimal_lon_range / 2
            max_lon = center_lon + optimal_lon_range / 2
        else:
            # Use traditional bounds (all points visible)
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)

            # Calculate data range
            lat_range = max_lat - min_lat
            lon_range = max_lon - min_lon

            # Apply aspect ratio correction
            # Terminal chars are ~2x taller than wide, so we need to REDUCE latitude range
            # to compensate for the visual stretching (zoom in vertically)
            if self.aspect_ratio > 1:
                # Reduce the latitude range to counteract tall characters
                lat_reduction = lat_range * (1 - 1 / self.aspect_ratio) * 0.5
                min_lat += lat_reduction
                max_lat -= lat_reduction

            # Add standard padding
            lat_padding = (max_lat - min_lat) * 0.1 or 1
            lon_padding = lon_range * 0.1 or 1

            min_lat -= lat_padding
            max_lat += lat_padding
            min_lon -= lon_padding
            max_lon += lon_padding

        # Calculate scale factors
        lat_scale = (self.height - 1) / (max_lat - min_lat)
        lon_scale = (self.width - 1) / (max_lon - min_lon)

        # Clear canvases
        self.canvas = [[' ' for _ in range(self.width)] for _ in range(self.height)]
        self.braille_canvas = [[0 for _ in range(self.width)] for _ in range(self.height)]
        self.block_canvas = [[{'upper': False, 'lower': False} for _ in range(self.width)] for _ in range(self.height)]
        self.density_map = [[0 for _ in range(self.width)] for _ in range(self.height)]

        # Plot points based on map type
        if map_type == 'density' or map_type == 'heatmap':
            self._plot_density(lats, lons, values, min_lat, min_lon, lat_scale, lon_scale)
        elif map_type == 'blocks_heatmap':
            self._plot_blocks_heatmap(lats, lons, values, min_lat, min_lon, lat_scale, lon_scale)
        elif map_type == 'braille_heatmap':
            self._plot_braille_heatmap(lats, lons, values, min_lat, min_lon, lat_scale, lon_scale)
        elif map_type == 'clusters':
            self._plot_clusters(lats, lons, colors, min_lat, min_lon, lat_scale, lon_scale)
        elif map_type == 'blocks':
            self._plot_blocks(lats, lons, colors, min_lat, min_lon, lat_scale, lon_scale)
        else:  # Default to points (Braille)
            self._plot_points(lats, lons, colors, min_lat, min_lon, lat_scale, lon_scale)

        # Build the output string
        return self._build_output(title, min_lat, max_lat, min_lon, max_lon, map_type)

    def _plot_points(self, lats: List[float], lons: List[float],
                     colors: Optional[List[str]],
                     min_lat: float, min_lon: float,
                     lat_scale: float, lon_scale: float):
        """Plot individual points using Braille characters for sub-character precision."""
        # Expanded color mapping for more values
        color_map = {
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
            'orange': '\033[38;5;208m',
            'purple': '\033[38;5;141m',
            'pink': '\033[38;5;213m',
            'brown': '\033[38;5;130m',
            'gray': '\033[90m',
            'grey': '\033[90m',
        }

        # Auto-assign colors to unique values if not standard colors
        unique_colors = {}
        if colors:
            for color in set(colors):
                if color and color.lower() not in color_map:
                    # Assign a color from a palette
                    palette = ['\033[91m', '\033[92m', '\033[93m', '\033[94m',
                               '\033[95m', '\033[96m', '\033[38;5;208m', '\033[38;5;141m']
                    color_idx = len(unique_colors) % len(palette)
                    unique_colors[color] = palette[color_idx]

        reset_color = '\033[0m'

        for i, (lat, lon) in enumerate(zip(lats, lons)):
            # Convert to canvas coordinates
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)

            if 0 <= x < self.width and 0 <= y < self.height:
                # For Braille, we can have 2x4 sub-character resolution
                # Calculate sub-position within the character cell
                sub_y = int((lat - min_lat) * lat_scale * 4) % 4
                sub_x = int((lon - min_lon) * lon_scale * 2) % 2

                # Set the appropriate Braille dot
                if sub_x < 2 and sub_y < 4:
                    self.braille_canvas[y][x] |= BRAILLE_DOTS[sub_y][sub_x]

                # Add color if specified
                if colors and i < len(colors) and colors[i]:
                    char = chr(BRAILLE_BASE + self.braille_canvas[y][x])
                    color_val = colors[i].lower() if isinstance(colors[i], str) else str(colors[i])

                    # Get color code
                    if color_val in color_map:
                        color_code = color_map[color_val]
                    elif colors[i] in unique_colors:
                        color_code = unique_colors[colors[i]]
                    else:
                        color_code = ''  # No color

                    if color_code:
                        self.canvas[y][x] = color_code + char + reset_color
                    else:
                        self.canvas[y][x] = char
                else:
                    self.canvas[y][x] = chr(BRAILLE_BASE + self.braille_canvas[y][x])

    def _plot_blocks(self, lats: List[float], lons: List[float],
                     colors: Optional[List[str]],
                     min_lat: float, min_lon: float,
                     lat_scale: float, lon_scale: float):
        """Plot points using half-block characters for a different visual style."""
        # Color mapping
        color_map = {
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
            'orange': '\033[38;5;208m',
            'purple': '\033[38;5;141m',
            'pink': '\033[38;5;213m',
            'brown': '\033[38;5;130m',
            'gray': '\033[90m',
            'grey': '\033[90m',
        }

        # Auto-assign colors to unique values
        unique_colors = {}
        if colors:
            for color in set(colors):
                if color and color.lower() not in color_map:
                    palette = ['\033[91m', '\033[92m', '\033[93m', '\033[94m',
                               '\033[95m', '\033[96m', '\033[38;5;208m', '\033[38;5;141m']
                    color_idx = len(unique_colors) % len(palette)
                    unique_colors[color] = palette[color_idx]

        reset_color = '\033[0m'

        # Store color info for each position
        color_grid = [[None for _ in range(self.width)] for _ in range(self.height)]

        for i, (lat, lon) in enumerate(zip(lats, lons)):
            # Convert to canvas coordinates
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)

            if 0 <= x < self.width and 0 <= y < self.height:
                # For half blocks, we have 2 vertical positions per character
                # Check if point is in upper or lower half of the cell
                y_fraction = ((lat - min_lat) * lat_scale * 2) % 2.0

                # Store which half to fill
                if y_fraction < 1.0:
                    self.block_canvas[y][x]['lower'] = True
                else:
                    self.block_canvas[y][x]['upper'] = True

                # Store color for this position
                if colors and i < len(colors) and colors[i]:
                    color_val = colors[i].lower() if isinstance(colors[i], str) else str(colors[i])
                    if color_val in color_map:
                        color_grid[y][x] = color_map[color_val]
                    elif colors[i] in unique_colors:
                        color_grid[y][x] = unique_colors[colors[i]]

        # Convert block_canvas to characters
        for y in range(self.height):
            for x in range(self.width):
                block = self.block_canvas[y][x]
                char = ' '

                if block['upper'] and block['lower']:
                    char = HALF_BLOCKS['full']
                elif block['upper']:
                    char = HALF_BLOCKS['upper']
                elif block['lower']:
                    char = HALF_BLOCKS['lower']

                # Apply color if available
                if char != ' ' and color_grid[y][x]:
                    self.canvas[y][x] = color_grid[y][x] + char + reset_color
                else:
                    self.canvas[y][x] = char

    def _plot_braille_heatmap(self, lats: List[float], lons: List[float],
                              values: Optional[List[float]],
                              min_lat: float, min_lon: float,
                              lat_scale: float, lon_scale: float):
        """Plot Braille points with true color gradient based on density."""
        # First, calculate density for each cell
        density_map = [[0 for _ in range(self.width)] for _ in range(self.height)]
        max_density = 0
        
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)
            
            if 0 <= x < self.width and 0 <= y < self.height:
                value = values[i] if values and i < len(values) else 1
                density_map[y][x] += value
                max_density = max(max_density, density_map[y][x])
        
        # Apply light smoothing to get neighborhood density
        smoothed_density = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for y in range(self.height):
            for x in range(self.width):
                total = density_map[y][x] * 4  # Center weight
                count = 4
                
                # Add neighboring cells
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < self.height and 0 <= nx < self.width:
                            total += density_map[ny][nx]
                            count += 1
                
                smoothed_density[y][x] = total / count
        
        # Update max density after smoothing
        max_density = 0
        for row in smoothed_density:
            for val in row:
                if val > 0:
                    max_density = max(max_density, val)
        
        # Now plot Braille points with gradient colors
        reset_color = '\033[0m'
        
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            # Convert to canvas coordinates
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)
            
            if 0 <= x < self.width and 0 <= y < self.height:
                # For Braille, we can have 2x4 sub-character resolution
                sub_y = int((lat - min_lat) * lat_scale * 4) % 4
                sub_x = int((lon - min_lon) * lon_scale * 2) % 2
                
                # Set the appropriate Braille dot
                if sub_x < 2 and sub_y < 4:
                    self.braille_canvas[y][x] |= BRAILLE_DOTS[sub_y][sub_x]
                
                # Calculate color based on local density
                local_density = smoothed_density[y][x]
                if local_density > 0 and max_density > 0:
                    # Normalize density (0 to 1)
                    normalized = local_density / max_density
                    
                    # Calculate RGB values for green->yellow->red gradient
                    if normalized <= 0.5:
                        # Green to Yellow (increase red)
                        r = int(normalized * 2 * 255)
                        g = 255
                        b = 0
                    else:
                        # Yellow to Red (decrease green)
                        r = 255
                        g = int((1 - (normalized - 0.5) * 2) * 255)
                        b = 0
                    
                    # Use true color ANSI escape sequence
                    color = f'\033[38;2;{r};{g};{b}m'
                    
                    # Apply color to the Braille character
                    char = chr(BRAILLE_BASE + self.braille_canvas[y][x])
                    self.canvas[y][x] = color + char + reset_color
                else:
                    # Low density - use dim green
                    char = chr(BRAILLE_BASE + self.braille_canvas[y][x])
                    self.canvas[y][x] = '\033[38;2;0;128;0m' + char + reset_color

    def _plot_blocks_heatmap(self, lats: List[float], lons: List[float],
                             values: Optional[List[float]],
                             min_lat: float, min_lon: float,
                             lat_scale: float, lon_scale: float):
        """Plot heatmap using full blocks with true color gradient."""
        # Calculate density for each cell
        max_density = 0
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)
            
            if 0 <= x < self.width and 0 <= y < self.height:
                value = values[i] if values and i < len(values) else 1
                self.density_map[y][x] += value
                max_density = max(max_density, self.density_map[y][x])
        
        # Apply lighter gaussian blur for smoother visualization (fewer iterations to maintain scale)
        self._smooth_density(iterations=2)
        
        # Recalculate max after smoothing
        max_density = 0
        for row in self.density_map:
            for val in row:
                if val > 0:
                    max_density = max(max_density, val)
        
        # Convert density to true color gradient blocks
        for y in range(self.height):
            for x in range(self.width):
                if self.density_map[y][x] > 0:
                    # Normalize density (0 to 1)
                    normalized = self.density_map[y][x] / max_density if max_density > 0 else 0
                    
                    # Calculate RGB values for green->yellow->red gradient
                    if normalized <= 0.5:
                        # Green to Yellow (increase red)
                        r = int(normalized * 2 * 255)
                        g = 255
                        b = 0
                    else:
                        # Yellow to Red (decrease green)
                        r = 255
                        g = int((1 - (normalized - 0.5) * 2) * 255)
                        b = 0
                    
                    # Use true color ANSI escape sequence
                    color = f'\033[38;2;{r};{g};{b}m'
                    
                    # Use full block character for solid appearance
                    self.canvas[y][x] = color + '█' + '\033[0m'
    
    def _plot_density(self, lats: List[float], lons: List[float],
                      values: Optional[List[float]],
                      min_lat: float, min_lon: float,
                      lat_scale: float, lon_scale: float):
        """Plot density map using block characters."""
        # Calculate density for each cell
        max_density = 0
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)

            if 0 <= x < self.width and 0 <= y < self.height:
                value = values[i] if values and i < len(values) else 1
                self.density_map[y][x] += value
                max_density = max(max_density, self.density_map[y][x])

        # Apply gaussian blur for smoother visualization
        self._smooth_density(iterations=2)

        # Convert density to block characters with color gradient
        for y in range(self.height):
            for x in range(self.width):
                if self.density_map[y][x] > 0:
                    # Normalize density
                    normalized = self.density_map[y][x] / max_density if max_density > 0 else 0

                    # Choose block character and color
                    block_idx = min(int(normalized * len(BLOCK_CHARS)), len(BLOCK_CHARS) - 1)

                    # Apply color gradient (blue -> cyan -> green -> yellow -> red)
                    if normalized < 0.2:
                        color = '\033[94m'  # Blue
                    elif normalized < 0.4:
                        color = '\033[96m'  # Cyan
                    elif normalized < 0.6:
                        color = '\033[92m'  # Green
                    elif normalized < 0.8:
                        color = '\033[93m'  # Yellow
                    else:
                        color = '\033[91m'  # Red

                    self.canvas[y][x] = color + BLOCK_CHARS[block_idx] + '\033[0m'

    def _plot_clusters(self, lats: List[float], lons: List[float],
                       colors: Optional[List[str]],
                       min_lat: float, min_lon: float,
                       lat_scale: float, lon_scale: float):
        """Plot clustered points using a combination of techniques."""
        # First, identify clusters
        clusters = self._identify_clusters(lats, lons, min_lat, min_lon, lat_scale, lon_scale)

        # Plot cluster centers with size indicators
        for cluster_id, points in clusters.items():
            if not points:
                continue

            # Calculate cluster center
            center_y = sum(p[0] for p in points) / len(points)
            center_x = sum(p[1] for p in points) / len(points)

            y = int(center_y)
            x = int(center_x)

            if 0 <= x < self.width and 0 <= y < self.height:
                # Use different characters based on cluster size
                size = len(points)
                if size < 5:
                    char = '•'
                elif size < 10:
                    char = '◉'
                elif size < 20:
                    char = '◎'
                else:
                    char = '⊕'

                # Color based on cluster ID or provided colors
                color_list = ['\033[91m', '\033[92m', '\033[93m', '\033[94m', '\033[95m', '\033[96m']
                color = color_list[cluster_id % len(color_list)]

                self.canvas[y][x] = color + char + '\033[0m'

                # Add cluster size label if significant
                if size >= 10 and x + 2 < self.width:
                    size_str = str(size)
                    for i, digit in enumerate(size_str[:min(3, self.width - x - 1)]):
                        self.canvas[y][x + i + 1] = '\033[90m' + digit + '\033[0m'

    def _identify_clusters(self, lats: List[float], lons: List[float],
                           min_lat: float, min_lon: float,
                           lat_scale: float, lon_scale: float,
                           threshold: float = 2.0) -> Dict[int, List[Tuple[int, int]]]:
        """Simple clustering based on proximity."""
        clusters = defaultdict(list)
        visited = set()
        cluster_id = 0

        points = []
        for lat, lon in zip(lats, lons):
            y = self.height - 1 - int((lat - min_lat) * lat_scale)
            x = int((lon - min_lon) * lon_scale)
            if 0 <= x < self.width and 0 <= y < self.height:
                points.append((y, x))

        for i, point in enumerate(points):
            if i in visited:
                continue

            # Start new cluster
            cluster = [point]
            visited.add(i)

            # Find nearby points
            for j, other in enumerate(points):
                if j in visited:
                    continue

                # Calculate distance
                dist = math.sqrt((point[0] - other[0])**2 + (point[1] - other[1])**2)
                if dist <= threshold:
                    cluster.append(other)
                    visited.add(j)

            clusters[cluster_id] = cluster
            cluster_id += 1

        return clusters

    def _find_density_center(self, lats: List[float], lons: List[float],
                             width: int, height: int, aspect_ratio: float,
                             target_coverage: float = 0.9) -> Tuple[float, float, float, float]:
        """Find the optimal center point and range to show desired percentage of points.

        Args:
            target_coverage: Percentage of points to include (default 0.8 = 80%)

        Returns:
            (center_lat, center_lon, optimal_lat_range, optimal_lon_range)
        """
        # Sort points by distance from centroid to find the core 80%
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)

        # Calculate distances from center for each point
        distances = []
        for lat, lon in zip(lats, lons):
            # Normalize by typical lat/lon aspect ratio
            lat_dist = (lat - center_lat)
            lon_dist = (lon - center_lon) * math.cos(math.radians(center_lat))
            dist = math.sqrt(lat_dist**2 + lon_dist**2)
            distances.append((dist, lat, lon))

        # Sort by distance and take the target percentage
        distances.sort()
        target_count = int(len(distances) * target_coverage)

        # Get the core points
        core_points = distances[:target_count]
        core_lats = [p[1] for p in core_points]
        core_lons = [p[2] for p in core_points]

        # Recalculate center based on core points only
        if core_lats:
            core_center_lat = sum(core_lats) / len(core_lats)
            core_center_lon = sum(core_lons) / len(core_lons)
        else:
            core_center_lat = center_lat
            core_center_lon = center_lon

        # Find the densest region using a grid approach for fine-tuning
        grid_size = 40
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Create grid cells
        lat_step = (max_lat - min_lat) / grid_size if max_lat > min_lat else 1
        lon_step = (max_lon - min_lon) / grid_size if max_lon > min_lon else 1

        # Count points in each grid cell
        grid_counts = {}
        for lat, lon in zip(lats, lons):
            lat_idx = int((lat - min_lat) / lat_step) if lat_step > 0 else 0
            lon_idx = int((lon - min_lon) / lon_step) if lon_step > 0 else 0
            lat_idx = min(max(0, lat_idx), grid_size - 1)
            lon_idx = min(max(0, lon_idx), grid_size - 1)
            key = (lat_idx, lon_idx)
            grid_counts[key] = grid_counts.get(key, 0) + 1

        # Find the peak density cell
        if grid_counts:
            max_cell = max(grid_counts.items(), key=lambda x: x[1])
            peak_lat_idx, peak_lon_idx = max_cell[0]
            peak_lat = min_lat + (peak_lat_idx + 0.5) * lat_step
            peak_lon = min_lon + (peak_lon_idx + 0.5) * lon_step

            # Blend core center with peak (70% core, 30% peak)
            final_center_lat = 0.9 * core_center_lat + 0.1 * peak_lat
            final_center_lon = 0.9 * core_center_lon + 0.1 * peak_lon
        else:
            final_center_lat = core_center_lat
            final_center_lon = core_center_lon

        # Calculate range to include target percentage of points
        # Use percentile-based approach
        sorted_lat_dists = sorted(abs(lat - final_center_lat) for lat in lats)
        sorted_lon_dists = sorted(abs(lon - final_center_lon) for lon in lons)

        # Get the distance that includes target_coverage of points
        percentile_idx = min(int(len(sorted_lat_dists) * target_coverage), len(sorted_lat_dists) - 1)

        optimal_lat_range = 2 * sorted_lat_dists[percentile_idx]
        optimal_lon_range = 2 * sorted_lon_dists[percentile_idx]

        # Apply aspect ratio correction
        if aspect_ratio > 1:
            optimal_lat_range = optimal_lat_range / aspect_ratio

        # Ensure minimum range - allow much smaller ranges for dense areas
        # Only enforce a tiny minimum to prevent division by zero
        optimal_lat_range = max(0.001, optimal_lat_range)
        optimal_lon_range = max(0.001, optimal_lon_range)

        # Add small padding for visual breathing room
        optimal_lat_range *= 1.33
        optimal_lon_range *= 1.8

        return final_center_lat, final_center_lon, optimal_lat_range, optimal_lon_range

    def _smooth_density(self, iterations: int = 7):
        """Apply smoothing to density map for better visualization."""
        for _ in range(iterations):
            new_density = [[0 for _ in range(self.width)] for _ in range(self.height)]

            for y in range(self.height):
                for x in range(self.width):
                    total = self.density_map[y][x] * 4  # Center weight
                    count = 4

                    # Add neighboring cells
                    for dy in [-1, 0, 1]:
                        for dx in [-1, 0, 1]:
                            if dy == 0 and dx == 0:
                                continue
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < self.height and 0 <= nx < self.width:
                                total += self.density_map[ny][nx]
                                count += 1

                    new_density[y][x] = total / count

            self.density_map = new_density

    def _build_output(self, title: Optional[str],
                      min_lat: float, max_lat: float,
                      min_lon: float, max_lon: float,
                      map_type: str) -> str:
        """Build the final output string with borders and labels."""
        lines = []

        # Add title
        if title:
            lines.append(f"\033[1m{title.center(self.width + 2)}\033[0m")

        # Add top border with longitude labels
        top_border = MAP_BORDERS['top_left'] + MAP_BORDERS['horizontal'] * self.width + MAP_BORDERS['top_right']
        lines.append(top_border)

        # Add latitude labels and map content
        for y in range(self.height):
            # Calculate latitude for this row
            lat = max_lat - (y / (self.height - 1)) * (max_lat - min_lat)

            # Build row
            row = MAP_BORDERS['vertical']
            for x in range(self.width):
                row += self.canvas[y][x] if len(self.canvas[y][x]) > 1 else self.canvas[y][x]
            row += MAP_BORDERS['vertical']

            # Add latitude label every 5 rows
            if y % 5 == 0:
                row += f" {lat:6.2f}°"

            lines.append(row)

        # Add bottom border
        bottom_border = MAP_BORDERS['bottom_left'] + MAP_BORDERS['horizontal'] * self.width + MAP_BORDERS['bottom_right']
        lines.append(bottom_border)

        # Add longitude labels
        lon_labels = " "
        label_spacing = max(1, self.width // 5)
        for x in range(0, self.width, label_spacing):
            lon = min_lon + (x / (self.width - 1)) * (max_lon - min_lon)
            label = f"{lon:6.1f}°"
            lon_labels += label.ljust(label_spacing)
        lines.append(lon_labels[:self.width + 2])

        # Add legend based on map type
        if map_type == 'density' or map_type == 'heatmap':
            lines.append("")
            lines.append("Density: " +
                         "\033[94m" + BLOCK_CHARS[1] + "\033[0m Low  " +
                         "\033[96m" + BLOCK_CHARS[2] + "\033[0m  " +
                         "\033[92m" + BLOCK_CHARS[3] + "\033[0m  " +
                         "\033[93m" + BLOCK_CHARS[4] + "\033[0m  " +
                         "\033[91m" + BLOCK_CHARS[4] + "\033[0m High")
        elif map_type == 'blocks_heatmap':
            lines.append("")
            # True color gradient legend
            lines.append("Density: " +
                         "\033[38;2;0;255;0m█\033[0m Low  " +
                         "\033[38;2;128;255;0m█\033[0m  " +
                         "\033[38;2;255;255;0m█\033[0m Medium  " +
                         "\033[38;2;255;128;0m█\033[0m  " +
                         "\033[38;2;255;0;0m█\033[0m High")
        elif map_type == 'braille_heatmap':
            lines.append("")
            # True color gradient legend with Braille
            lines.append("Density: " +
                         "\033[38;2;0;255;0m⣿\033[0m Low  " +
                         "\033[38;2;128;255;0m⣿\033[0m  " +
                         "\033[38;2;255;255;0m⣿\033[0m Medium  " +
                         "\033[38;2;255;128;0m⣿\033[0m  " +
                         "\033[38;2;255;0;0m⣿\033[0m High")
        elif map_type == 'clusters':
            lines.append("")
            lines.append("Clusters: • <5 points  ◉ 5-10  ◎ 10-20  ⊕ >20")

        return "\n".join(lines)


def render_map(lats: List[float], lons: List[float],
               values: Optional[List[float]] = None,
               colors: Optional[List[str]] = None,
               width: int = None, height: int = None,
               title: Optional[str] = None,
               map_type: str = 'points',
               aspect_ratio: float = 0.45,
               center_on_density: bool = True) -> str:
    """Convenience function to render a map.

    If width/height not specified, uses full terminal size.

    Args:
        aspect_ratio: Character aspect ratio (height/width). Default 2.0.
                     Adjust to compensate for terminal font proportions.
        center_on_density: Center view on highest concentration of points.
    """
    renderer = MapRenderer(width, height, aspect_ratio)
    return renderer.render_map(lats, lons, values, colors, title, map_type, center_on_density)
