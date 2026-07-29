from initialize import index_path, Path
from utils import input_is
from typing import List
import json
import sqlite3
import time

DB_PATH = index_path / "index.sqlite3"

_conn: sqlite3.Connection | None = None


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
        _conn = conn
    return _conn


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
    Retrieves a list of pending URIs from the index.

    :return:    A list of URI strings with a pending entry.
    """
    rows = _get_conn().execute("SELECT uri FROM entries WHERE status = 'pending'").fetchall()
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
    if any(payload.values()):
        conn.execute(
            "INSERT INTO entries (uri, status, payload, updated_at) VALUES (?, 'pending', ?, ?) "
            "ON CONFLICT(uri) DO UPDATE SET status='pending', payload=excluded.payload, "
            "updated_at=excluded.updated_at",
            (str(uri), json.dumps(payload), time.time()),
        )
    else:
        conn.execute(
            "INSERT INTO entries (uri, status, payload, updated_at) VALUES (?, 'done', NULL, ?) "
            "ON CONFLICT(uri) DO UPDATE SET status='done', payload=NULL, "
            "updated_at=excluded.updated_at",
            (str(uri), time.time()),
        )


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

    conn = _get_conn()
    n_records = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    uris_to_do = to_do()
    n_to_do = len(uris_to_do)
    n_empty_records = n_records - n_to_do

    info = [
        ('number of processed records', n_empty_records),
        ('number of unprocessed records', n_to_do),
        ('location', DB_PATH),
    ]

    print('INDEX INFORMATION:',
          *['\n- {}{}'.format(k.ljust(30), str(v).rjust(6)) for k, v in info]
          )

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
    debug()
