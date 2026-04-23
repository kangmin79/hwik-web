"""Stage 1b 주소 인벤토리 추출 단위 테스트."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.stage1b_extract_addresses import _normalize_name, _parse_bun_ji


class TestParseBunJi(unittest.TestCase):
    def test_with_sub_no(self):
        self.assertEqual(_parse_bun_ji("719-24"), ("0719", "0024"))

    def test_main_only(self):
        self.assertEqual(_parse_bun_ji("719"), ("0719", "0000"))

    def test_invalid_returns_none(self):
        self.assertIsNone(_parse_bun_ji(""))
        self.assertIsNone(_parse_bun_ji("산 12"))
        self.assertIsNone(_parse_bun_ji("12-3-4"))


class TestNormalizeName(unittest.TestCase):
    def test_strip_spaces(self):
        self.assertEqual(_normalize_name("역삼 센트럴 푸르지오 시티"), "역삼센트럴푸르지오시티")
        self.assertEqual(_normalize_name(" k 타워 "), "k타워")

    def test_empty(self):
        self.assertEqual(_normalize_name(""), "")
        self.assertEqual(_normalize_name(None), "")


if __name__ == "__main__":
    unittest.main()
