"""
One-off migration: converts the legacy file-per-URI index (one empty or
JSON-holding file per tracked URI directly under src/index/) into the
SQLite-backed index (src/index/index.sqlite3) that index.py now uses.

Safe to run multiple times: entries already present in the database are
left untouched (INSERT OR IGNORE), and legacy files are only deleted after
the row counts are verified and a backup archive has been written.

Usage: python src/migrate_index_to_sqlite.py
"""
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from initialize import index_path  # noqa: E402
import index as index_module  # noqa: E402

BACKUP_PATH = index_path / "index_legacy_backup.tar.gz"
SKIP_NAMES = {"index.sqlite3", "index.sqlite3-wal", "index.sqlite3-shm", BACKUP_PATH.name}


def find_legacy_files() -> list[Path]:
    return [
        p for p in index_path.iterdir()
        if p.is_file() and p.name not in SKIP_NAMES
    ]


def migrate() -> None:
    legacy_files = find_legacy_files()
    print(f"Found {len(legacy_files)} legacy index files under {index_path}")
    if not legacy_files:
        print("Nothing to migrate.")
        return

    conn = index_module._get_conn()

    conn.execute("BEGIN")
    n_done = 0
    n_pending = 0
    n_skipped_existing = 0
    now = time.time()
    for path in legacy_files:
        uri = path.name
        existing = conn.execute("SELECT 1 FROM entries WHERE uri = ?", (uri,)).fetchone()
        if existing is not None:
            n_skipped_existing += 1
            continue
        content = path.read_bytes()
        if content:
            conn.execute(
                "INSERT INTO entries (uri, status, payload, updated_at) VALUES (?, 'pending', ?, ?)",
                (uri, content.decode("utf-8"), now),
            )
            n_pending += 1
        else:
            conn.execute(
                "INSERT INTO entries (uri, status, payload, updated_at) VALUES (?, 'done', NULL, ?)",
                (uri, now),
            )
            n_done += 1
    conn.execute("COMMIT")

    print(f"Inserted {n_done} done + {n_pending} pending entries "
          f"({n_skipped_existing} already present, skipped).")

    # Verify: every legacy URI must now have a row.
    missing = [
        p.name for p in legacy_files
        if conn.execute("SELECT 1 FROM entries WHERE uri = ?", (p.name,)).fetchone() is None
    ]
    if missing:
        raise RuntimeError(
            f"Migration verification failed: {len(missing)} URIs missing from the "
            f"database after insert, e.g. {missing[:5]}. Legacy files were NOT deleted."
        )
    print("Verification passed: every legacy URI has a corresponding database row.")

    print(f"Archiving {len(legacy_files)} legacy files to {BACKUP_PATH} ...")
    with tarfile.open(BACKUP_PATH, "w:gz") as tar:
        for path in legacy_files:
            tar.add(path, arcname=path.name)
    print("Backup archive written.")

    for path in legacy_files:
        path.unlink()
    print(f"Deleted {len(legacy_files)} legacy files from {index_path}.")

    remaining = sorted(p.name for p in index_path.iterdir())
    print(f"{index_path} now contains: {remaining}")


if __name__ == "__main__":
    migrate()
