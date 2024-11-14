# rebuild_indexes.py

"""
Database Index Rebuild Script for System Control Panel

This script rebuilds the SQLite database indexes for the System Control Panel application.
It should only be run if you're experiencing database performance issues or after
manual database modifications.

Note: This is a maintenance script that is automatically handled by the application
during normal operation. You should NOT need to run this unless specifically 
instructed to do so by the application maintainers.

What it does:
- Drops and recreates timestamp indexes for system_metrics and events tables
- Helps optimize query performance for time-based data retrieval
- Takes only a few seconds to complete on typical installations

Usage:
    python3 rebuild_indexes.py

The script will automatically connect to the application's database at 'data/metrics.db'
and perform the necessary index operations.
"""

import sqlite3

def rebuild_indexes():
    print("Rebuilding database indexes...")
    with sqlite3.connect('data/metrics.db') as conn:
        c = conn.cursor()
        # Drop existing indexes if they exist
        c.execute("DROP INDEX IF EXISTS idx_metrics_timestamp")
        c.execute("DROP INDEX IF EXISTS idx_events_timestamp")
        
        # Recreate indexes
        c.execute('''CREATE INDEX idx_metrics_timestamp 
                    ON system_metrics(timestamp)''')
        c.execute('''CREATE INDEX idx_events_timestamp 
                    ON events(timestamp)''')
        
        conn.commit()
    print("Database indexes rebuilt successfully")
    
rebuild_indexes()