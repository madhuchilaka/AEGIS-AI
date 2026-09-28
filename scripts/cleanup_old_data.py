"""
Data Retention Cleanup CLI Script
Deletes snapshots and database events older than RETENTION_DAYS (default 30 days).
Can be scheduled via Windows Task Scheduler or cron.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from services.retention_service import retention_service

def main():
    days = None
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"Invalid days argument '{sys.argv[1]}'. Using configured retention.")

    app = create_app()
    with app.app_context():
        report = retention_service.run_cleanup(retention_days=days)
        print("\nCleanup Summary:")
        print(f"- Retention Window: {report['retention_days']} days (Cutoff: {report['cutoff_date']})")
        print(f"- Deleted Events: {report['deleted_events']}")
        print(f"- Deleted Files: {report['deleted_files']}")
        print(f"- Disk Space Freed: {report['freed_mb']} MB\n")

if __name__ == "__main__":
    main()
