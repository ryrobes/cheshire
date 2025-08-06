#!/usr/bin/env python3
"""
Database connectors for cheshire.
Supports DuckDB, PostgreSQL, MySQL, SQLite (via DuckDB extensions), ClickHouse, and osquery.
"""

import duckdb
import subprocess
import json
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path


class DatabaseConnector:
    """Base class for database connections."""
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query and return results as list of dictionaries."""
        raise NotImplementedError


class DuckDBConnector(DatabaseConnector):
    """Direct DuckDB connection for .duckdb files and in-memory databases."""
    
    def __init__(self, path: str = ':memory:'):
        self.path = path
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using DuckDB."""
        # Special handling for in-memory database
        if self.path == ':memory:' or not self.path:
            conn = duckdb.connect(':memory:')
        else:
            conn = duckdb.connect(self.path, read_only=True)
        try:
            result = conn.execute(query).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [dict(zip(columns, row)) for row in result]
        finally:
            conn.close()


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL connection via DuckDB's postgres_scanner extension."""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using DuckDB's PostgreSQL scanner."""
        conn = duckdb.connect(':memory:')
        try:
            # Install and load postgres_scanner extension
            conn.execute("INSTALL postgres_scanner; LOAD postgres_scanner;")
            
            # For postgres_scanner, we can either:
            # 1. Use postgres_scan function for specific tables
            # 2. Attach the entire database
            
            # Try to attach the database
            conn.execute(f"ATTACH '{self.connection_string}' AS pg (TYPE postgres)")
            
            # If query references tables without schema, try with pg prefix
            try:
                result = conn.execute(query).fetchall()
            except Exception:
                # Try prefixing tables with pg.
                # This is a simple approach - in production you'd want better SQL parsing
                modified_query = query.replace("FROM ", "FROM pg.")
                result = conn.execute(modified_query).fetchall()
            
            columns = [desc[0] for desc in conn.description]
            return [dict(zip(columns, row)) for row in result]
        finally:
            conn.close()


class MySQLConnector(DatabaseConnector):
    """MySQL connection via DuckDB's mysql_scanner extension."""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using DuckDB's MySQL scanner."""
        conn = duckdb.connect(':memory:')
        try:
            # Install and load mysql_scanner extension
            conn.execute("INSTALL mysql_scanner; LOAD mysql_scanner;")
            
            # Attach the MySQL database
            conn.execute(f"ATTACH '{self.connection_string}' AS mysql_db (TYPE mysql)")
            
            # Try to execute query
            try:
                result = conn.execute(query).fetchall()
            except Exception:
                # Try prefixing tables with mysql_db.
                modified_query = query.replace("FROM ", "FROM mysql_db.")
                result = conn.execute(modified_query).fetchall()
            
            columns = [desc[0] for desc in conn.description]
            return [dict(zip(columns, row)) for row in result]
        finally:
            conn.close()


class SQLiteConnector(DatabaseConnector):
    """SQLite connection via DuckDB's sqlite_scanner extension."""
    
    def __init__(self, path: str):
        self.path = path
        
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using DuckDB's SQLite scanner."""
        conn = duckdb.connect(':memory:')
        try:
            # Install and load sqlite_scanner extension
            conn.execute("INSTALL sqlite_scanner; LOAD sqlite_scanner;")
            
            # Attach the SQLite database
            conn.execute(f"ATTACH '{self.path}' AS sqlite_db (TYPE sqlite)")
            
            # Try to execute query
            try:
                result = conn.execute(query).fetchall()
            except Exception as e:
                # Handle PRAGMA queries specially
                if query.strip().upper().startswith("PRAGMA"):
                    # For PRAGMA table_info, we need to prefix the table name, not the PRAGMA
                    if "table_info" in query:
                        # Extract table name and prefix it
                        import re
                        match = re.search(r'table_info\((.*?)\)', query)
                        if match:
                            table_name = match.group(1).strip()
                            modified_query = query.replace(f"table_info({table_name})", f"table_info(sqlite_db.{table_name})")
                        else:
                            raise e
                    else:
                        raise e
                else:
                    # Try prefixing tables with sqlite_db.
                    modified_query = query.replace("FROM ", "FROM sqlite_db.")
                result = conn.execute(modified_query).fetchall()
            
            columns = [desc[0] for desc in conn.description]
            return [dict(zip(columns, row)) for row in result]
        finally:
            conn.close()


class ClickHouseConnector(DatabaseConnector):
    """Native ClickHouse connection using clickhouse-driver."""
    
    def __init__(self, host: str = 'localhost', port: int = 9000, 
                 database: str = 'default', user: str = 'default', 
                 password: str = '', **kwargs):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.extra_params = kwargs
        
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using clickhouse-driver."""
        try:
            from clickhouse_driver import Client
        except ImportError:
            raise ImportError(
                "clickhouse-driver not installed. Run: pip install clickhouse-driver"
            )
        
        # Disable compression by default to avoid lz4 errors
        params = {
            'compression': False,
            **self.extra_params
        }
        
        client = Client(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            **params
        )
        
        # Execute query with column info
        result = client.execute(query, with_column_types=True)
        
        if not result or not result[0]:
            return []
        
        rows, columns_with_types = result
        columns = [col[0] for col in columns_with_types]
        
        # Convert rows to list of dicts
        return [dict(zip(columns, row)) for row in rows]


class OsqueryConnector(DatabaseConnector):
    """osquery connection via osqueryi CLI tool."""
    
    def __init__(self):
        """Initialize osquery connector."""
        # Check if osqueryi is available
        self.osqueryi_path = shutil.which('osqueryi')
        if not self.osqueryi_path:
            raise RuntimeError(
                "osqueryi not found in PATH. Please install osquery: "
                "https://osquery.io/downloads/"
            )
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query using osqueryi CLI and return results."""
        try:
            # Execute query via osqueryi with JSON output
            # Use --json for JSON output format
            # Use --disable_events to avoid event-based tables that might hang
            result = subprocess.run(
                [self.osqueryi_path, '--json', '--disable_events', query],
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                check=False  # Don't raise on non-zero exit codes
            )
            
            # Check for errors
            if result.returncode != 0:
                # osqueryi returns non-zero for SQL errors
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                # Try to extract meaningful error from output
                if "Error:" in result.stdout:
                    error_msg = result.stdout.split("Error:")[1].strip()
                raise RuntimeError(f"osquery error: {error_msg}")
            
            # Parse JSON output
            if not result.stdout.strip():
                return []
                
            try:
                data = json.loads(result.stdout)
                # osqueryi returns a list of dictionaries
                if isinstance(data, list):
                    return data
                else:
                    # Unexpected format
                    return []
            except json.JSONDecodeError as e:
                # If JSON parsing fails, try to provide helpful error
                raise RuntimeError(f"Failed to parse osquery output: {e}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("osquery query timed out after 30 seconds")
        except Exception as e:
            raise RuntimeError(f"Failed to execute osquery: {e}")


def is_osquery_available() -> bool:
    """Check if osquery is installed and available."""
    return shutil.which('osqueryi') is not None


def create_connector(db_config: Dict[str, Any]) -> DatabaseConnector:
    """
    Factory function to create appropriate database connector.
    
    Args:
        db_config: Database configuration dict with 'type' and connection params
        
    Returns:
        DatabaseConnector instance
    """
    db_type = db_config.get('type', 'duckdb').lower()
    
    if db_type == 'duckdb':
        return DuckDBConnector(db_config.get('path', ':memory:'))
        
    elif db_type in ['postgres', 'postgresql']:
        connection = db_config.get('connection', '')
        if not connection:
            # Build connection string from parts
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 5432)
            user = db_config.get('user', 'postgres')
            password = db_config.get('password', '')
            database = db_config.get('database', 'postgres')
            
            connection = f"host={host} port={port} user={user}"
            if password:
                connection += f" password={password}"
            connection += f" dbname={database}"
            
        return PostgreSQLConnector(connection)
        
    elif db_type == 'mysql':
        connection = db_config.get('connection', '')
        if not connection:
            # Build connection string from parts
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 3306)
            user = db_config.get('user', 'root')
            password = db_config.get('password', '')
            database = db_config.get('database', '')
            
            # MySQL connection string format for DuckDB
            connection = f"host={host} port={port} user={user}"
            if password:
                connection += f" password={password}"
            if database:
                connection += f" database={database}"
                
        return MySQLConnector(connection)
        
    elif db_type == 'sqlite':
        path = db_config.get('path', '')
        if not path:
            raise ValueError("SQLite requires 'path' parameter")
        return SQLiteConnector(path)
        
    elif db_type == 'clickhouse':
        return ClickHouseConnector(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 9000),
            database=db_config.get('database', 'default'),
            user=db_config.get('user', 'default'),
            password=db_config.get('password', ''),
            secure=db_config.get('secure', False),
            verify=db_config.get('verify', True),
            compression=db_config.get('compression', True)
        )
        
    elif db_type == 'osquery':
        return OsqueryConnector()
        
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


# For backward compatibility
def execute_query_compat(query: str, db_path: str) -> List[Dict[str, Any]]:
    """
    Backward compatible execute_query function.
    If db_path looks like a file path, use DuckDB directly.
    Otherwise, treat it as a database config dict.
    """
    if isinstance(db_path, str):
        # Legacy mode - direct file path
        connector = DuckDBConnector(db_path)
    elif isinstance(db_path, dict):
        # New mode - database config
        connector = create_connector(db_path)
    else:
        raise ValueError(f"Invalid db_path type: {type(db_path)}")
        
    return connector.execute_query(query)