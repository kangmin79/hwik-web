"""local_store JSONL 입출력 단위 테스트."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.local_store import (
    append_jsonl,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)


class TestJsonl(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "data.jsonl"

    def test_write_then_read(self):
        rows = [{"a": 1}, {"a": 2, "b": "한글"}]
        write_jsonl(self.tmp, rows)
        loaded = list(read_jsonl(self.tmp))
        self.assertEqual(loaded, rows)

    def test_append_concurrent_safe(self):
        # 8 thread 동시 append → 모두 보존되는지
        def worker(i):
            append_jsonl(self.tmp, [{"i": i}])
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        loaded = list(read_jsonl(self.tmp))
        self.assertEqual(len(loaded), 20)


class TestJson(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "data.json"

    def test_write_then_read(self):
        write_json(self.tmp, {"k": [1, 2, "삼"]})
        self.assertEqual(read_json(self.tmp), {"k": [1, 2, "삼"]})

    def test_default_when_missing(self):
        self.assertEqual(read_json(self.tmp, default={}), {})


if __name__ == "__main__":
    unittest.main()
