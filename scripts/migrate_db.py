import sqlite3
import os

db_path = os.path.join("instance", "security.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

def add_column_if_missing(table, col_name, col_def):
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table});").fetchall()]
    if col_name not in cols:
        print(f"Adding column '{col_name}' to table '{table}'...")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def};")
        conn.commit()
    else:
        print(f"Column '{col_name}' already exists in table '{table}'.")

# 1. Update events table
add_column_if_missing("events", "severity", "VARCHAR(20) DEFAULT 'INFO'")
add_column_if_missing("events", "zone_name", "VARCHAR(100)")
add_column_if_missing("events", "is_acknowledged", "BOOLEAN DEFAULT 0")
add_column_if_missing("events", "acknowledged_at", "DATETIME")
add_column_if_missing("events", "acknowledged_by", "VARCHAR(100)")

# 2. Update notifications table
add_column_if_missing("notifications", "category", "VARCHAR(30) DEFAULT 'ALL'")
add_column_if_missing("notifications", "is_acknowledged", "BOOLEAN DEFAULT 0")

# 3. Create restricted_zones table if not exists
cur.execute("""
CREATE TABLE IF NOT EXISTS restricted_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    boundary_type VARCHAR(20) NOT NULL DEFAULT 'rectangle',
    coordinates_json TEXT NOT NULL DEFAULT '{}',
    allowed_hours_start VARCHAR(10) NOT NULL DEFAULT '08:00',
    allowed_hours_end VARCHAR(10) NOT NULL DEFAULT '20:00',
    authorized_person_ids_json TEXT NOT NULL DEFAULT '[]',
    alert_level VARCHAR(20) NOT NULL DEFAULT 'HIGH',
    enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()

# Seed default restricted zone if none
cur.execute("SELECT COUNT(*) FROM restricted_zones;")
if cur.fetchone()[0] == 0:
    cur.execute("""
    INSERT INTO restricted_zones (camera_id, name, boundary_type, coordinates_json, allowed_hours_start, allowed_hours_end, authorized_person_ids_json, alert_level, enabled)
    VALUES (1, 'Main Entrance Zone', 'rectangle', '{"x1": 0.2, "y1": 0.35, "x2": 0.8, "y2": 0.95}', '08:00', '20:00', '[]', 'HIGH', 1);
    """)
    conn.commit()
    print("Seeded default RestrictedZone 'Main Entrance Zone'")

conn.close()
print("Database schema migration complete!")
