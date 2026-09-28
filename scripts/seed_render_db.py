"""
Render Initialization & Database Seeding Helper
Ensures database tables are created, loads demo data / SQL dump if database is blank,
and guarantees the administrator account is present.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import create_app
from models import db, User, Camera, Event
import sqlite3

def init_render_deployment():
    app = create_app()
    with app.app_context():
        print("[*] Checking database initialization...")
        db.create_all()

        # Check if database has events or is completely blank
        dump_sql_path = BASE_DIR / "instance" / "security_dump.sql"
        if Event.query.count() == 0 and dump_sql_path.exists():
            print(f"[*] Database is blank. Importing seed dump from {dump_sql_path}...")
            try:
                db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
                if db_uri.startswith("sqlite:///"):
                    sqlite_path = db_uri.replace("sqlite:///", "")
                    conn = sqlite3.connect(sqlite_path)
                    with open(dump_sql_path, "r", encoding="utf-8") as f:
                        conn.executescript(f.read())
                    conn.commit()
                    conn.close()
                    print("[+] Seed SQL dump imported successfully into SQLite!")
            except Exception as e:
                print(f"[!] Warning: Could not import SQL dump: {e}")

        # Ensure Admin User exists
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            admin = User(
                username=admin_username,
                role="admin",
                full_name=os.environ.get("ADMIN_FULL_NAME", "System Administrator")
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f"[+] Admin account '{admin_username}' provisioned.")
        else:
            print(f"[*] Admin account '{admin_username}' verified.")

        print(f"[+] Render deployment check complete. Events: {Event.query.count()}, Cameras: {Camera.query.count()}, Users: {User.query.count()}")

if __name__ == "__main__":
    init_render_deployment()
