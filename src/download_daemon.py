from initialize import music_dir, daemon_dir, log_dir, disp_daemons, glob, Path

import logging
import subprocess
import time
from utils import get_url_platform, get_path_components, track_exists, clip_path_length, call_with_backoff
import os
import index
from download_errors import classify_download_error
from tag_manager import download_cover_img, set_file_tags
import atexit
import sys
import click

PERMANENT_FAIL_LIMIT = 3
STALE_LOCK_TTL_SECONDS = 30 * 60


class LockFile:
    """Simple lock/marker file with optional stale detection.

    This intentionally stays file-based to avoid breaking other modules that
    expect daemon/task markers to exist under daemon_dir.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.touch()

    def touch(self) -> None:
        # write pid; also updates mtime (used by optional stale checks)
        self.path.write_text(str(os.getpid()), encoding="utf-8")

    def rm(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def is_stale(self, ttl_seconds: int) -> bool:
        try:
            return (time.time() - self.path.stat().st_mtime) > ttl_seconds
        except FileNotFoundError:
            return False


def download_track(track_uri: str, logger: logging.Logger | None = None) -> None:
    """
    This handles downloading audio from YouTube and setting the right mp3 tags.

    :param track_uri:
    :param logger:
    :return: Does not return anything
    """
    logger = logger or logging.getLogger(__name__)
    conclusion = "failed."
    logger.info('Started download_track for "%s"', track_uri)

    try:
        conclusion = _download_track_body(track_uri, logger)
    except Exception as e:
        kind, reason = classify_download_error(e)
        logger.error("download_track %s failure (%s): %s", kind, reason, e)
        if kind == "permanent":
            count = index.record_permanent_failure(track_uri)
            if count >= PERMANENT_FAIL_LIMIT:
                index.blacklist_uri(track_uri, reason, str(e), fail_count=count)
                logger.info(
                    "Blacklisted %s after %d permanent failures: %s",
                    track_uri,
                    count,
                    reason,
                )
                conclusion = "failed permanently; blacklisted."
            else:
                logger.info(
                    "Permanent failure %d/%d for %s: %s",
                    count,
                    PERMANENT_FAIL_LIMIT,
                    track_uri,
                    reason,
                )
        else:
            index.record_attempt(track_uri)

    logger.info("download_track %s", conclusion)


def _download_track_body(track_uri: str, logger: logging.Logger) -> str:
    download_info = index.read(track_uri)
    if download_info is None:
        logger.warning(
            'No pending download entry for "%s". This means the match step '
            "above did not actually add this URI as pending -- it either "
            "failed, was already marked done from an earlier attempt, or "
            "there's a URI mismatch bug. Check the "
            "match log lines above (look for Success/Skipped/Failed) and "
            "resubmit the URL if needed.",
            track_uri,
        )
        return "failed."

    settings = download_info["settings"]
    mp3_tags = download_info["tags"]

    avoid_duplicates = settings["avoid_duplicates"]
    do_overwrite = settings["do_overwrite"]
    ps = settings["print_space"]
    preferred_quality = settings["quality"]

    artist_p, album_p, track_p = get_path_components(mp3_tags)

    file_exists = False
    if avoid_duplicates and any(track_exists(artist_p, track_p)):
        logger.info("Skipped: FileExists")
        file_exists = True
    else:
        album_dir = clip_path_length(music_dir / artist_p / album_p)
        tr_prefix = None if mp3_tags.get("track_num") is None else f'{mp3_tags["track_num"]} - '
        mp3_fname = album_dir / f"{tr_prefix}{track_p}.mp3"
        os.makedirs(album_dir, exist_ok=True)

        art_fname = album_dir.parent / "artist.jpg"
        art_exists = art_fname.is_file()

        cov_fname = album_dir / "folder.jpg"
        cov_exists = cov_fname.is_file()

        logger.info('%s "%s"', "Album dir".ljust(ps), album_dir)
        logger.info('%s "%s"', "MP3 Audio filename".ljust(ps), mp3_fname)
        logger.info('%s "%s"', "Artist filename   ".ljust(ps), art_fname)
        logger.info('%s "%s"', "Cover filename    ".ljust(ps), cov_fname)

        if "artist_image" not in mp3_tags:
            logger.warning("KeyError: Artist Image URL was not set at all")
            artist_url = None
        else:
            artist_url = mp3_tags.pop("artist_image")

        if "cover" not in mp3_tags:
            logger.warning("KeyError: Cover URL was not set at all")
            cover_url = None
        else:
            cover_url = mp3_tags.pop("cover")

        if artist_url is None:
            logger.warning("ValueError: No artist image URL set.")
        elif art_exists and not do_overwrite:
            logger.info('%s "%s"', "FileExistsWarning:".ljust(ps), art_fname)
        else:
            if art_exists:
                logger.info('%s "%s"', "File Overwritten:".ljust(ps), art_fname)
            call_with_backoff(
                download_cover_img,
                art_fname,
                artist_url,
                logger=logger,
                backoff_logger=logger,
                print_space=ps,
            )

        if cover_url is None:
            logger.warning("ValueError: No cover URL set.")
        elif cov_exists and not do_overwrite:
            logger.info('%s "%s"', "FileExistsWarning:".ljust(ps), cov_fname)
        else:
            if cov_exists:
                logger.info('%s "%s"', "File Overwritten:".ljust(ps), cov_fname)
            call_with_backoff(
                download_cover_img,
                cov_fname,
                cover_url,
                logger=logger,
                backoff_logger=logger,
                print_space=ps,
            )

        download_method = get_url_platform(track_uri)
        track_url = download_method.uri2url(track_uri)

        if do_overwrite and os.path.isfile(mp3_fname):
            logger.info('%s "%s"', "File Overwritten:".ljust(ps), mp3_fname)
            os.remove(mp3_fname)

        call_with_backoff(
            download_method.audio_download,
            track_url,
            mp3_fname,
            preferred_quality,
            logger=logger,
            backoff_logger=logger,
        )

        if os.path.isfile(mp3_fname):
            file_exists = True
            set_file_tags(
                mp3_tags=mp3_tags,
                file_name=mp3_fname,
                audio_source_url=track_url,
                logger=logger,
            )

    if file_exists:
        index.write(track_uri, overwrite=True)
        logger.info("Index item cleared to None.")
        return "finished successfully."

    index.record_attempt(track_uri)
    logger.error("download produced no mp3 without an exception")
    return "failed."


def syscall(
    verbose: bool = False,
    sleep_seconds: int = 10,
    verbose_continuous: bool = False,
) -> subprocess.Popen:
    """Spawn a daemon process.

    Uses subprocess (no shell), so it's cross-platform and doesn't depend on '&' or pythonw.
    Keeps prior behavior: non-verbose spawns a headless background process.

    Verbose is the opposite case: the child inherits this process's stdout/stderr
    and stays in the same session, so the point of asking for verbose -- seeing
    the download happen -- actually holds.
    """
    args = [
        sys.executable,
        __file__,
        "--sleep_seconds",
        str(sleep_seconds),
    ]
    if verbose:
        args.append("--verbose")
    if verbose_continuous:
        args.append("--verbose_continuous")

    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=None if verbose else subprocess.DEVNULL,
        stderr=None if verbose else subprocess.DEVNULL,
        # Detaching a verbose daemon would orphan the output we just asked it for.
        start_new_session=(os.name != "nt" and not verbose),
        creationflags=(0x00000008 | 0x00000200) if os.name == "nt" and not verbose else 0,
        close_fds=True,
    )


def start_daemons(
    max_daemons: int = 4,
    verbose: bool = False,
    sleep_seconds: int = 10,
    verbose_continuous: bool = False,
) -> int:
    """
    .. py:function:: start_daemons(max_daemons=4, verbose=False)

    Initiates a number of downloading Daemons.

    NOTE: This function is called by other modules. The signature remains backward-compatible:
    callers that don't pass sleep_seconds will get the default (10).

    :param int max_daemons: The number up until new daemons will be started.
    :param bool verbose: Whether to run the daemon process in the foreground
    :param int sleep_seconds: Seconds to sleep between downloads (per daemon)
    :param bool verbose_continuous: When verbose, keep going after 1 item

    :return: Number of daemon processes started
    :rtype: int
    """
    if verbose:
        proc = syscall(
            verbose=True,
            sleep_seconds=sleep_seconds,
            verbose_continuous=verbose_continuous,
        )
        # Foreground means foreground: block, or the caller races the child for
        # the terminal (and for stdin, if it goes on to prompt for more URLs).
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
        return 1

    n_started = 0
    # Only try to start daemons when there are tasks to do
    for _i, _ in zip(range(max_daemons), get_tasks()):
        n_daemons = len(glob(daemon_dir.format("[0-9]")))
        if n_daemons < max_daemons:
            # syscall already spawns a background process correctly; no need for multiprocessing wrapper
            proc = syscall(verbose=False, sleep_seconds=sleep_seconds)
            # Give it a brief moment to fail fast (e.g. a bad CLI arg) rather
            # than trusting a bare Popen() call as proof it's actually
            # running -- otherwise this count can silently lie forever.
            time.sleep(0.3)
            if proc.poll() is None:
                n_started += 1
            else:
                print(f'Warning: a DAEMON failed to start (exit code {proc.returncode}).')
        else:
            break
    return n_started


def uri2tmp(n, uri: str | Path) -> str:
    """URI to TMP marker name."""
    return daemon_dir.format(f"{n}_{str(uri)}")


def sweep_stale_locks(ttl_seconds: int = STALE_LOCK_TTL_SECONDS) -> int:
    """Remove daemon/task markers whose pid is dead or whose mtime is too old."""
    removed = 0
    now = time.time()
    for path in glob(daemon_dir.format("*")):
        stale = False
        pid = None
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text.isdigit():
                pid = int(text)
        except (OSError, ValueError):
            pid = None

        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                stale = True
            except PermissionError:
                pass
            except OSError:
                stale = True

        if not stale:
            try:
                if (now - path.stat().st_mtime) > ttl_seconds:
                    stale = True
            except FileNotFoundError:
                continue

        if stale:
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass
    return removed


def get_tasks() -> list:
    """Return list of unprocessed URIs that are not currently busy (no tmp marker present)."""
    sweep_stale_locks()
    uris = index.to_do()
    uris = [u for u in uris if not any(glob(uri2tmp("*", u)))]  # busy
    return uris


@click.command()
@click.version_option()
@click.option("-x", "--max_daemons", default=4, help="Number of DAEMONs to spawn as integer")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Whether to download in foreground as bool")
@click.option(
    "-c",
    "--verbose_continuous",
    "--continuous",
    "verbose_continuous",
    is_flag=True,
    default=False,
    help="When verbose, whether to continue after 1 item",
)
@click.option(
    "-t",
    "--sleep_seconds",
    default=10,
    type=int,
    help="Seconds to sleep between downloads to avoid rate limiting",
)
def daemon_job(max_daemons: int = 4, verbose: bool = False, verbose_continuous: bool = False, sleep_seconds: int = 10):
    # Local import to avoid breaking callers if logging_setup import paths differ in other contexts
    from logging_setup import configure_logger

    daemon_logger = configure_logger(
        name="web2mp3.daemon",
        log_file=log_dir.format(f"daemon-{os.getpid()}", "log"),
        console=bool(verbose),
    )

    sweep_stale_locks()

    # List daemons that are not running
    daemon_ns = [i for i in range(max_daemons) if not daemon_dir.format(i).is_file()]

    if max_daemons == -1:
        # For -1 we always add a daemon
        daemon_ns = [i for i in range(len(glob(daemon_dir.format("*"))) + 1) if not daemon_dir.format(i).is_file()]

    if len(daemon_ns):
        daemon_n = daemon_ns[0]  # first free daemon slot
    else:
        if max_daemons != -1:
            if verbose:
                daemon_logger.info("No Daemon initiated, %s Daemons are already running:", max_daemons)
                disp_daemons()
                daemon_logger.info(
                    "Run initialize.py to clean old Daemon files or increase the --max_daemons flag."
                )
            return
        # Always initiate the next daemon
        all_daemon_files = range(len(glob(daemon_dir.format("*"))))
        daemons = [i for i in all_daemon_files if daemon_dir.format(i).is_file()]
        daemon_n = daemons[-1] + 1

    # Initiate the DAEMON lock
    daemon_name = daemon_dir.format(daemon_n)
    daemon_tmp = LockFile(daemon_name)
    atexit.register(daemon_tmp.rm)

    tried: list[str] = []
    while True:
        uris = get_tasks()
        uris = [u for u in uris if u not in tried]  # max tries per process lifetime

        if len(uris) > 0:
            task = uris[0]
            tried.append(task)

            task_tmp = LockFile(uri2tmp(daemon_n, task))
            atexit.register(task_tmp.rm)

            logger_path = log_dir.format(task, "txt")
            task_logger = configure_logger(
                name=f"web2mp3.download.{daemon_n}",
                log_file=logger_path,
                console=bool(verbose),
            )

            download_track(task, logger=task_logger)
            task_tmp.rm()

            if sleep_seconds > 0:
                task_logger.info("Sleeping %d seconds to avoid YouTube rate limiting", sleep_seconds)
                time.sleep(sleep_seconds)
        else:
            daemon_logger.info("daemon_job finished: No unprocessed URIs found.")
            break

        if verbose and not verbose_continuous:
            break


if __name__ == "__main__":
    daemon_job()
