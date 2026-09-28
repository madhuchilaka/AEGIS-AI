"""
Database Dump Utility
Exports the SQLite database (schemas, tables, and rows) into a standalone SQL dump file.
"""
import os
import sys
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "instance" / "security.db"
OUTPUT_PATH = BASE_DIR / "instance" / "security_dump.sql"

def dump_database(db_file=None, output_file=None):
    db_file = Path(db_file) if db_file else DB_PATH
    output_file = Path(output_file) if output_file else OUTPUT_PATH

    if not db_file.exists():
        print(f"[!] Database file does not exist at: {db_file}")
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"[*] Dumping database from: {db_file}")
    print(f"[*] Destination: {output_file}")

    conn = sqlite3.connect(str(db_file))
    with open(output_file, "w", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    conn.close()

    size_kb = output_file.stat().st_size / 1024
    print(f"[+] Dump completed successfully! Output file size: {size_kb:.2f} KB")

if __name__ == "__main__":
    db_arg = sys.argv[1] if len(sys.argv) > 1 else None
    out_arg = sys.argv[2] if len(sys.argv) > 2 else None
    dump_database(db_arg, out_arg)
