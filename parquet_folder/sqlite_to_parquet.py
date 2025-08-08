#!/usr/bin/env python3
import sqlite3
import pandas as pd
import pyarrow.parquet as pq
import sys

def export_sqlite_to_parquet(db_path):
    conn = sqlite3.connect(db_path)
    
    # Get all table names
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table';", conn
    )
    
    for table_name in tables['name']:
        print(f"Exporting {table_name}...")
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        df.to_parquet(f"{table_name}.parquet", engine='pyarrow')
        print(f"✓ Saved {table_name}.parquet")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sqlite_to_parquet.py <database.db>")
        sys.exit(1)
    
    export_sqlite_to_parquet(sys.argv[1])


