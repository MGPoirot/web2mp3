# Web2MP3 GUI — Design Plan

## Context

Today the only way to use web2mp3 is `docker exec ... dl <url>`. The goal is an
optional single-page web GUI (port 4546) that lets you paste a URL into a
textbox and watch the exact same matching → download → tagging pipeline the
CLI runs, without needing a shell. It must stay fully optional (toggleable
per-deployment) and must not change any existing CLI behavior.

Two problems make this harder than "run a shell command and show its
output":

1. **Interactive input.** When there's no clear match, the CLI blocks on
   `input()` — asking the user to pick a candidate, retry, or enter metadata
   manually. A web page can't block; it needs some way to detect "the process
   is waiting for input" and turn that into an on-page prompt whose answer
   gets fed back to the process.
2. **Per-submission output isolation.** The CLI is one continuous log
   stream. The GUI should show each submission its own clean output, and
   (per your request) keep a sidebar of past submissions, ChatGPT-style.

Your own proposed architecture — invoke the CLI fresh per submission, capture
its output to a file, stream that file over a WebSocket — solves both
problems well and is what this plan builds on directly, plus a PTY, which is
the missing piece that makes the interactive-input part actually work.

## Architecture

```
Browser  <--WS/HTTP-->  FastAPI app (src/gui/server.py)
                              |
                         runner.py: spawns `python src/main.py --headless --sync <url>`
                         attached to a PTY (not a plain pipe)
                              |
                    stdout+stdin <-> PTY master fd, read/written by runner.py
                              |
                    transcript appended to .gui/transcripts/<id>.log
                    metadata tracked in .gui/sessions.sqlite3
```

**Why a PTY, not a plain subprocess pipe:** Python's `input()` writes its
prompt to stdout with no trailing newline, and when stdout isn't a terminal,
Python fully-buffers it — the prompt text can sit in an internal buffer and
never reach a plain pipe until much more output accumulates. A PTY makes the
child process's stdout behave exactly like a real interactive terminal
(line-buffered, prompts flush immediately), which is what lets the backend
reliably see a prompt appear and detect that the process has gone idle
waiting for a reply.

**Why a fresh subprocess per submission, not in-process calls:** this is
your own proposed design, and it's the right call — it means **zero changes
are needed to the existing matching/download logic** (`main.py`,
`modules/youtube.py`, `modules/spotify.py`, `tag_manager.py` all stay
untouched apart from one additive flag, see below). Each submission also
gets full isolation: a crash in one doesn't affect another or the GUI server
itself, and `tag_manager.py`'s module-level caches don't leak across
concurrent submissions the way they would if calls happened in one shared
process.

## Key design decisions

- **Frontend stack: plain HTML + CSS + vanilla JavaScript. No framework, no
  build step, no bundler, no npm at all.** The actual UI surface is small
  (textbox, submit button, scrolling output box, sidebar list, an input box
  that appears/disappears) — native `fetch()` for REST calls, the native
  `WebSocket` API for streaming, and plain DOM updates
  (`createElement`/`textContent`/`appendChild`) are all it needs; nothing
  here benefits enough from a framework's data-binding to justify one. This
  repo has zero frontend tooling today, and adding a Node/npm build stage to
  the Docker image just to produce a handful of DOM interactions would be a
  lot of new toolchain for what the page actually does. CSS is hand-written,
  no CDN-hosted framework either, so the page stays fully self-contained —
  relevant since this may run on a LAN-only NAS with no guaranteed internet
  access at page-load time. Served directly as static files by FastAPI's
  `StaticFiles`. (The one real alternative worth naming is
  [htmx](https://htmx.org) — a single ~14kb script tag, still no build step
  — if more declarative server-driven interactivity is ever wanted later;
  skipped for now since the core interaction, idle-detection triggering a
  dynamic input box plus live WebSocket streaming, is custom enough that
  plain JS is more direct than adopting htmx's own conventions for it.)
- **Toggle**: new `GUI_ENABLED` env var (default `true`), fully separate
  from the CLI's existing `--headless` flag (which means something
  unrelated: whether the CLI drops into its "any more URLs?" loop). When
  `GUI_ENABLED=false`, the container behaves exactly as it does today
  (`sleep infinity`, use via `docker exec`).
- **Auth**: optional shared-secret gate via `GUI_PASSWORD`. Unset (default)
  → no auth, fine for LAN-only use. Set → HTTP Basic Auth required on every
  route (browsers natively prompt for credentials and cache them per-origin,
  including for the WebSocket upgrade — no custom login page/session/cookie
  code needed). Compared with `secrets.compare_digest` to avoid timing
  attacks.
- **New `--sync` flag on `main.py`** (opt-in, default off, zero effect on
  existing behavior): normally, after a match, `main()` hands the actual
  download off to detached background daemons and returns immediately — the
  CLI itself never shows download/tagging completion. For the GUI, that
  would mean the output box trails off after "match added" with no visible
  ending. `--sync` instead calls `download_daemon.download_track()`
  directly, in-process, right after a successful match, so one continuous
  stream shows match → download → tag → done. Requires one small additive
  change: `match_audio_with_tags()` returns the `track_uri` it just added
  (currently returns nothing used by callers) so `main()` knows what to
  download when `--sync` is set.
- **GUI invokes**: `python src/main.py --headless --sync <url>` — headless
  skips the trailing "any more URLs?" loop (irrelevant/unwanted for a
  one-shot GUI submission), and deliberately omits `--response`, so
  ambiguous-match prompts still fire and get relayed to the browser instead
  of being silently auto-resolved.
- **Idle-as-input-needed heuristic**: rather than pattern-matching the
  app's exact prompt strings (fragile, breaks if wording changes), the
  runner treats "no new output for ~400ms while the process is still alive"
  as "probably waiting for input" and surfaces an input box. Simple, and
  robust to future prompt wording changes.

## Components

### `src/gui/sessions.py` — submission history
Mirrors the existing SQLite pattern in `src/index.py`. New DB at
`.gui/sessions.sqlite3`:
```sql
CREATE TABLE submissions (
    id         TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    status     TEXT NOT NULL,   -- running | needs_input | done | failed
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
```
Transcripts live separately as plain text: `.gui/transcripts/<id>.log`.

### `src/gui/runner.py` — process/PTY driver
- `start(url) -> id`: allocates a uuid, `pty.openpty()`, spawns the
  subprocess attached to the PTY slave, inserts a `submissions` row
  (`status='running'`).
- A background thread does blocking reads on the PTY master fd (PTY fds
  aren't natively asyncio-friendly), appends each chunk to the transcript
  file, and hands it to the asyncio event loop (`call_soon_threadsafe`) to
  fan out to any connected WebSocket for that id and to flip
  `status` between `running`/`needs_input` based on the idle heuristic.
- `send_input(id, text)`: writes `text + "\n"` to the PTY master fd; only
  valid while `status == 'needs_input'`.
- On process exit: final status `done` or `failed` (by exit code), fds
  closed.

### `src/gui/server.py` — FastAPI app
- `GET /` → `static/index.html`
- `POST /api/submit {url}` → starts a submission, returns `{id}`
- `GET /api/sessions` → list for the sidebar (id, url, status, created_at)
- `GET /api/sessions/{id}/transcript` → full text so far (for reopening a
  past/finished submission without needing the live socket)
- `WS /ws/{id}` → server pushes new output chunks; client sends
  `{"input": "..."}` to answer a prompt
- All routes behind the optional Basic Auth dependency described above.

### `static/index.html` + `app.js` + `style.css`
Plain HTML/JS, no build step or framework — matches the project's existing
lightweight style and the scope genuinely doesn't need more:
- Title "Web2MP3", a URL textbox + submit button at the top (Google-style).
- Left sidebar: past submissions (from `/api/sessions`), click to load.
- Main panel: monospace auto-scrolling output box; when status flips to
  `needs_input`, a text input + send button appears inline and posts to the
  WebSocket.
- On submit: POST `/api/submit`, immediately add an optimistic sidebar
  entry, open `WS /ws/{id}`, stream chunks into the output box.

## File changes

- **New**: `src/gui/__init__.py`, `server.py`, `runner.py`, `sessions.py`,
  `static/index.html`, `static/app.js`, `static/style.css`
- **New**: `docker-cmd.sh` (repo root, same convention as `dl`/`cookie`/
  `inspect`) — becomes the Dockerfile's `CMD`:
  ```sh
  #!/bin/sh
  if [ "${GUI_ENABLED:-true}" = "true" ]; then
      exec python -m uvicorn src.gui.server:app --host 0.0.0.0 --port 4546
  else
      exec sleep infinity
  fi
  ```
  `docker-entrypoint.sh` is unchanged — it already just privilege-drops and
  `exec`s whatever CMD it's given.
- **`Dockerfile`**: `COPY docker-cmd.sh /usr/local/bin/docker-cmd.sh` (+
  chmod), change `CMD ["sleep", "infinity"]` → `CMD ["docker-cmd.sh"]`.
- **`requirements.txt`**: add `fastapi` and `uvicorn[standard]` (pulls in
  `websockets`).
- **`docker-compose.yml`**: add `ports: ["${GUI_PORT:-4546}:4546"]` and a
  new volume `./.gui:/app/.gui` (so submission history survives restarts,
  same pattern as `.config`/`.logs`).
- **`.env.example`**: document `GUI_ENABLED` (default true), `GUI_PORT`
  (default 4546), `GUI_PASSWORD` (optional, unset = no auth).
- **`.gitignore`/`.dockerignore`**: add `.gui/` (runtime state).
- **`src/main.py`**: additive `--sync` click option; `match_audio_with_tags`
  returns the added `track_uri` (or `None`).
- **`README.md`**: new section documenting the GUI, its env vars, and the
  auth behavior.

Nothing in `modules/youtube.py`, `modules/spotify.py`, `tag_manager.py`,
`download_daemon.py`, or the existing `dl`/`cookie`/`inspect` commands
changes at all.

## Verification plan

1. `GUI_ENABLED=true`, no `GUI_PASSWORD`: visit `http://<host>:4546` with no
   login prompt. Submit a known-good URL, confirm the output box streams
   match → download → tag → done and the mp3 lands correctly (cross-check
   against `inspect`).
2. Submit a URL that produces an ambiguous match: confirm an input box
   appears, answering it (e.g. picking a numbered option) resumes the
   stream to completion.
3. Reload the page: confirm the sidebar lists prior submissions, and
   clicking a finished one shows its full transcript.
4. Set `GUI_PASSWORD`: confirm the browser prompts for credentials and
   wrong credentials are rejected; unset it and confirm no prompt.
5. `GUI_ENABLED=false`: confirm the container just idles, port 4546 isn't
   listening, and `docker exec ... dl/cookie/inspect` all still work
   exactly as before.
6. Run the existing manual regression pass for `dl`/`cookie`/`inspect` and
   a normal (non-GUI) headless download to confirm zero behavior change
   when the GUI isn't involved.
