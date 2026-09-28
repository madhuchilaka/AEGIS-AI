"""
Admin Account Creation Script
Creates an initial administrator account with secure Werkzeug password hashing.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from models import db, User

def create_admin(username="admin", password="Admin@123", full_name="System Administrator"):
    if len(sys.argv) > 1:
        username = sys.argv[1]
    if len(sys.argv) > 2:
        password = sys.argv[2]
    if len(sys.argv) > 3:
        full_name = sys.argv[3]

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"User '{username}' already exists. Updating credentials to Admin role...")
            user.set_password(password)
            user.role = "admin"
            user.full_name = full_name
            db.session.commit()
            print(f"Admin user '{username}' updated successfully.")
        else:
            user = User(
                username=username,
                role="admin",
                full_name=full_name
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print(f"Admin user '{username}' created successfully.")

        print(f"\n======================================")
        print(f" Admin Credentials:")
        print(f" Username: {username}")
        print(f" Password: {password}")
        print(f" Role: admin")
        print(f"======================================\n")

if __name__ == "__main__":
    create_admin()
