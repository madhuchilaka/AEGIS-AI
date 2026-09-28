"""
Database Restore Utility
Restores SQLite database from an SQL dump file into the target database.
"""
import os
import sys
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "instance" / "security.db"
INPUT_PATH = BASE_DIR / "instance" / "security_dump.sql"

def restore_database(input_file=None, db_file=None):
    input_file = Path(input_file) if input_file else INPUT_PATH
    db_file = Path(db_file) if db_file else DB_PATH

    if not input_file.exists():
        print(f"[!] Dump file does not exist at: {input_file}")
        sys.exit(1)

    db_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"[*] Restoring database to: {db_file}")
    print(f"[*] From dump file: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    conn = sqlite3.connect(str(db_file))
    conn.executescript(sql_script)
    conn.commit()
    conn.close()

    print(f"[+] Database restored successfully from {input_file}!")

if __name__ == "__main__":
    in_arg = sys.argv[1] if len(sys.argv) > 1 else None
    db_arg = sys.argv[2] if len(sys.argv) > 2 else None
    restore_database(in_arg, db_arg)
