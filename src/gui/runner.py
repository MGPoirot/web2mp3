"""
PTY-driven subprocess runner.

Each submission spawns a fresh `python src/main.py --sync <url>` attached to
a pseudo-terminal (not a plain pipe) -- see GUI_PLAN.md for why a PTY is
needed: it's what makes the child's stdout line-buffered and its input()
prompts flush immediately, exactly like a real interactive terminal session.

A background thread per submission reads the PTY master fd, appends output
to a transcript file (src/gui/sessions.py), and fans it out to any
subscribed WebSocket via an asyncio queue. An idle heuristic (no output for
IDLE_THRESHOLD seconds while the process is still alive) flags the
submission as 'needs_input' so the frontend can show an input box; the one
known, harmless exception is main.py's own trailing "any more URLs?" loop
prompt (we deliberately don't pass --headless, so this shows up too, see
below) -- that one specific, stable prompt string is auto-answered with a
blank line to end the session cleanly instead of being relayed as a real
question.
"""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initialize import home_dir  # noqa: E402
import sessions  # noqa: E402

IDLE_THRESHOLD = 0.4  # seconds of silence while alive => probably waiting for input
WIZARD_PROMPT_SENTINEL = '>>> URL or [Abort]?'

_active: dict[str, "_Submission"] = {}
_active_lock = threading.Lock()


class _Submission:
    def __init__(self, sid: str, url: str):
        self.sid = sid
        self.url = url
        self.proc: subprocess.Popen | None = None
        self.master_fd: int | None = None
        self.subscribers: list[tuple] = []  # (asyncio.Queue, asyncio event loop)
        self.lock = threading.Lock()
        self.closing = False  # True once we've auto-answered the trailing wizard prompt

    def _broadcast(self, message: dict) -> None:
        with self.lock:
            subs = list(self.subscribers)
        for queue, loop in subs:
            loop.call_soon_threadsafe(queue.put_nowait, message)

    def emit_output(self, text: str) -> None:
        with sessions.transcript_path(self.sid).open('a', encoding='utf-8') as f:
            f.write(text)
        self._broadcast({'type': 'output', 'text': text})

    def set_status(self, status: str) -> None:
        sessions.set_status(self.sid, status)
        self._broadcast({'type': 'status', 'status': status})


def _reader_thread(sub: _Submission) -> None:
    fd = sub.master_fd
    last_output = time.time()
    flagged_needs_input = False
    tail = ''

    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 0.2)
        except (OSError, ValueError):
            break

        if not ready:
            if sub.proc.poll() is not None:
                break
            # A multi-second gap between two complete, newline-terminated
            # log lines (e.g. waiting on a Spotify API call) is normal and
            # must NOT be flagged as needing input -- only a genuine
            # input()/click prompt leaves the output mid-line (no trailing
            # newline) while the process goes idle, so require both.
            ends_mid_line = bool(tail) and not tail.endswith('\n')
            if (
                ends_mid_line
                and not flagged_needs_input
                and not sub.closing
                and (time.time() - last_output) > IDLE_THRESHOLD
            ):
                flagged_needs_input = True
                sub.set_status('needs_input')
            continue

        try:
            chunk = os.read(fd, 4096)
        except OSError:
            # Reading from a PTY master after the child/slave side is gone
            # raises EIO on Linux rather than returning a clean EOF.
            break
        if not chunk:
            break

        text = chunk.decode('utf-8', errors='replace')
        sub.emit_output(text)
        last_output = time.time()
        tail = (tail + text)[-200:]

        if not sub.closing and WIZARD_PROMPT_SENTINEL in tail:
            # main.py's own harmless "any more URLs?" loop -- we don't pass
            # --headless (so match-phase logging still prints), so this
            # shows up once processing finishes. Auto-answer it rather than
            # relaying it as a real question.
            sub.closing = True
            try:
                os.write(fd, b'\n')
            except OSError:
                pass
            continue

        if flagged_needs_input:
            flagged_needs_input = False
            sub.set_status('running')

    rc = sub.proc.wait()
    sub.set_status('done' if rc == 0 else 'failed')
    try:
        os.close(fd)
    except OSError:
        pass
    with _active_lock:
        _active.pop(sub.sid, None)


def start(url: str) -> str:
    sid = sessions.create(url)
    sub = _Submission(sid, url)

    master_fd, slave_fd = pty.openpty()
    try:
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 200, 0, 0))
    except OSError:
        pass

    proc = subprocess.Popen(
        [sys.executable, str(home_dir / 'src' / 'main.py'), '--sync', url],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=str(home_dir),
        close_fds=True,
    )
    os.close(slave_fd)  # parent only needs the master end from here on

    sub.proc = proc
    sub.master_fd = master_fd
    with _active_lock:
        _active[sid] = sub

    threading.Thread(target=_reader_thread, args=(sub,), daemon=True).start()
    return sid


def subscribe(sid: str, loop, queue) -> bool:
    """Registers a live queue for a submission's output. False if it's not (or no longer) running."""
    with _active_lock:
        sub = _active.get(sid)
    if sub is None:
        return False
    with sub.lock:
        sub.subscribers.append((queue, loop))
    return True


def unsubscribe(sid: str, queue) -> None:
    with _active_lock:
        sub = _active.get(sid)
    if sub is None:
        return
    with sub.lock:
        sub.subscribers = [(q, l) for (q, l) in sub.subscribers if q is not queue]


def send_input(sid: str, text: str) -> bool:
    with _active_lock:
        sub = _active.get(sid)
    if sub is None or sub.proc.poll() is not None:
        return False
    try:
        os.write(sub.master_fd, (text + '\n').encode('utf-8'))
    except OSError:
        return False
    return True


def is_active(sid: str) -> bool:
    with _active_lock:
        return sid in _active


def reconcile_after_restart() -> None:
    """Any submission still 'running'/'needs_input' in the DB at server
    startup belongs to a process that no longer exists (the GUI server
    restarted) -- mark them failed so the sidebar doesn't show a
    permanently-stuck "running" entry."""
    for entry in sessions.list_all():
        if entry['status'] in ('running', 'needs_input'):
            sessions.set_status(entry['id'], 'failed')
