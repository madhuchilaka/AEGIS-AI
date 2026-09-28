import sqlite3

conn = sqlite3.connect("instance/security.db")
cur = conn.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables in security.db:")
for (name,) in tables:
    count = cur.execute(f"SELECT COUNT(*) FROM \"{name}\";").fetchone()[0]
    print(f"  {name}: {count} records")

cols = cur.execute("PRAGMA table_info(events);").fetchall()
print("\nEvents columns:")
for col in cols:
    print(f"  {col[1]} ({col[2]})")

users = cur.execute("SELECT id, username, role FROM users;").fetchall()
print("\nUsers:", users)
conn.close()
