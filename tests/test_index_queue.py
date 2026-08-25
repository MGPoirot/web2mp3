import sys
import tempfile
import types
import pathlib
import unittest
import contextlib
from io import StringIO
from pathlib import Path as StdPath

sys.path.insert(0, str(StdPath(__file__).resolve().parents[1] / "src"))


def _stub_index_deps(index_dir: str):
    class Path(type(pathlib.Path())):
        def format(self, *args, **kwargs):
            return Path(str(self).format(*args, **kwargs))

    init = types.ModuleType("initialize")
    init.Path = Path
    init.index_path = Path(index_dir)
    utils = types.ModuleType("utils")

    def input_is(expect, value, ignore_case=True):
        if value is None:
            return False
        a, b = str(expect), str(value)
        if ignore_case:
            a, b = a.lower(), b.lower()
        return b.startswith(a[0]) if a else False

    utils.input_is = input_is
    saved = {name: sys.modules.get(name) for name in ("initialize", "utils", "index")}
    sys.modules["initialize"] = init
    sys.modules["utils"] = utils
    sys.modules.pop("index", None)
    import index

    index.reset_conn_for_tests()
    index.DB_PATH = Path(index_dir) / "index.sqlite3"
    return index, saved, Path


class IndexQueueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.index, self._saved, self.Path = _stub_index_deps(self._tmp.name)

    def tearDown(self):
        self.index.reset_conn_for_tests()
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        self._tmp.cleanup()

    def _pending(self, uri):
        self.index.write(
            uri,
            tags={"title": uri, "artist": "x", "album": "y"},
            settings={"quality": 192},
        )

    def test_never_tried_sorts_before_attempted(self):
        self._pending("youtube.oldfail")
        self.index.record_attempt("youtube.oldfail")
        self._pending("youtube.fresh")
        self.assertEqual(self.index.to_do(), ["youtube.fresh", "youtube.oldfail"])

    def test_blacklist_marks_done_and_skips_todo(self):
        self._pending("youtube.dead")
        for _ in range(3):
            self.index.record_permanent_failure("youtube.dead")
        self.index.blacklist_uri("youtube.dead", "video unavailable", "gone", fail_count=3)
        self.assertEqual(self.index.to_do(), [])
        self.assertTrue(self.index.has_uri("youtube.dead"))
        self.assertTrue(self.index.is_blacklisted("youtube.dead"))
        self.assertEqual(self.index.blacklist_count(), 1)
        self.assertIsNone(self.index.read("youtube.dead"))

    def test_summary_includes_blacklist_count(self):
        self._pending("youtube.a")
        self.index.blacklist_uri("youtube.a", "private video", "nope", fail_count=3)
        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            n = self.index.summary()
        self.assertEqual(n, 0)
        self.assertIn("blacklisted", buf.getvalue())
