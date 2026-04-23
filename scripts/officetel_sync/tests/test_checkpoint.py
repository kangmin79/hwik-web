"""Checkpoint SQLite 단위 테스트."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.checkpoint import Checkpoint


class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cp = Checkpoint(Path(self.tmpdir) / "cp.db")

    def test_mark_done_then_is_done(self):
        self.assertFalse(self.cp.is_done("stage1", "11680_202401"))
        self.cp.mark_done("stage1", "11680_202401", row_count=42)
        self.assertTrue(self.cp.is_done("stage1", "11680_202401"))

    def test_mark_error_then_not_done(self):
        self.cp.mark_error("stage1", "11680_202401", "MolitError: 503")
        self.assertFalse(self.cp.is_done("stage1", "11680_202401"))

    def test_summary(self):
        for i in range(5):
            self.cp.mark_done("s", f"k{i}", row_count=10)
        self.cp.mark_error("s", "k_err", "boom")
        s = self.cp.stage_summary("s")
        self.assertEqual(s["done"], 5)
        self.assertEqual(s["error"], 1)
        self.assertEqual(s["rows"], 50)


if __name__ == "__main__":
    unittest.main()
