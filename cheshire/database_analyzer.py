#!/usr/bin/env python3
"""
Database Analyzer for cheshire
Analyzes database tables to recommend appropriate visualizations
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import duckdb
from .db_connectors import create_connector, execute_query_compat


class ColumnAnalysis:
    """Analysis results for a single column"""
    def __init__(self, name: str, data_type: str):
        self.name = name
        self.data_type = data_type
        self.sql_type = None
        self.is_date = False
        self.is_numeric = False
        self.is_dimension = False
        self.is_measure = False
        self.is_latitude = False
        self.is_longitude = False
        self.is_geographic = False
        self.cardinality = 0
        self.null_count = 0
        self.total_count = 0
        self.min_value = None
        self.max_value = None
        self.avg_value = None
        self.sample_values = []
        self.date_format = None
        self.date_range_days = None
        self.recommended_for = []  # Chart types this column is good for
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'data_type': self.data_type,
            'sql_type': self.sql_type,
            'is_date': self.is_date,
            'is_numeric': self.is_numeric,
            'is_dimension': self.is_dimension,
            'is_measure': self.is_measure,
            'is_latitude': self.is_latitude,
            'is_longitude': self.is_longitude,
            'is_geographic': self.is_geographic,
            'cardinality': self.cardinality,
            'null_count': self.null_count,
            'total_count': self.total_count,
            'min_value': str(self.min_value) if self.min_value else None,
            'max_value': str(self.max_value) if self.max_value else None,
            'avg_value': float(self.avg_value) if self.avg_value else None,
            'sample_values': [str(v) for v in self.sample_values],
            'date_format': self.date_format,
            'date_range_days': self.date_range_days,
            'recommended_for': self.recommended_for
        }


class TableAnalysis:
    """Analysis results for a single table"""
    def __init__(self, name: str):
        self.name = name
        self.row_count = 0
        self.columns: Dict[str, ColumnAnalysis] = {}
        self.recommended_charts = []  # List of (chart_type, config) tuples
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'row_count': self.row_count,
            'columns': {name: col.to_dict() for name, col in self.columns.items()},
            'recommended_charts': self.recommended_charts
        }


class DatabaseAnalyzer:
    """Analyzes database schema and data to recommend visualizations"""
    
    def __init__(self, db_config: Any, db_type: str = 'duckdb', db_name: Optional[str] = None):
        self.db_config = db_config
        self.db_type = db_type
        self.db_name = db_name
        self.analysis_results: Dict[str, TableAnalysis] = {}
        
    def analyze(self) -> Dict[str, TableAnalysis]:
        """Run full analysis on all tables"""
        print("🔍 Starting database analysis...")
        
        # Get all tables
        tables = self._get_tables()
        print(f"Found {len(tables)} tables to analyze")
        
        for table_name in tables:
            print(f"\n📊 Analyzing table: {table_name}")
            self._analyze_table(table_name)
            
        # Generate recommendations
        print("\n💡 Generating chart recommendations...")
        self._generate_recommendations()
        
        return self.analysis_results
    
    def _get_tables(self) -> List[str]:
        """Get list of all tables in database"""
        if self.db_type == 'duckdb':
            query = "SHOW TABLES"
        elif self.db_type == 'sqlite':
            query = "SELECT name FROM sqlite_master WHERE type='table'"
        else:
            query = "SHOW TABLES"
            
        results = execute_query_compat(query, self.db_config)
        tables = []
        for row in results:
            if isinstance(row, dict):
                table_name = row.get('name') or list(row.values())[0]
            else:
                table_name = str(row)
            tables.append(table_name)
        
        return tables
    
    def _analyze_table(self, table_name: str) -> None:
        """Analyze a single table"""
        analysis = TableAnalysis(table_name)
        
        # Get row count
        count_query = f"SELECT COUNT(*) as cnt FROM {table_name}"
        results = execute_query_compat(count_query, self.db_config)
        if results:
            analysis.row_count = results[0].get('cnt', 0)
        
        print(f"  Row count: {analysis.row_count:,}")
        
        # Get columns
        if self.db_type == 'duckdb':
            columns_query = f"DESCRIBE {table_name}"
        elif self.db_type == 'sqlite':
            columns_query = f"PRAGMA table_info({table_name})"
        else:
            columns_query = f"DESCRIBE {table_name}"
            
        columns = execute_query_compat(columns_query, self.db_config)
        
        # Analyze each column
        for col_info in columns:
            if self.db_type == 'duckdb':
                col_name = col_info.get('column_name', '')
                col_type = col_info.get('column_type', '')
            elif self.db_type == 'sqlite':
                col_name = col_info.get('name', '')
                col_type = col_info.get('type', '')
            else:
                col_name = list(col_info.values())[0]
                col_type = list(col_info.values())[1] if len(col_info.values()) > 1 else ''
                
            if col_name:
                print(f"  Analyzing column: {col_name} ({col_type})")
                col_analysis = self._analyze_column(table_name, col_name, col_type)
                analysis.columns[col_name] = col_analysis
        
        self.analysis_results[table_name] = analysis
    
    def _analyze_column(self, table_name: str, col_name: str, col_type: str) -> ColumnAnalysis:
        """Analyze a single column"""
        analysis = ColumnAnalysis(col_name, col_type)
        analysis.sql_type = col_type
        
        # Determine basic type
        col_type_upper = col_type.upper()
        if any(t in col_type_upper for t in ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL', 'NUMERIC', 'REAL']):
            analysis.is_numeric = True
        elif any(t in col_type_upper for t in ['DATE', 'TIME', 'TIMESTAMP']):
            analysis.is_date = True
            
        # Get basic statistics
        try:
            # Count total and nulls
            stats_query = f"""
            SELECT 
                COUNT(*) as total,
                COUNT({col_name}) as non_null,
                COUNT(DISTINCT {col_name}) as distinct_count
            FROM {table_name}
            """
            results = execute_query_compat(stats_query, self.db_config)
            if results:
                stats = results[0]
                analysis.total_count = stats.get('total', 0)
                analysis.null_count = analysis.total_count - stats.get('non_null', 0)
                analysis.cardinality = stats.get('distinct_count', 0)
            
            # Get sample values
            sample_query = f"""
            SELECT DISTINCT {col_name} as val
            FROM {table_name}
            WHERE {col_name} IS NOT NULL
            LIMIT 10
            """
            results = execute_query_compat(sample_query, self.db_config)
            analysis.sample_values = [row.get('val') for row in results if row.get('val') is not None]
            
            # Numeric column analysis
            if analysis.is_numeric:
                numeric_query = f"""
                SELECT 
                    MIN(CAST({col_name} AS DOUBLE)) as min_val,
                    MAX(CAST({col_name} AS DOUBLE)) as max_val,
                    AVG(CAST({col_name} AS DOUBLE)) as avg_val
                FROM {table_name}
                WHERE {col_name} IS NOT NULL
                """
                results = execute_query_compat(numeric_query, self.db_config)
                if results:
                    stats = results[0]
                    analysis.min_value = stats.get('min_val')
                    analysis.max_value = stats.get('max_val')
                    analysis.avg_value = stats.get('avg_val')
                    
                    # Check if this might be latitude or longitude
                    if self._is_geographic_column(col_name, analysis.min_value, analysis.max_value):
                        analysis.is_geographic = True
                        if self._is_latitude_column(col_name, analysis.min_value, analysis.max_value):
                            analysis.is_latitude = True
                        elif self._is_longitude_column(col_name, analysis.min_value, analysis.max_value):
                            analysis.is_longitude = True
                    
                # Numeric columns are usually measures (unless geographic)
                if not analysis.is_geographic:
                    analysis.is_measure = True
                else:
                    analysis.is_dimension = True
                
            # Date column analysis
            elif analysis.is_date:
                date_query = f"""
                SELECT 
                    MIN({col_name}) as min_date,
                    MAX({col_name}) as max_date
                FROM {table_name}
                WHERE {col_name} IS NOT NULL
                """
                results = execute_query_compat(date_query, self.db_config)
                if results:
                    stats = results[0]
                    analysis.min_value = stats.get('min_date')
                    analysis.max_value = stats.get('max_date')
                    
                    # Calculate date range in days
                    try:
                        if analysis.min_value and analysis.max_value:
                            min_date = self._parse_date(str(analysis.min_value))
                            max_date = self._parse_date(str(analysis.max_value))
                            if min_date and max_date:
                                analysis.date_range_days = (max_date - min_date).days
                    except:
                        pass
                        
                # Dates are dimensions
                analysis.is_dimension = True
                
            # Text column analysis
            else:
                # Check if it might be a date stored as text
                if analysis.sample_values and self._looks_like_date(analysis.sample_values[0]):
                    analysis.is_date = True
                    analysis.is_dimension = True
                    analysis.date_format = self._detect_date_format(analysis.sample_values[0])
                else:
                    # Low cardinality text columns are dimensions
                    if analysis.cardinality > 0 and analysis.cardinality <= 100:
                        analysis.is_dimension = True
                        
            # Determine dimension vs measure for remaining cases
            if not analysis.is_dimension and not analysis.is_measure:
                # High cardinality suggests IDs or measures
                cardinality_ratio = analysis.cardinality / max(analysis.total_count, 1)
                if cardinality_ratio > 0.5:
                    # Likely an ID column
                    pass
                else:
                    # Low cardinality = dimension
                    analysis.is_dimension = True
                    
        except Exception as e:
            print(f"    Warning: Error analyzing column {col_name}: {e}")
            
        return analysis
    
    def _is_geographic_column(self, col_name: str, min_val: float, max_val: float) -> bool:
        """Check if a column appears to contain geographic coordinates."""
        if min_val is None or max_val is None:
            return False
            
        col_lower = col_name.lower()
        
        # Check column name patterns
        geo_patterns = ['lat', 'lon', 'latitude', 'longitude', 'coord', 'geo', 
                       'location', 'position', 'gps', 'y_coord', 'x_coord']
        
        has_geo_name = any(pattern in col_lower for pattern in geo_patterns)
        
        # Check value ranges
        is_lat_range = -90 <= min_val <= 90 and -90 <= max_val <= 90
        is_lon_range = -180 <= min_val <= 180 and -180 <= max_val <= 180
        
        return has_geo_name and (is_lat_range or is_lon_range)
    
    def _is_latitude_column(self, col_name: str, min_val: float, max_val: float) -> bool:
        """Check if column is specifically latitude."""
        if min_val is None or max_val is None:
            return False
            
        col_lower = col_name.lower()
        
        # Strong latitude indicators
        if any(x in col_lower for x in ['lat', 'latitude', 'y_coord', 'y_pos']):
            return -90 <= min_val <= 90 and -90 <= max_val <= 90
            
        # If just called 'y' and in latitude range
        if col_lower == 'y' and -90 <= min_val <= 90 and -90 <= max_val <= 90:
            return True
            
        return False
    
    def _is_longitude_column(self, col_name: str, min_val: float, max_val: float) -> bool:
        """Check if column is specifically longitude."""
        if min_val is None or max_val is None:
            return False
            
        col_lower = col_name.lower()
        
        # Strong longitude indicators
        if any(x in col_lower for x in ['lon', 'lng', 'long', 'longitude', 'x_coord', 'x_pos']):
            return -180 <= min_val <= 180 and -180 <= max_val <= 180
            
        # If just called 'x' and in longitude range
        if col_lower == 'x' and -180 <= min_val <= 180 and -180 <= max_val <= 180:
            return True
            
        return False
    
    def _looks_like_date(self, value: Any) -> bool:
        """Check if a value looks like a date"""
        if not value:
            return False
        value_str = str(value)
        # Common date patterns
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY or DD/MM/YYYY
            r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
            r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY or MM-DD-YYYY
        ]
        return any(re.match(pattern, value_str) for pattern in date_patterns)
    
    def _detect_date_format(self, value: Any) -> Optional[str]:
        """Detect the date format of a value"""
        if not value:
            return None
        value_str = str(value)
        
        formats = [
            ('%Y-%m-%d', 'YYYY-MM-DD'),
            ('%Y/%m/%d', 'YYYY/MM/DD'),
            ('%d/%m/%Y', 'DD/MM/YYYY'),
            ('%m/%d/%Y', 'MM/DD/YYYY'),
            ('%d-%m-%Y', 'DD-MM-YYYY'),
            ('%m-%d-%Y', 'MM-DD-YYYY'),
            ('%Y-%m-%d %H:%M:%S', 'YYYY-MM-DD HH:MM:SS'),
        ]
        
        for fmt, name in formats:
            try:
                datetime.strptime(value_str.split('.')[0], fmt)
                return name
            except:
                continue
        return None
    
    def _parse_date(self, value: str) -> Optional[datetime]:
        """Parse a date string"""
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y-%m-%d %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(value.split('.')[0], fmt)
            except:
                continue
        return None
    
    def _generate_recommendations(self) -> None:
        """Generate chart recommendations for each table"""
        for table_name, table_analysis in self.analysis_results.items():
            recommendations = []
            
            # Find date columns
            date_cols = [col for col in table_analysis.columns.values() if col.is_date]
            
            # Find numeric columns (measures)
            numeric_cols = [col for col in table_analysis.columns.values() if col.is_numeric]
            
            # Find dimension columns (excluding geographic ones)
            dimension_cols = [col for col in table_analysis.columns.values() 
                            if col.is_dimension and not col.is_date and not col.is_geographic]
            
            # Find all string columns that might be dimensions (including high cardinality)
            string_cols = [col for col in table_analysis.columns.values()
                          if not col.is_numeric and not col.is_date]
            
            # Find geographic columns
            lat_cols = [col for col in table_analysis.columns.values() if col.is_latitude]
            lon_cols = [col for col in table_analysis.columns.values() if col.is_longitude]
            geo_cols = [col for col in table_analysis.columns.values() if col.is_geographic]
            
            # Generate map recommendations if we have lat/lon pairs
            if lat_cols and lon_cols:
                lat_col = lat_cols[0]  # Use first lat column found
                lon_col = lon_cols[0]  # Use first lon column found
                
                # Points map (Braille - higher precision)
                recommendations.append({
                    'chart_type': 'map_points',
                    'title': f'{table_name}: Geographic Distribution (Braille)',
                    'description': f'High-precision map with Braille dots showing points from {table_name}',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.98
                })
                
                # Blocks map (more visible)
                recommendations.append({
                    'chart_type': 'map_blocks',
                    'title': f'{table_name}: Geographic Distribution (Blocks)',
                    'description': f'Map with solid blocks showing points from {table_name}',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.97
                })
                
                # Density map
                recommendations.append({
                    'chart_type': 'map_density',
                    'title': f'{table_name}: Density Heatmap',
                    'description': f'Geographic density visualization of {table_name}',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, 1 as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.96
                })
                
                # Clusters map
                recommendations.append({
                    'chart_type': 'map_clusters',
                    'title': f'{table_name}: Location Clusters',
                    'description': f'Clustered view of geographic points in {table_name}',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.94
                })
                
                # If there are categorical dimensions, suggest colored maps
                # Sort dimensions by cardinality (lower is better for colors)
                color_dims = [col for col in dimension_cols if not col.is_geographic]
                color_dims.sort(key=lambda x: (x.cardinality > 30, x.cardinality))
                
                # Generate maps for more low-cardinality dimensions
                for i, dim_col in enumerate(color_dims[:6]):  # Increase to 6 dimensions
                    # Include dimensions up to 30 cardinality (was 10)
                    if 1 < dim_col.cardinality <= 30:
                        # Calculate score based on position and cardinality
                        base_score = 0.93 - (i * 0.015)  # Small decrease for each dimension
                        if dim_col.cardinality > 15:
                            base_score -= 0.02  # Small penalty for higher cardinality
                        
                        # Braille version
                        recommendations.append({
                            'chart_type': 'map_points',
                            'title': f'{table_name}: Map by {dim_col.name} (Braille)',
                            'description': f'Geographic points colored by {dim_col.name} ({dim_col.cardinality} values) using Braille dots',
                            'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {dim_col.name} as color FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {dim_col.name} IS NOT NULL",
                            'score': base_score
                        })
                        # Blocks version
                        recommendations.append({
                            'chart_type': 'map_blocks',
                            'title': f'{table_name}: Map by {dim_col.name} (Blocks)',
                            'description': f'Geographic points colored by {dim_col.name} ({dim_col.cardinality} values) using solid blocks',
                            'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {dim_col.name} as color FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {dim_col.name} IS NOT NULL",
                            'score': base_score - 0.005
                        })
                
                # Also suggest combined dimensions for richer coloring
                if len(color_dims) >= 2:
                    # Find pairs of very low cardinality dimensions that combine well
                    for dim1 in color_dims[:3]:
                        for dim2 in color_dims[:3]:
                            if dim1 != dim2 and dim1.cardinality <= 5 and dim2.cardinality <= 5:
                                combined_card = dim1.cardinality * dim2.cardinality
                                if combined_card <= 20:
                                    recommendations.append({
                                        'chart_type': 'map_points',
                                        'title': f'{table_name}: Map by {dim1.name}+{dim2.name} (Braille)',
                                        'description': f'Points colored by {dim1.name} and {dim2.name} combination',
                                        'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {dim1.name} || '-' || {dim2.name} as color FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {dim1.name} IS NOT NULL AND {dim2.name} IS NOT NULL",
                                        'score': 0.89
                                    })
                                    recommendations.append({
                                        'chart_type': 'map_blocks',
                                        'title': f'{table_name}: Map by {dim1.name}+{dim2.name} (Blocks)',
                                        'description': f'Points colored by {dim1.name} and {dim2.name} combination',
                                        'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {dim1.name} || '-' || {dim2.name} as color FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {dim1.name} IS NOT NULL AND {dim2.name} IS NOT NULL",
                                        'score': 0.885
                                    })
                                    break  # Only one combination per dim1
                
                # Always add COUNT-based density/heatmap as it's often most useful
                recommendations.append({
                    'chart_type': 'map_density',
                    'title': f'{table_name}: Point Density Map',
                    'description': f'Density heatmap showing concentration of records',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, 1 as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.95
                })
                
                recommendations.append({
                    'chart_type': 'map_blocks_heatmap',
                    'title': f'{table_name}: True Color Heatmap',
                    'description': f'True color gradient heatmap (green-yellow-red) showing record density',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, 1 as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.96
                })
                
                # Add Braille heatmap visualization
                recommendations.append({
                    'chart_type': 'map_braille_heatmap',
                    'title': f'{table_name}: Braille Heatmap',
                    'description': f'Braille points with density-based color gradient',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, 1 as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.95
                })
                
                recommendations.append({
                    'chart_type': 'map_heatmap',
                    'title': f'{table_name}: Record Count Heatmap',
                    'description': f'Geographic heatmap showing record count distribution',
                    'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, 1 as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL",
                    'score': 0.94
                })
                
                # If there are numeric measures, suggest value-based heatmaps
                for num_col in numeric_cols[:2]:  # Limit to 2 best measures
                    if not num_col.is_geographic:  # Don't use lat/lon as values
                        recommendations.append({
                            'chart_type': 'map_blocks_heatmap',
                            'title': f'{table_name}: {num_col.name} True Color Heatmap',
                            'description': f'True color gradient heatmap showing {num_col.name} values',
                            'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {num_col.name} as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {num_col.name} IS NOT NULL",
                            'score': 0.93
                        })
                        
                        recommendations.append({
                            'chart_type': 'map_braille_heatmap',
                            'title': f'{table_name}: {num_col.name} Braille Heatmap',
                            'description': f'Braille points colored by {num_col.name} values',
                            'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {num_col.name} as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {num_col.name} IS NOT NULL",
                            'score': 0.92
                        })
                        
                        recommendations.append({
                            'chart_type': 'map_heatmap',
                            'title': f'{table_name}: {num_col.name} Heatmap',
                            'description': f'Geographic heatmap showing {num_col.name} distribution',
                            'sql': f"SELECT {lat_col.name} as lat, {lon_col.name} as lon, {num_col.name} as value FROM {table_name} WHERE {lat_col.name} IS NOT NULL AND {lon_col.name} IS NOT NULL AND {num_col.name} IS NOT NULL",
                            'score': 0.92
                        })
            
            # Simple table metrics (figlet)
            recommendations.append({
                'chart_type': 'figlet',
                'title': f'{table_name}: Total Record Count',
                'description': f'Count of all records in {table_name}',
                'sql': f"SELECT COUNT(*) as x, COUNT(*) as y FROM {table_name}",
                'score': 0.95
            })
            
            # Dimension analysis - COUNT(*) for all low/medium cardinality dimensions
            for dim_col in dimension_cols:
                if dim_col.cardinality <= 50 and dim_col.cardinality > 1:
                    # Bar chart for counts
                    recommendations.append({
                        'chart_type': 'bar',
                        'title': f'{table_name}: Record Count by {dim_col.name}',
                        'description': f'Count of records grouped by {dim_col.name}',
                        'sql': f"SELECT {dim_col.name} as x, COUNT(*) as y FROM {table_name} GROUP BY 1 ORDER BY 2 DESC",
                        'x_column': dim_col.name,
                        'y_column': 'count',
                        'score': 0.9
                    })
                    
                    # Termgraph horizontal bar for counts
                    recommendations.append({
                        'chart_type': 'tg_bar',
                        'title': f'{table_name}: Count by {dim_col.name} (Horizontal Bar)',
                        'description': f'Horizontal bar chart showing record counts by {dim_col.name}',
                        'sql': f"SELECT {dim_col.name} as x, COUNT(*) as y FROM {table_name} WHERE {dim_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
                        'x_column': dim_col.name,
                        'y_column': 'count',
                        'score': 0.85
                    })
                    
                    # Simple bar for smaller cardinality
                    if dim_col.cardinality <= 10:
                        recommendations.append({
                            'chart_type': 'simple_bar',
                            'title': f'{table_name}: {dim_col.name} Distribution',
                            'description': f'Simple bar chart of {dim_col.name} counts',
                            'sql': f"SELECT {dim_col.name} as x, COUNT(*) as y FROM {table_name} WHERE {dim_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                            'x_column': dim_col.name,
                            'y_column': 'count',
                            'score': 0.87
                        })
            
            # Matrix heatmap recommendations for pairs of low-cardinality dimensions
            low_card_dims = [col for col in dimension_cols if 2 <= col.cardinality <= 20]
            
            # Look for date-like columns (YEAR, MONTH, etc.)
            date_like_dims = []
            for col in dimension_cols:
                col_upper = col.name.upper()
                if any(term in col_upper for term in ['YEAR', 'MONTH', 'QUARTER', 'WEEK', 'DAY', 'HOUR']):
                    if col.cardinality <= 50:
                        date_like_dims.append(col)
            
            # Generate matrix heatmaps for dimension pairs
            if len(low_card_dims) >= 2:
                # Take best dimension pairs (prioritize date-like dimensions)
                priority_dims = date_like_dims[:2] if len(date_like_dims) >= 2 else []
                other_dims = [d for d in low_card_dims if d not in date_like_dims]
                
                dim_pairs = []
                
                # First priority: date x date combinations
                if len(date_like_dims) >= 2:
                    for i in range(len(date_like_dims)-1):
                        for j in range(i+1, min(i+2, len(date_like_dims))):
                            dim_pairs.append((date_like_dims[i], date_like_dims[j]))
                
                # Second priority: date x other dimension
                if date_like_dims and other_dims:
                    for date_dim in date_like_dims[:2]:
                        for other_dim in other_dims[:2]:
                            dim_pairs.append((date_dim, other_dim))
                
                # Third priority: other dimension pairs
                if len(other_dims) >= 2:
                    for i in range(min(2, len(other_dims)-1)):
                        for j in range(i+1, min(i+2, len(other_dims))):
                            dim_pairs.append((other_dims[i], other_dims[j]))
                
                # Generate recommendations for top dimension pairs
                for dim1, dim2 in dim_pairs[:3]:  # Limit to 3 matrix heatmaps
                    recommendations.append({
                        'chart_type': 'matrix_heatmap',
                        'title': f'{table_name}: {dim1.name} vs {dim2.name} Heatmap',
                        'description': f'Matrix heatmap showing record counts by {dim1.name} and {dim2.name}',
                        'sql': f"SELECT {dim1.name} as x, {dim2.name} as y, COUNT(*) as value FROM {table_name} WHERE {dim1.name} IS NOT NULL AND {dim2.name} IS NOT NULL GROUP BY 1, 2",
                        'x_column': dim1.name,
                        'y_column': dim2.name,
                        'score': 0.88 + (0.03 if dim1 in date_like_dims or dim2 in date_like_dims else 0)
                    })
                    
                    # If there are numeric measures, also suggest value-based matrix heatmaps
                    for num_col in numeric_cols[:1]:  # Just top measure
                        if not num_col.is_geographic:
                            recommendations.append({
                                'chart_type': 'matrix_heatmap',
                                'title': f'{table_name}: {num_col.name} by {dim1.name} vs {dim2.name}',
                                'description': f'Matrix heatmap showing sum of {num_col.name} by dimensions',
                                'sql': f"SELECT {dim1.name} as x, {dim2.name} as y, SUM({num_col.name}) as value FROM {table_name} WHERE {dim1.name} IS NOT NULL AND {dim2.name} IS NOT NULL AND {num_col.name} IS NOT NULL GROUP BY 1, 2",
                                'x_column': dim1.name,
                                'y_column': dim2.name,
                                'value_column': num_col.name,
                                'score': 0.85 + (0.03 if dim1 in date_like_dims or dim2 in date_like_dims else 0)
                            })
            
            # Pie and Waffle chart recommendations for low-cardinality dimensions
            suitable_pie_dims = [col for col in dimension_cols if 2 <= col.cardinality <= 8]
            suitable_waffle_dims = [col for col in dimension_cols if 2 <= col.cardinality <= 10]
            
            # Pie charts for the lowest cardinality dimensions
            if suitable_pie_dims:
                for dim in suitable_pie_dims[:1]:  # Limit to 1 pie chart per table
                    recommendations.append({
                        'chart_type': 'pie',
                        'title': f'{table_name}: {dim.name} Distribution',
                        'description': f'Pie chart showing proportion of records by {dim.name}',
                        'sql': f"SELECT {dim.name} as x, COUNT(*) as y FROM {table_name} WHERE {dim.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                        'x_column': 'x',
                        'y_column': 'y',
                        'score': 0.83
                    })
            
            # Waffle charts
            if suitable_waffle_dims:
                for dim in suitable_waffle_dims[:2]:  # Limit to 2 waffle charts per table
                    # Waffle with COUNT(*)
                    recommendations.append({
                        'chart_type': 'waffle',
                        'title': f'{table_name}: {dim.name} Distribution',
                        'description': f'Waffle chart showing proportion of records by {dim.name}',
                        'sql': f"SELECT {dim.name} as x, COUNT(*) as y FROM {table_name} WHERE {dim.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                        'x_column': 'x',
                        'y_column': 'y',
                        'score': 0.82
                    })
                    
                    # Waffle with a measure if available
                    if numeric_cols:
                        measure = numeric_cols[0]
                        recommendations.append({
                            'chart_type': 'waffle',
                            'title': f'{table_name}: {measure.name} by {dim.name}',
                            'description': f'Waffle chart showing {measure.name} proportions by {dim.name}',
                            'sql': f"SELECT {dim.name} as x, SUM({measure.name}) as y FROM {table_name} WHERE {dim.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                            'x_column': 'x',
                            'y_column': 'y',
                            'score': 0.81
                        })
            
            # Add recommendations for medium-high cardinality string dimensions
            for str_col in string_cols:
                if 50 < str_col.cardinality <= 200:  # Medium-high cardinality
                    # Top N values
                    recommendations.append({
                        'chart_type': 'bar',
                        'title': f'{table_name}: Top 20 {str_col.name} by Count',
                        'description': f'Top 20 most frequent {str_col.name} values',
                        'sql': f"SELECT {str_col.name} as x, COUNT(*) as y FROM {table_name} WHERE {str_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
                        'x_column': str_col.name,
                        'y_column': 'count',
                        'score': 0.75
                    })
                    
                    # Termgraph for better horizontal display
                    recommendations.append({
                        'chart_type': 'tg_bar',
                        'title': f'{table_name}: Top 15 {str_col.name} (Horizontal)',
                        'description': f'Horizontal view of top {str_col.name} values',
                        'sql': f"SELECT {str_col.name} as x, COUNT(*) as y FROM {table_name} WHERE {str_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 15",
                        'x_column': str_col.name,
                        'y_column': 'count',
                        'score': 0.73
                    })
            
            # Time series recommendations with proper date formatting
            if date_cols:
                for date_col in date_cols:
                    # Simple daily counts - plotext needs d/m/Y format
                    recommendations.append({
                        'chart_type': 'line',
                        'title': f'{table_name}: Daily Record Count by {date_col.name}',
                        'description': f'Time series showing count of records per day',
                        'sql': f"SELECT strftime('%d/%m/%Y', {date_col.name}) as x, COUNT(*) as y FROM {table_name} GROUP BY {date_col.name} ORDER BY {date_col.name}",
                        'x_column': date_col.name,
                        'y_column': 'count',
                        'score': 0.88
                    })
                    
                    # Calendar heatmap for daily counts
                    if date_col.date_range_days and date_col.date_range_days > 30:
                        recommendations.append({
                            'chart_type': 'tg_calendar',
                            'title': f'{table_name}: Activity Heatmap by {date_col.name}',
                            'description': f'Calendar heatmap showing daily record counts',
                            'sql': f"SELECT strftime('%Y-%m-%d', {date_col.name}) as x, COUNT(*) as y FROM {table_name} GROUP BY 1 ORDER BY 1",
                            'x_column': date_col.name,
                            'y_column': 'count',
                            'score': 0.85
                        })
                    
                    # Monthly aggregation
                    recommendations.append({
                        'chart_type': 'bar',
                        'title': f'{table_name}: Monthly Count by {date_col.name}',
                        'description': f'Bar chart showing record counts by month',
                        'sql': f"SELECT strftime('%Y-%m', {date_col.name}) as x, COUNT(*) as y FROM {table_name} GROUP BY 1 ORDER BY 1",
                        'x_column': 'month',
                        'y_column': 'count',
                        'score': 0.85
                    })
                    
                    # Day of week analysis
                    recommendations.append({
                        'chart_type': 'bar',
                        'title': f'{table_name}: Day of Week Pattern from {date_col.name}',
                        'description': f'Record count distribution by day of week',
                        'sql': f"SELECT strftime('%w', {date_col.name}) || '-' || CASE strftime('%w', {date_col.name}) WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue' WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri' WHEN '6' THEN 'Sat' END as x, COUNT(*) as y FROM {table_name} GROUP BY strftime('%w', {date_col.name}) ORDER BY strftime('%w', {date_col.name})",
                        'x_column': 'day_of_week',
                        'y_column': 'count',
                        'score': 0.82
                    })
                    
                    for num_col in numeric_cols:
                        # Line chart for time series with EU date format for plotext
                        recommendations.append({
                            'chart_type': 'line',
                            'title': f'{table_name}: {num_col.name} by {date_col.name}',
                            'description': f'Time series showing sum of {num_col.name} over time',
                            'sql': f"SELECT strftime('%d/%m/%Y', {date_col.name}) as x, SUM({num_col.name}) as y FROM {table_name} GROUP BY {date_col.name} ORDER BY {date_col.name}",
                            'x_column': date_col.name,
                            'y_column': num_col.name,
                            'score': 0.85
                        })
                        
                        # Calendar heatmap for daily data (termgraph uses Y-m-d)
                        if date_col.date_range_days and date_col.date_range_days > 30:
                            recommendations.append({
                                'chart_type': 'tg_calendar',
                                'title': f'{table_name}: {num_col.name} Heatmap by {date_col.name}',
                                'description': f'Calendar heatmap showing daily sum of {num_col.name}',
                                'sql': f"SELECT strftime('%Y-%m-%d', {date_col.name}) as x, SUM({num_col.name}) as y FROM {table_name} GROUP BY 1 ORDER BY 1",
                                'x_column': date_col.name,
                                'y_column': num_col.name,
                                'score': 0.8
                            })
            
            # Dimensions with COUNT (most fundamental analysis)
            if dimension_cols:
                for dim_col in dimension_cols:
                    if dim_col.cardinality <= 30 and dim_col.cardinality > 1:  # Good for bar charts
                        # Count by dimension (often most important)
                        recommendations.append({
                            'chart_type': 'bar',
                            'title': f'{table_name}: Count by {dim_col.name}',
                            'description': f'Bar chart showing record count for each {dim_col.name}',
                            'sql': f"SELECT {dim_col.name} as x, COUNT(*) as y FROM {table_name} WHERE {dim_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                            'x_column': dim_col.name,
                            'y_column': 'count',
                            'score': 0.85
                        })
            
            # Numeric measures with dimensions
            if dimension_cols and numeric_cols:
                for dim_col in dimension_cols:
                    if dim_col.cardinality <= 30 and dim_col.cardinality > 1:  # Good for bar charts
                        for num_col in numeric_cols:
                            # Sum by dimension
                            recommendations.append({
                                'chart_type': 'bar',
                                'title': f'{table_name}: Sum of {num_col.name} by {dim_col.name}',
                                'description': f'Bar chart showing total {num_col.name} for each {dim_col.name}',
                                'sql': f"SELECT {dim_col.name} as x, SUM({num_col.name}) as y FROM {table_name} WHERE {dim_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                                'x_column': dim_col.name,
                                'y_column': num_col.name,
                                'score': 0.82
                            })
                            
                            # Average by dimension
                            recommendations.append({
                                'chart_type': 'bar',
                                'title': f'{table_name}: Average {num_col.name} by {dim_col.name}',
                                'description': f'Bar chart showing average {num_col.name} for each {dim_col.name}',
                                'sql': f"SELECT {dim_col.name} as x, AVG({num_col.name}) as y FROM {table_name} WHERE {dim_col.name} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
                                'x_column': dim_col.name,
                                'y_column': num_col.name,
                                'score': 0.8
                            })
            
            # Histogram for numeric distributions
            for num_col in numeric_cols:
                recommendations.append({
                    'chart_type': 'histogram',
                    'title': f'{table_name}: Distribution of {num_col.name}',
                    'description': f'Histogram showing value distribution of {num_col.name}',
                    'sql': f"SELECT {num_col.name} as x, {num_col.name} as y FROM {table_name} WHERE {num_col.name} IS NOT NULL",
                    'x_column': num_col.name,
                    'y_column': num_col.name,
                    'score': 0.7
                })
            
            # Scatter plots with numeric pairs
            if len(numeric_cols) >= 2:
                for i, x_col in enumerate(numeric_cols[:4]):
                    for y_col in numeric_cols[i+1:min(i+3, len(numeric_cols))]:
                        if not x_col.is_geographic and not y_col.is_geographic:
                            recommendations.append({
                                'chart_type': 'scatter',
                                'title': f'{table_name}: {y_col.name} vs {x_col.name}',
                                'description': f'Scatter plot showing relationship between {x_col.name} and {y_col.name}',
                                'sql': f"SELECT {x_col.name} as x, {y_col.name} as y FROM {table_name} WHERE {x_col.name} IS NOT NULL AND {y_col.name} IS NOT NULL LIMIT 2000",
                                'x_column': x_col.name,
                                'y_column': y_col.name,
                                'score': 0.75
                            })
            
            # Scatter/bubble charts with COUNT for dimension pairs
            if len(dimension_cols) >= 2:
                dim_pairs = []
                for dim1 in dimension_cols[:4]:
                    for dim2 in dimension_cols[:4]:
                        if dim1 != dim2 and dim1.cardinality <= 40 and dim2.cardinality <= 40:
                            # Sort to avoid duplicates
                            pair = tuple(sorted([dim1.name, dim2.name]))
                            if pair not in dim_pairs:
                                dim_pairs.append(pair)
                                recommendations.append({
                                    'chart_type': 'scatter',
                                    'title': f'{table_name}: Count by {dim1.name} vs {dim2.name}',
                                    'description': f'Bubble chart showing record counts for {dim1.name}/{dim2.name} combinations',
                                    'sql': f"SELECT {dim1.name} as x, {dim2.name} as y, COUNT(*) as size FROM {table_name} WHERE {dim1.name} IS NOT NULL AND {dim2.name} IS NOT NULL GROUP BY 1, 2",
                                    'x_column': dim1.name,
                                    'y_column': dim2.name,
                                    'score': 0.77
                                })
                                if len(dim_pairs) >= 3:  # Limit to 3 pairs
                                    break
                    if len(dim_pairs) >= 3:
                        break
                
                # Figlet for key metrics
                recommendations.append({
                    'chart_type': 'figlet',
                    'title': f'{table_name}: Total {num_col.name}',
                    'description': f'Sum of all {num_col.name} values in {table_name}',
                    'sql': f"SELECT SUM({num_col.name}) as x, SUM({num_col.name}) as y FROM {table_name}",
                    'score': 0.9
                })
                
                recommendations.append({
                    'chart_type': 'figlet',
                    'title': f'{table_name}: Average {num_col.name}',
                    'description': f'Average value of {num_col.name} in {table_name}',
                    'sql': f"SELECT ROUND(AVG({num_col.name}), 2) as x, ROUND(AVG({num_col.name}), 2) as y FROM {table_name}",
                    'score': 0.85
                })
            
            # Multi-series recommendations (with color dimension)
            if dimension_cols and numeric_cols and (date_cols or dimension_cols):
                # Find low cardinality dimensions for color
                color_dims = [col for col in dimension_cols if 2 <= col.cardinality <= 10]
                
                if color_dims:
                    color_col = color_dims[0]  # Pick first suitable color dimension
                    
                    # Time series with color
                    if date_cols:
                        date_col = date_cols[0]
                        num_col = numeric_cols[0]
                        recommendations.append({
                            'chart_type': 'line',
                            'title': f'{table_name}: {num_col.name} by {date_col.name}, colored by {color_col.name}',
                            'description': f'Multi-series time series with {color_col.name} as color dimension',
                            'sql': f"SELECT strftime('%d/%m/%Y', {date_col.name}) as x, {num_col.name} as y, {color_col.name} as color FROM {table_name} ORDER BY {date_col.name}",
                            'x_column': date_col.name,
                            'y_column': num_col.name,
                            'color_column': color_col.name,
                            'score': 0.85
                        })
                    
                    # Grouped bar chart
                    if dimension_cols:
                        x_dim = [col for col in dimension_cols if col != color_col and col.cardinality <= 10]
                        if x_dim:
                            x_col = x_dim[0]
                            num_col = numeric_cols[0]
                            recommendations.append({
                                'chart_type': 'bar',
                                'title': f'{table_name}: {num_col.name} by {x_col.name}, grouped by {color_col.name}',
                                'description': f'Grouped bar chart with {x_col.name} on x-axis and {color_col.name} as groups',
                                'sql': f"SELECT {x_col.name} as x, SUM({num_col.name}) as y, {color_col.name} as color FROM {table_name} GROUP BY 1, 3 ORDER BY 1",
                                'x_column': x_col.name,
                                'y_column': num_col.name,
                                'color_column': color_col.name,
                                'score': 0.8
                            })
                            
                            # Termgraph stacked bars - both dimension arrangements
                            # Version 1: x_col on x-axis, color_col as stack segments
                            recommendations.append({
                                'chart_type': 'tg_stacked',
                                'title': f'{table_name}: {num_col.name} by {x_col.name}, stacked by {color_col.name}',
                                'description': f'Stacked bar chart with {x_col.name} on x-axis and {color_col.name} as stack segments',
                                'sql': f"SELECT {x_col.name} as x, SUM({num_col.name}) as y, {color_col.name} as color FROM {table_name} WHERE {x_col.name} IS NOT NULL AND {color_col.name} IS NOT NULL GROUP BY 1, 3 ORDER BY 1, 3",
                                'x_column': x_col.name,
                                'y_column': num_col.name,
                                'color_column': color_col.name,
                                'score': 0.82
                            })
                            
                            # Version 2: color_col on x-axis, x_col as stack segments
                            recommendations.append({
                                'chart_type': 'tg_stacked',
                                'title': f'{table_name}: {num_col.name} by {color_col.name}, stacked by {x_col.name}',
                                'description': f'Stacked bar chart with {color_col.name} on x-axis and {x_col.name} as stack segments',
                                'sql': f"SELECT {color_col.name} as x, SUM({num_col.name}) as y, {x_col.name} as color FROM {table_name} WHERE {x_col.name} IS NOT NULL AND {color_col.name} IS NOT NULL GROUP BY 1, 3 ORDER BY 1, 3",
                                'x_column': color_col.name,
                                'y_column': num_col.name,
                                'color_column': x_col.name,
                                'score': 0.82
                            })
                
                # Also add termgraph stacked for single dimension with counts
                for dim_col in dimension_cols:
                    if 2 <= dim_col.cardinality <= 20:
                        # Find another dimension to pair with
                        other_dims = [col for col in dimension_cols if col != dim_col and 2 <= col.cardinality <= 10]
                        if other_dims:
                            other_dim = other_dims[0]
                            # Count stacked bars
                            recommendations.append({
                                'chart_type': 'tg_stacked',
                                'title': f'{table_name}: Count by {dim_col.name}, stacked by {other_dim.name}',
                                'description': f'Stacked count chart with {dim_col.name} categories and {other_dim.name} segments',
                                'sql': f"SELECT {dim_col.name} as x, COUNT(*) as y, {other_dim.name} as color FROM {table_name} WHERE {dim_col.name} IS NOT NULL AND {other_dim.name} IS NOT NULL GROUP BY 1, 3 ORDER BY 1, 3",
                                'x_column': dim_col.name,
                                'y_column': 'count',
                                'color_column': other_dim.name,
                                'score': 0.83
                            })
            
            # Special handling for single-row summary tables
            if table_analysis.row_count == 1 and numeric_cols:
                for num_col in numeric_cols:
                    recommendations.append({
                        'chart_type': 'figlet',
                        'title': f'{table_name}: {num_col.name} Value',
                        'description': f'Single value display of {num_col.name}',
                        'sql': f"SELECT {num_col.name} as x, {num_col.name} as y FROM {table_name}",
                        'x_column': num_col.name,
                        'y_column': num_col.name,
                        'score': 0.95
                    })
            
            # Rich table for detailed views
            if len(table_analysis.columns) >= 3:
                col_list = list(table_analysis.columns.keys())[:10]  # Limit columns
                recommendations.append({
                    'chart_type': 'rich_table',
                    'title': f'{table_name}: Sample Records',
                    'description': f'Table view showing columns: {', '.join(col_list[:5])}{'...' if len(col_list) > 5 else ''}',
                    'sql': f"SELECT {', '.join(col_list)} FROM {table_name} LIMIT 100",
                    'score': 0.6
                })
            
            # Add more count-based figlet displays
            if table_analysis.row_count > 0:
                # Count of unique values for each dimension
                for dim_col in dimension_cols:
                    if dim_col.cardinality > 1:
                        recommendations.append({
                            'chart_type': 'figlet',
                            'title': f'{table_name}: Unique {dim_col.name} Count',
                            'description': f'Number of distinct {dim_col.name} values',
                            'sql': f"SELECT COUNT(DISTINCT {dim_col.name}) as x, COUNT(DISTINCT {dim_col.name}) as y FROM {table_name}",
                            'score': 0.8
                        })
            
            # Sort by score and save
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            table_analysis.recommended_charts = recommendations
    
    def save_results(self, output_path: str = '.cheshire_analysis.json') -> None:
        """Save analysis results to JSON file"""
        # Build database info
        db_info = {
            'type': self.db_type
        }
        
        if self.db_name:
            db_info['name'] = self.db_name
        elif isinstance(self.db_config, str):
            db_info['path'] = self.db_config
        elif isinstance(self.db_config, dict):
            # Include relevant config info
            if 'path' in self.db_config:
                db_info['path'] = self.db_config['path']
            if 'host' in self.db_config:
                db_info['host'] = self.db_config['host']
            if 'database' in self.db_config:
                db_info['database'] = self.db_config['database']
        
        output = {
            'analysis_date': datetime.now().isoformat(),
            'database': db_info,
            'tables': {name: table.to_dict() for name, table in self.analysis_results.items()}
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Analysis saved to: {output_path}")


def analyze_database(db_identifier: Any, db_type: str = 'duckdb', output_path: Optional[str] = None, db_name: Optional[str] = None) -> None:
    """Main entry point for database analysis
    
    Args:
        db_identifier: Database connection info
        db_type: Type of database ('duckdb', 'sqlite', etc.)
        output_path: Optional custom output path for JSON results
        db_name: Optional database name for generating default output filename
    """
    analyzer = DatabaseAnalyzer(db_identifier, db_type, db_name)
    results = analyzer.analyze()
    
    # Print summary
    print("\n📈 Analysis Summary:")
    total_recommendations = 0
    for table_name, table_analysis in results.items():
        chart_count = len(table_analysis.recommended_charts)
        total_recommendations += chart_count
        print(f"  {table_name}: {chart_count} chart recommendations")
    
    print(f"\n✨ Total recommendations: {total_recommendations}")
    
    # Determine output path
    if not output_path:
        # Generate output filename based on database name or path
        if db_name:
            # Named database from config
            safe_name = db_name.replace('/', '_').replace('\\', '_')
            output_path = f'.cheshire_analysis_{safe_name}.json'
        elif isinstance(db_identifier, str) and db_identifier != ':memory:':
            # File-based database
            from pathlib import Path
            db_path = Path(db_identifier)
            safe_name = db_path.stem.replace('.', '_')
            output_path = f'.cheshire_analysis_{safe_name}.json'
        else:
            # Default fallback
            output_path = '.cheshire_analysis.json'
    
    # Save results
    analyzer.save_results(output_path)


def analyze_csv_tsv_file(file_path: str, file_type: str = 'csv', output_path: Optional[str] = None) -> None:
    """Analyze a CSV or TSV file using DuckDB
    
    Args:
        file_path: Path to the CSV/TSV file
        file_type: 'csv' or 'tsv'
        output_path: Optional custom output path for JSON results
    """
    from pathlib import Path
    
    # Check if file exists
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        return
    
    # Get absolute path for the file
    abs_file_path = str(Path(file_path).resolve())
        
    # Create a special analyzer for CSV/TSV files
    print(f"🔍 Analyzing {file_type.upper()} file: {abs_file_path}")
    
    # We'll use DuckDB to analyze the CSV/TSV
    conn = duckdb.connect(':memory:')
    
    try:
        # Create the appropriate FROM clause using absolute path
        if file_type == 'csv':
            from_clause = f"read_csv_auto('{abs_file_path}')"
        else:
            from_clause = f"read_csv_auto('{abs_file_path}', delim='\\t')"
        
        # Get column information
        schema_query = f"DESCRIBE SELECT * FROM {from_clause}"
        schema_result = conn.execute(schema_query).fetchall()
        
        # Get row count
        count_query = f"SELECT COUNT(*) FROM {from_clause}"
        row_count = conn.execute(count_query).fetchone()[0]
        
        # Get sample data
        sample_query = f"SELECT * FROM {from_clause} LIMIT 10"
        sample_data = conn.execute(sample_query).fetchall()
        
        print(f"Found {len(schema_result)} columns and {row_count} rows")
        
        # Create a TableAnalysis object
        table_name = Path(file_path).stem
        table_analysis = TableAnalysis(table_name)
        table_analysis.row_count = row_count
        
        # Analyze each column
        for col_info in schema_result:
            col_name = col_info[0]
            col_type = str(col_info[1])
            
            print(f"  Analyzing column: {col_name} ({col_type})")
            
            col_analysis = ColumnAnalysis(col_name, col_type)
            col_analysis.sql_type = col_type
            
            # Determine data characteristics
            col_analysis.is_numeric = any(t in col_type.upper() for t in ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL', 'NUMERIC'])
            col_analysis.is_date = any(t in col_type.upper() for t in ['DATE', 'TIME', 'TIMESTAMP'])
            
            # Get column statistics
            try:
                # Cardinality
                card_query = f"SELECT COUNT(DISTINCT {col_name}) FROM {from_clause}"
                col_analysis.cardinality = conn.execute(card_query).fetchone()[0]
                
                # Null count
                null_query = f"SELECT COUNT(*) FROM {from_clause} WHERE {col_name} IS NULL"
                col_analysis.null_count = conn.execute(null_query).fetchone()[0]
                col_analysis.total_count = row_count
                
                # Min/Max/Avg for numeric columns
                if col_analysis.is_numeric:
                    stats_query = f"SELECT MIN({col_name}), MAX({col_name}), AVG({col_name}) FROM {from_clause} WHERE {col_name} IS NOT NULL"
                    stats = conn.execute(stats_query).fetchone()
                    col_analysis.min_value = stats[0]
                    col_analysis.max_value = stats[1]
                    col_analysis.avg_value = stats[2]
                elif not col_analysis.is_date:
                    # For text columns, get min/max length
                    len_query = f"SELECT MIN(LENGTH({col_name})), MAX(LENGTH({col_name})) FROM {from_clause} WHERE {col_name} IS NOT NULL"
                    len_stats = conn.execute(len_query).fetchone()
                    col_analysis.min_value = f"Length: {len_stats[0]}"
                    col_analysis.max_value = f"Length: {len_stats[1]}"
                
                # Sample values
                sample_query = f"SELECT DISTINCT {col_name} FROM {from_clause} WHERE {col_name} IS NOT NULL LIMIT 10"
                samples = conn.execute(sample_query).fetchall()
                col_analysis.sample_values = [row[0] for row in samples]
                
                # Determine if dimension or measure
                if col_analysis.is_numeric:
                    # High cardinality numeric = measure, low = dimension
                    col_analysis.is_measure = col_analysis.cardinality > (row_count * 0.5)
                    col_analysis.is_dimension = not col_analysis.is_measure
                else:
                    col_analysis.is_dimension = True
                    col_analysis.is_measure = False
                    
                # Check for geographic columns
                col_name_lower = col_name.lower()
                if any(lat in col_name_lower for lat in ['lat', 'latitude']):
                    col_analysis.is_latitude = True
                    col_analysis.is_geographic = True
                elif any(lon in col_name_lower for lon in ['lon', 'long', 'longitude']):
                    col_analysis.is_longitude = True
                    col_analysis.is_geographic = True
                    
            except Exception as e:
                print(f"    Warning: Could not analyze column {col_name}: {e}")
            
            table_analysis.columns[col_name] = col_analysis
        
        # Generate chart recommendations
        print("\n📊 Generating chart recommendations...")
        recommendations = generate_csv_recommendations(table_analysis, from_clause)
        table_analysis.recommended_charts = recommendations
        
        # Prepare results for saving
        results = {table_name: table_analysis}
        
        # Determine output path
        if not output_path:
            safe_name = Path(file_path).stem.replace('.', '_')
            output_path = f'.cheshire_analysis_{safe_name}.json'
        
        # Save results in the same format as database analysis
        save_data = {
            'analysis_date': datetime.now().isoformat(),
            'database': {
                'type': file_type,
                'name': Path(abs_file_path).name,
                'path': abs_file_path  # Store absolute path
            },
            'tables': {name: table.to_dict() for name, table in results.items()}
        }
        
        with open(output_path, 'w') as f:
            json.dump(save_data, f, indent=2, default=str)
        
        print(f"\n💾 Analysis saved to: {output_path}")
        print(f"✨ Generated {len(recommendations)} chart recommendations")
        
    finally:
        conn.close()


def generate_csv_recommendations(table: TableAnalysis, from_clause: str) -> List[Dict[str, Any]]:
    """Generate chart recommendations for a CSV/TSV file
    
    Args:
        table: TableAnalysis object with column information
        from_clause: DuckDB FROM clause for reading the file
    
    Returns:
        List of chart recommendation dictionaries
    """
    recommendations = []
    
    # Find numeric and categorical columns
    numeric_cols = [name for name, col in table.columns.items() if col.is_numeric]
    categorical_cols = [name for name, col in table.columns.items() 
                       if not col.is_numeric and not col.is_date and col.cardinality < 50]
    date_cols = [name for name, col in table.columns.items() if col.is_date]
    geo_cols = [(name, col) for name, col in table.columns.items() if col.is_geographic]
    
    # Check for lat/lon pairs
    lat_cols = [name for name, col in table.columns.items() if col.is_latitude]
    lon_cols = [name for name, col in table.columns.items() if col.is_longitude]
    has_geo = lat_cols and lon_cols
    
    # 1. Bar charts for categorical vs numeric
    for cat_col in categorical_cols[:3]:  # Limit to top 3 categorical
        for num_col in numeric_cols[:3]:  # Limit to top 3 numeric
            recommendations.append({
                'chart_type': 'bar',
                'title': f'{num_col} by {cat_col}',
                'description': f'Average {num_col} for each {cat_col}',
                'sql': f"SELECT {cat_col} as x, AVG({num_col}) as y FROM {from_clause} WHERE {cat_col} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
                'score': 0.85
            })
            
    # 2. Time series if date columns exist
    for date_col in date_cols[:2]:
        for num_col in numeric_cols[:3]:
            recommendations.append({
                'chart_type': 'line',
                'title': f'{num_col} over time',
                'description': f'Trend of {num_col} by {date_col}',
                'sql': f"SELECT {date_col} as x, AVG({num_col}) as y FROM {from_clause} GROUP BY 1 ORDER BY 1",
                'score': 0.90
            })
    
    # 3. Distribution charts
    for num_col in numeric_cols[:3]:
        col = table.columns[num_col]
        if col.cardinality > 10:
            recommendations.append({
                'chart_type': 'histogram',
                'title': f'Distribution of {num_col}',
                'description': f'Histogram showing distribution of {num_col} values',
                'sql': f"SELECT {num_col} as x, {num_col} as y FROM {from_clause} WHERE {num_col} IS NOT NULL",
                'score': 0.75
            })
    
    # 4. Scatter plots for numeric correlations
    if len(numeric_cols) >= 2:
        for i, col1 in enumerate(numeric_cols[:3]):
            for col2 in numeric_cols[i+1:4]:
                recommendations.append({
                    'chart_type': 'scatter',
                    'title': f'{col1} vs {col2}',
                    'description': f'Correlation between {col1} and {col2}',
                    'sql': f"SELECT {col1} as x, {col2} as y FROM {from_clause} WHERE {col1} IS NOT NULL AND {col2} IS NOT NULL",
                    'score': 0.70
                })
    
    # 5. Pie charts for small categorical columns
    for cat_col in categorical_cols:
        col = table.columns[cat_col]
        if 2 <= col.cardinality <= 10:
            recommendations.append({
                'chart_type': 'pie',
                'title': f'Distribution of {cat_col}',
                'description': f'Pie chart showing {cat_col} distribution',
                'sql': f"SELECT {cat_col} as x, COUNT(*) as y FROM {from_clause} GROUP BY 1",
                'score': 0.80
            })
    
    # 6. Geographic visualizations if lat/lon exist
    if has_geo:
        lat_col = lat_cols[0]
        lon_col = lon_cols[0]
        
        recommendations.append({
            'chart_type': 'map',
            'title': 'Geographic Distribution',
            'description': 'Map showing data point locations',
            'sql': f"SELECT {lat_col} as lat, {lon_col} as lon FROM {from_clause} WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL",
            'score': 0.95
        })
        
        # Add heatmap if there's a value column
        if numeric_cols:
            value_col = numeric_cols[0]
            recommendations.append({
                'chart_type': 'map_heatmap',
                'title': f'Geographic Heatmap of {value_col}',
                'description': f'Heatmap showing {value_col} by location',
                'sql': f"SELECT {lat_col} as lat, {lon_col} as lon, {value_col} as value FROM {from_clause} WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL AND {value_col} IS NOT NULL",
                'score': 0.93
            })
    
    # 7. Summary statistics
    if numeric_cols:
        # Pick the most interesting numeric column (highest cardinality)
        best_num_col = max(numeric_cols, key=lambda c: table.columns[c].cardinality)
        recommendations.append({
            'chart_type': 'figlet',
            'title': f'Total {best_num_col}',
            'description': f'Sum of all {best_num_col} values',
            'sql': f"SELECT SUM({best_num_col}) as y, '{best_num_col.upper()}' as x FROM {from_clause}",
            'score': 0.60
        })
    
    # 8. Table view for overview
    col_list = list(table.columns.keys())[:5]  # First 5 columns
    col_select = ', '.join(col_list)
    recommendations.append({
        'chart_type': 'rich_table',
        'title': 'Data Sample',
        'description': 'Sample rows from the dataset',
        'sql': f"SELECT {col_select} FROM {from_clause} LIMIT 20",
        'score': 0.50
    })
    
    # Sort by score
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    
    return recommendations


def analyze_parquet_file(path: str, output_path: Optional[str] = None) -> None:
    """Analyze a Parquet file or folder of Parquet files using DuckDB
    
    Args:
        path: Path to a Parquet file or directory containing Parquet files
        output_path: Optional custom output path for JSON results
    """
    from pathlib import Path
    import glob
    
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"Error: Path not found: {path}")
        return
    
    # Get absolute path
    abs_path = str(path_obj.resolve())
    
    # Determine what we're analyzing
    parquet_files = []
    if path_obj.is_file():
        # Single file
        if path_obj.suffix.lower() == '.parquet':
            parquet_files = [abs_path]
            from_clause = f"read_parquet('{abs_path}')"
        else:
            print(f"Error: Not a Parquet file: {path}")
            return
    else:
        # Directory - find all Parquet files
        parquet_files = glob.glob(f"{abs_path}/**/*.parquet", recursive=True)
        if not parquet_files:
            parquet_files = glob.glob(f"{abs_path}/*.parquet")
        
        if not parquet_files:
            print(f"Error: No Parquet files found in: {path}")
            return
        
        # Use glob pattern for DuckDB
        if len(parquet_files) == 1:
            from_clause = f"read_parquet('{parquet_files[0]}')"
        else:
            # Use wildcard pattern
            from_clause = f"read_parquet('{abs_path}/**/*.parquet')"
    
    print(f"🔍 Analyzing Parquet data: {path}")
    print(f"Found {len(parquet_files)} Parquet file(s)")
    
    # Connect to DuckDB
    conn = duckdb.connect(':memory:')
    
    try:
        # Get schema information
        schema_query = f"DESCRIBE SELECT * FROM {from_clause}"
        schema_result = conn.execute(schema_query).fetchall()
        
        # Get row count
        count_query = f"SELECT COUNT(*) FROM {from_clause}"
        row_count = conn.execute(count_query).fetchone()[0]
        
        print(f"Found {len(schema_result)} columns and {row_count:,} rows")
        
        # For multiple files, also show file-level statistics
        if len(parquet_files) > 1:
            print("\nFile statistics:")
            for pf in parquet_files[:10]:  # Show first 10 files
                file_count = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{pf}')").fetchone()[0]
                print(f"  {Path(pf).name}: {file_count:,} rows")
            if len(parquet_files) > 10:
                print(f"  ... and {len(parquet_files) - 10} more files")
        
        # Create TableAnalysis object
        table_name = Path(path).stem if path_obj.is_file() else Path(path).name
        table_analysis = TableAnalysis(table_name)
        table_analysis.row_count = row_count
        
        # Analyze each column (similar to CSV analysis)
        print("\n📊 Analyzing columns...")
        for col_info in schema_result:
            col_name = col_info[0]
            col_type = str(col_info[1])
            
            print(f"  Analyzing column: {col_name} ({col_type})")
            
            col_analysis = ColumnAnalysis(col_name, col_type)
            col_analysis.sql_type = col_type
            
            # Determine data characteristics
            col_analysis.is_numeric = any(t in col_type.upper() for t in ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL', 'NUMERIC'])
            col_analysis.is_date = any(t in col_type.upper() for t in ['DATE', 'TIME', 'TIMESTAMP'])
            
            # Get column statistics
            try:
                # Cardinality
                card_query = f"SELECT COUNT(DISTINCT {col_name}) FROM {from_clause}"
                col_analysis.cardinality = conn.execute(card_query).fetchone()[0]
                
                # Null count
                null_query = f"SELECT COUNT(*) FROM {from_clause} WHERE {col_name} IS NULL"
                col_analysis.null_count = conn.execute(null_query).fetchone()[0]
                col_analysis.total_count = row_count
                
                # Min/Max/Avg for numeric columns
                if col_analysis.is_numeric:
                    stats_query = f"SELECT MIN({col_name}), MAX({col_name}), AVG({col_name}) FROM {from_clause} WHERE {col_name} IS NOT NULL"
                    stats = conn.execute(stats_query).fetchone()
                    col_analysis.min_value = stats[0]
                    col_analysis.max_value = stats[1]
                    col_analysis.avg_value = stats[2]
                elif col_analysis.is_date:
                    # For date columns, get range
                    date_query = f"SELECT MIN({col_name}), MAX({col_name}) FROM {from_clause} WHERE {col_name} IS NOT NULL"
                    date_stats = conn.execute(date_query).fetchone()
                    col_analysis.min_value = str(date_stats[0]) if date_stats[0] else None
                    col_analysis.max_value = str(date_stats[1]) if date_stats[1] else None
                else:
                    # For text columns, get length stats
                    len_query = f"SELECT MIN(LENGTH({col_name})), MAX(LENGTH({col_name})) FROM {from_clause} WHERE {col_name} IS NOT NULL"
                    len_stats = conn.execute(len_query).fetchone()
                    if len_stats[0] is not None:
                        col_analysis.min_value = f"Length: {len_stats[0]}"
                        col_analysis.max_value = f"Length: {len_stats[1]}"
                
                # Sample values (limit for performance on large datasets)
                sample_query = f"SELECT DISTINCT {col_name} FROM {from_clause} WHERE {col_name} IS NOT NULL LIMIT 10"
                samples = conn.execute(sample_query).fetchall()
                col_analysis.sample_values = [str(row[0]) for row in samples]
                
                # Determine if dimension or measure
                if col_analysis.is_numeric:
                    col_analysis.is_measure = col_analysis.cardinality > (row_count * 0.5)
                    col_analysis.is_dimension = not col_analysis.is_measure
                else:
                    col_analysis.is_dimension = True
                    col_analysis.is_measure = False
                
                # Check for geographic columns
                col_name_lower = col_name.lower()
                if any(lat in col_name_lower for lat in ['lat', 'latitude']):
                    col_analysis.is_latitude = True
                    col_analysis.is_geographic = True
                elif any(lon in col_name_lower for lon in ['lon', 'long', 'longitude']):
                    col_analysis.is_longitude = True
                    col_analysis.is_geographic = True
                    
            except Exception as e:
                print(f"    Warning: Could not fully analyze column {col_name}: {e}")
            
            table_analysis.columns[col_name] = col_analysis
        
        # Generate chart recommendations
        print("\n📊 Generating chart recommendations...")
        recommendations = generate_parquet_recommendations(table_analysis, from_clause)
        table_analysis.recommended_charts = recommendations
        
        # Prepare results
        results = {table_name: table_analysis}
        
        # Determine output path
        if not output_path:
            safe_name = Path(path).stem.replace('.', '_') if path_obj.is_file() else Path(path).name.replace('.', '_')
            output_path = f'.cheshire_analysis_{safe_name}.json'
        
        # Save results
        save_data = {
            'analysis_date': datetime.now().isoformat(),
            'database': {
                'type': 'parquet',
                'name': Path(path).name,
                'path': abs_path,
                'file_count': len(parquet_files),
                'total_rows': row_count
            },
            'tables': {name: table.to_dict() for name, table in results.items()}
        }
        
        with open(output_path, 'w') as f:
            json.dump(save_data, f, indent=2, default=str)
        
        print(f"\n💾 Analysis saved to: {output_path}")
        print(f"✨ Generated {len(recommendations)} chart recommendations")
        
    finally:
        conn.close()


def generate_parquet_recommendations(table: TableAnalysis, from_clause: str) -> List[Dict[str, Any]]:
    """Generate chart recommendations for Parquet data
    
    Uses the same logic as CSV but with read_parquet() instead of read_csv_auto()
    """
    recommendations = []
    
    # Find numeric and categorical columns
    numeric_cols = [name for name, col in table.columns.items() if col.is_numeric]
    categorical_cols = [name for name, col in table.columns.items() 
                       if not col.is_numeric and not col.is_date and col.cardinality < 50]
    date_cols = [name for name, col in table.columns.items() if col.is_date]
    
    # Check for lat/lon pairs
    lat_cols = [name for name, col in table.columns.items() if col.is_latitude]
    lon_cols = [name for name, col in table.columns.items() if col.is_longitude]
    has_geo = lat_cols and lon_cols
    
    # 1. Bar charts for categorical vs numeric
    for cat_col in categorical_cols[:3]:
        for num_col in numeric_cols[:3]:
            recommendations.append({
                'chart_type': 'bar',
                'title': f'{num_col} by {cat_col}',
                'description': f'Average {num_col} for each {cat_col}',
                'sql': f"SELECT {cat_col} as x, AVG({num_col}) as y FROM {from_clause} WHERE {cat_col} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
                'score': 0.85
            })
    
    # 2. Time series if date columns exist
    for date_col in date_cols[:2]:
        for num_col in numeric_cols[:3]:
            recommendations.append({
                'chart_type': 'line',
                'title': f'{num_col} over time',
                'description': f'Trend of {num_col} by {date_col}',
                'sql': f"SELECT {date_col} as x, AVG({num_col}) as y FROM {from_clause} GROUP BY 1 ORDER BY 1",
                'score': 0.90
            })
    
    # 3. Distribution charts
    for num_col in numeric_cols[:3]:
        col = table.columns[num_col]
        if col.cardinality > 10:
            recommendations.append({
                'chart_type': 'histogram',
                'title': f'Distribution of {num_col}',
                'description': f'Histogram showing distribution of {num_col} values',
                'sql': f"SELECT {num_col} as x, {num_col} as y FROM {from_clause} WHERE {num_col} IS NOT NULL",
                'score': 0.75
            })
    
    # 4. Scatter plots
    if len(numeric_cols) >= 2:
        for i, col1 in enumerate(numeric_cols[:3]):
            for col2 in numeric_cols[i+1:4]:
                recommendations.append({
                    'chart_type': 'scatter',
                    'title': f'{col1} vs {col2}',
                    'description': f'Correlation between {col1} and {col2}',
                    'sql': f"SELECT {col1} as x, {col2} as y FROM {from_clause} WHERE {col1} IS NOT NULL AND {col2} IS NOT NULL LIMIT 10000",
                    'score': 0.70
                })
    
    # 5. Pie charts for small categorical columns
    for cat_col in categorical_cols:
        col = table.columns[cat_col]
        if 2 <= col.cardinality <= 10:
            recommendations.append({
                'chart_type': 'pie',
                'title': f'Distribution of {cat_col}',
                'description': f'Pie chart showing {cat_col} distribution',
                'sql': f"SELECT {cat_col} as x, COUNT(*) as y FROM {from_clause} GROUP BY 1",
                'score': 0.80
            })
    
    # 6. Geographic visualizations
    if has_geo:
        lat_col = lat_cols[0]
        lon_col = lon_cols[0]
        
        recommendations.append({
            'chart_type': 'map',
            'title': 'Geographic Distribution',
            'description': 'Map showing data point locations',
            'sql': f"SELECT {lat_col} as lat, {lon_col} as lon FROM {from_clause} WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL LIMIT 50000",
            'score': 0.95
        })
        
        if numeric_cols:
            value_col = numeric_cols[0]
            recommendations.append({
                'chart_type': 'map_heatmap',
                'title': f'Geographic Heatmap of {value_col}',
                'description': f'Heatmap showing {value_col} by location',
                'sql': f"SELECT {lat_col} as lat, {lon_col} as lon, {value_col} as value FROM {from_clause} WHERE {lat_col} IS NOT NULL AND {lon_col} IS NOT NULL AND {value_col} IS NOT NULL LIMIT 50000",
                'score': 0.93
            })
    
    # 7. Summary statistics
    if numeric_cols:
        best_num_col = max(numeric_cols, key=lambda c: table.columns[c].cardinality)
        recommendations.append({
            'chart_type': 'figlet',
            'title': f'Total {best_num_col}',
            'description': f'Sum of all {best_num_col} values',
            'sql': f"SELECT SUM({best_num_col}) as y, '{best_num_col.upper()}' as x FROM {from_clause}",
            'score': 0.60
        })
        
        # Row count display
        recommendations.append({
            'chart_type': 'figlet',
            'title': 'Total Records',
            'description': 'Number of records in dataset',
            'sql': f"SELECT COUNT(*) as y, 'ROWS' as x FROM {from_clause}",
            'score': 0.55
        })
    
    # 8. Table view
    col_list = list(table.columns.keys())[:5]
    col_select = ', '.join(col_list)
    recommendations.append({
        'chart_type': 'rich_table',
        'title': 'Data Sample',
        'description': 'Sample rows from the dataset',
        'sql': f"SELECT {col_select} FROM {from_clause} LIMIT 20",
        'score': 0.50
    })
    
    # Sort by score
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    
    return recommendations