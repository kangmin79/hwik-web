"""안전 가드 단위 테스트. 2026-04-23 사고 재발 방지 검증."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.safety_guards import (
    SafetyViolation,
    assert_content_range_complete,
    assert_limit,
    assert_not_apartment_table,
)


class TestLimitGuard(unittest.TestCase):
    def test_accepts_1000(self):
        assert_limit(1000)  # 기준 상한, 통과

    def test_rejects_10000(self):
        with self.assertRaises(SafetyViolation):
            assert_limit(10000)  # 2026-04-23 사고 재현 차단

    def test_rejects_1001(self):
        with self.assertRaises(SafetyViolation):
            assert_limit(1001)


class TestApartmentTableGuard(unittest.TestCase):
    def test_allows_officetel_tables(self):
        assert_not_apartment_table("officetel_trades?select=*")
        assert_not_apartment_table("TRUNCATE officetels")
        assert_not_apartment_table("officetel_pyeongs?officetel_id=eq.o0336018")

    def test_blocks_apartments(self):
        with self.assertRaises(SafetyViolation):
            assert_not_apartment_table("DELETE FROM apartments")

    def test_blocks_trades(self):
        with self.assertRaises(SafetyViolation):
            assert_not_apartment_table("trades?sgg_cd=eq.11680")

    def test_blocks_case_insensitive(self):
        with self.assertRaises(SafetyViolation):
            assert_not_apartment_table("APARTMENTS?select=id")


class TestContentRangeValidation(unittest.TestCase):
    def test_consistent_range(self):
        assert_content_range_complete("0-999/12345", 1000)  # 통과

    def test_inconsistent_range_raises(self):
        with self.assertRaises(SafetyViolation):
            assert_content_range_complete("0-999/12345", 500)  # 받은 row < 범위

    def test_empty_range_ok(self):
        assert_content_range_complete("*/0", 0)  # 빈 결과 허용


if __name__ == "__main__":
    unittest.main()
