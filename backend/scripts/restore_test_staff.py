"""One-time repair of the two documented demo fixtures recreated by iteration 8.

Never imported by startup or login. No account creation or general phone-based
privilege assignment. Exact IDs and current state are required for this repair.
"""
import argparse
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if os.environ.get("MSG91_AUTH_KEY") or os.environ.get("MSG91_TEMPLATE_ID"):
        raise SystemExit("Demo fixture repair is disabled when real SMS is configured")
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    fixtures = [
        ("efd1b56b-5616-48a6-b799-7797db944dd5", "9999999998", "admin", "Admin Kumar"),
        ("bd1399b5-3e24-4e89-b0ab-f9b11c569568", "9999999997", "team", "Ravi (Team)"),
    ]
    for uid, phone, role, name in fixtures:
        before = db.users.find_one({"id": uid, "phone": phone}, {"_id": 0})
        if not before or before.get("deleted") or before.get("disabled"):
            print(phone, "SKIPPED: missing or disabled; never resurrected")
            continue
        if db.users.count_documents({"phone": phone}) != 1:
            raise SystemExit("Duplicate phone: manual review required")
        if before["role"] == role:
            print(phone, "already correct")
            continue
        if before["role"] != "subscriber" or before["name"] != f"User {phone[-4:]}":
            raise SystemExit("Unexpected fixture state: manual review required")
        print(phone, "subscriber ->", role, "apply:", args.apply)
        if args.apply:
            # Preserve pre-repair data in an audit record; no user data removed.
            now = datetime.now(timezone.utc)
            db.maintenance_audit.insert_one({"id": str(uuid.uuid4()), "action": "restore_iter8_test_fixture", "before": before, "created_at": now})
            result = db.users.update_one(
                {"id": uid, "phone": phone, "role": "subscriber", "name": before["name"]},
                {"$set": {"role": role, "name": name, "demo_fixture_restored_at": now}},
                upsert=False,
            )
            if result.modified_count != 1:
                raise SystemExit("Fixture changed concurrently; stopped")
    client.close()


if __name__ == "__main__":
    main()