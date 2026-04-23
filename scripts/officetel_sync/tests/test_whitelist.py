"""화이트리스트 검증 단위 테스트."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.safety_guards import (
    SafetyViolation,
    assert_whitelist_present,
)


class TestWhitelist(unittest.TestCase):
    WL = ["역삼센트럴푸르지오시티", "강남 지웰홈스"]

    def test_all_present(self):
        existing = ["역삼센트럴푸르지오시티", "강남지웰홈스", "다른단지"]
        assert_whitelist_present(self.WL, existing)  # 공백 제거 매칭

    def test_missing_raises(self):
        existing = ["역삼센트럴푸르지오시티"]
        with self.assertRaises(SafetyViolation):
            assert_whitelist_present(self.WL, existing)

    def test_space_normalization(self):
        """화이트리스트와 DB 이름 간 공백 차이 허용."""
        assert_whitelist_present(
            ["역삼 센트럴 푸르지오 시티"],
            ["역삼센트럴푸르지오시티"],
        )


if __name__ == "__main__":
    unittest.main()
