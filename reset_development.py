
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent

DATABASE_FILES = [
    BASE_DIR / "instance" / "school.db",
    BASE_DIR / "instance" / "school.db-wal",
    BASE_DIR / "instance" / "school.db-shm",
]

print("WARNING: All local school database records will be deleted.")
print("Stop Flask and background workers first.")

confirmation = input(
    "Type RESET ALL DATA to continue: "
).strip()

if confirmation != "RESET ALL DATA":
    raise SystemExit("Reset cancelled.")

database = DATABASE_FILES[0]

if database.exists():
    try:
        connection = sqlite3.connect(
            str(database),
            timeout=0
        )
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.rollback()
        finally:
            connection.close()

    except sqlite3.OperationalError as error:
        raise SystemExit(
            f"Database is locked: {error}"
        )

for file_path in DATABASE_FILES:
    if file_path.exists():
        file_path.unlink()
        print(f"Deleted: {file_path.name}")

print("Database reset complete.")
