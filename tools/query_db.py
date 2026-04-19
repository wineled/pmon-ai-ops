import sqlite3, json, sys

conn = sqlite3.connect(r'C:\ProgramData\HskDDNS\orayfile-repo-data\orayfile.db')
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
print("Tables:", tables)

# Get schema for each table
for table in tables:
    print(f"\n=== {table} ===")
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    print("Columns:", cols)
    cur.execute(f"SELECT * FROM {table} LIMIT 5")
    rows = cur.fetchall()
    for row in rows:
        print(row)

conn.close()
