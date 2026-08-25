from initialize import index_path, Path
from utils import input_is
from typing import List, Optional, Tuple
import json
import sqlite3
import sys
import time

DB_PATH = index_path / "index.sqlite3"

_conn: sqlite3.Connection | None = None


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            uri        TEXT PRIMARY KEY,
            status     TEXT NOT NULL CHECK (status IN ('pending', 'done')),
            payload    TEXT,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status)")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    if "last_attempt_at" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN last_attempt_at REAL")
    if "perm_fail_count" not in cols:
        conn.execute(
            "ALTER TABLE entries ADD COLUMN perm_fail_count INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blacklist (
            uri        TEXT PRIMARY KEY,
            reason     TEXT,
            error      TEXT,
            fail_count INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        )
        """
    )


def _get_conn() -> sqlite3.Connection:
    """
    Lazily opens (and initializes the schema of) the module-level SQLite
    connection. One connection per process is the correct usage pattern for
    concurrent multi-process SQLite access under WAL mode, which is what
    lets the 4 DAEMON processes read/write the index concurrently.
    """
    global _conn
    if _conn is None:
        conn = sqlite3.connect(str(DB_PATH), timeout=5, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _ensure_schema(conn)
        _conn = conn
    return _conn


def reset_conn_for_tests() -> None:
    """Close the module connection so tests can point DB_PATH at a temp file."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def has_uri(uri: str | Path) -> bool:
    """
    Checks if the URI has an entry in the index.

    :param uri:     A URI string or Path object representing the index item.
    :return:        True if an entry exists, False otherwise.
    """
    row = _get_conn().execute(
        "SELECT 1 FROM entries WHERE uri = ?", (str(uri),)
    ).fetchone()
    return row is not None


def read(uri: str | Path) -> dict | None:
    """
    Reads and returns the pending payload for a URI from the index.

    :param uri:     A URI string or Path object representing the index item.
    :return:        A dictionary with the JSON content if the entry is
                    pending, or `None` if the entry is done or absent.
    """
    row = _get_conn().execute(
        "SELECT payload FROM entries WHERE uri = ? AND status = 'pending'", (str(uri),)
    ).fetchone()
    return None if row is None else json.loads(row[0])


def to_do() -> List[str]:
    """
    Retrieves pending URIs, never-tried first, then least-recently attempted.
    """
    rows = _get_conn().execute(
        """
        SELECT uri FROM entries
        WHERE status = 'pending'
        ORDER BY last_attempt_at IS NOT NULL, last_attempt_at, updated_at
        """
    ).fetchall()
    return [r[0] for r in rows]


def write(
        uri: str | Path,
        tags: dict | None = None,
        settings: dict | None = None,
        overwrite: bool = True,
) -> None:
    """
    Writes a value to a key (short URL) in the index.

    :param uri:         A URI string or Path object representing the index item.
    :param tags:        A dictionary of tags to associate with the key (default: `None`).
    :param settings:    A dictionary of settings to associate with the key (default: `None`).
    :param overwrite:   A boolean indicating whether to overwrite existing data (default: `True`).

    :return:            None.
    """
    if not overwrite and has_uri(uri):
        return
    payload = {'tags': tags, 'settings': settings}
    conn = _get_conn()
    now = time.time()
    if any(payload.values()):
        conn.execute(
            "INSERT INTO entries (uri, status, payload, updated_at, last_attempt_at, perm_fail_count) "
            "VALUES (?, 'pending', ?, ?, NULL, 0) "
            "ON CONFLICT(uri) DO UPDATE SET status='pending', payload=excluded.payload, "
            "updated_at=excluded.updated_at, last_attempt_at=NULL, perm_fail_count=0",
            (str(uri), json.dumps(payload), now),
        )
    else:
        conn.execute(
            "INSERT INTO entries (uri, status, payload, updated_at) VALUES (?, 'done', NULL, ?) "
            "ON CONFLICT(uri) DO UPDATE SET status='done', payload=NULL, "
            "updated_at=excluded.updated_at",
            (str(uri), now),
        )


def record_attempt(uri: str | Path) -> None:
    """Bump last_attempt_at so this pending URI rotates behind never-tried ones."""
    _get_conn().execute(
        "UPDATE entries SET last_attempt_at = ? WHERE uri = ? AND status = 'pending'",
        (time.time(), str(uri)),
    )


def record_permanent_failure(uri: str | Path) -> int:
    """Increment perm_fail_count and last_attempt_at. Returns the new count (0 if no row)."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        "UPDATE entries SET last_attempt_at = ?, perm_fail_count = perm_fail_count + 1 "
        "WHERE uri = ? AND status = 'pending'",
        (now, str(uri)),
    )
    row = conn.execute(
        "SELECT perm_fail_count FROM entries WHERE uri = ?", (str(uri),)
    ).fetchone()
    return int(row[0]) if row else 0


def blacklist_uri(uri: str | Path, reason: str, error: str, fail_count: Optional[int] = None) -> None:
    """Record a permanent download failure and mark the entry done."""
    conn = _get_conn()
    key = str(uri)
    if fail_count is None:
        row = conn.execute(
            "SELECT perm_fail_count FROM entries WHERE uri = ?", (key,)
        ).fetchone()
        fail_count = int(row[0]) if row else 1
    now = time.time()
    conn.execute(
        "INSERT INTO blacklist (uri, reason, error, fail_count, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(uri) DO UPDATE SET reason=excluded.reason, error=excluded.error, "
        "fail_count=excluded.fail_count, updated_at=excluded.updated_at",
        (key, reason, error, fail_count, now),
    )
    write(key)


def is_blacklisted(uri: str | Path) -> bool:
    row = _get_conn().execute(
        "SELECT 1 FROM blacklist WHERE uri = ?", (str(uri),)
    ).fetchone()
    return row is not None


def blacklist_count() -> int:
    return _get_conn().execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]


def list_pending() -> List[Tuple[str, Optional[float]]]:
    rows = _get_conn().execute(
        """
        SELECT uri, last_attempt_at FROM entries
        WHERE status = 'pending'
        ORDER BY last_attempt_at IS NOT NULL, last_attempt_at, updated_at
        """
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def list_blacklist() -> List[Tuple[str, str, str, int, float]]:
    rows = _get_conn().execute(
        "SELECT uri, reason, error, fail_count, updated_at FROM blacklist ORDER BY updated_at"
    ).fetchall()
    return [(r[0], r[1] or "", r[2] or "", int(r[3]), float(r[4])) for r in rows]


def _fmt_attempt(ts: Optional[float]) -> str:
    if ts is None:
        return "never"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def print_pending() -> None:
    rows = list_pending()
    print(f"PENDING ({len(rows)}):")
    for uri, last_attempt in rows:
        print(f"  {uri}\tlast_attempt={_fmt_attempt(last_attempt)}")


def print_blacklist() -> None:
    rows = list_blacklist()
    print(f"BLACKLIST ({len(rows)}):")
    for uri, reason, error, fail_count, _updated in rows:
        err = error.replace("\n", " ")
        if len(err) > 160:
            err = err[:157] + "..."
        print(f"  {uri}\treason={reason}\tfails={fail_count}\t{err}")


def summary() -> int:
    """
    Prints index statistics (processed/unprocessed record counts, location).
    Non-interactive — used standalone by the `inspect` CLI subcommand, and
    as the first step of the interactive `debug()` below.

    :return: The number of pending (unprocessed) URIs.
    """
    conn = _get_conn()
    n_records = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    uris_to_do = to_do()
    n_to_do = len(uris_to_do)
    n_empty_records = n_records - n_to_do
    n_blacklisted = blacklist_count()

    info = [
        ('number of processed records', n_empty_records),
        ('number of unprocessed records', n_to_do),
        ('number of blacklisted records', n_blacklisted),
        ('location', DB_PATH),
    ]

    print('INDEX INFORMATION:',
          *['\n- {}{}'.format(k.ljust(30), str(v).rjust(6)) for k, v in info]
          )
    return n_to_do


def debug() -> None:
    """
    Provides an interactive interface for debugging and managing the index.

    This function allows the user to:
    - View statistics about the index (number of records, processed/unprocessed records).
    - View detailed information about individual items in the database.
    - Delete or clear items from the database.
    """

    def _pretty_print(uri: str) -> None:
        print(json.dumps(read(uri), indent=4, sort_keys=True))

    def _pop_uri_from_index(uri: str) -> None:
        _get_conn().execute("DELETE FROM entries WHERE uri = ?", (uri,))
        print(f'Deleted index item "{uri}"')

    n_to_do = summary()
    uris_to_do = to_do()

    if not n_to_do:
        return

    look_closer = input('>>> Do you want to see a list of items,'
                        ' or check per item? List / Item / [No]  ')

    if not input_is('List', look_closer) and not input_is('Item', look_closer):
        return

    for i, uri in enumerate(uris_to_do):
        print(f'{str(i + 1).rjust(3)}/{n_to_do}:', uri)
        _pretty_print(uri)

        if input_is('Item', look_closer):
            do_pop = input(
                '>>> Do you want to permanently delete or clear this '
                'item from the index? Delete / Clear / [No]  ')
            if input_is('Delete', do_pop):
                _pop_uri_from_index(uri)
                msg = 'deleted'
            elif input_is('Clear', do_pop):
                write(uri)
                msg = 'cleared'
            else:
                msg = 'untouched'
            print(f'Index entry {msg}.')


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--pending' in args:
        print_pending()
    elif '--blacklist' in args:
        print_blacklist()
    elif '--summary' in args:
        summary()
    else:
        debug()
