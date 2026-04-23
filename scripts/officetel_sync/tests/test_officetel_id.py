"""officetel_id 해결 로직 단위 테스트 (DB 무의존)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.db.officetel_id import generate_new_id, resolve_id


class TestResolveId(unittest.TestCase):
    def test_existing_mapping_reused(self):
        id_map = {"1050134682": "o0040313"}
        got, is_new = resolve_id("1050134682", id_map)
        self.assertEqual(got, "o0040313")
        self.assertFalse(is_new)

    def test_new_mgm_generates_and_caches(self):
        id_map: dict[str, str] = {}
        got, is_new = resolve_id("NEW_PK_12345", id_map)
        self.assertTrue(is_new)
        self.assertTrue(got.startswith("o"))
        self.assertEqual(len(got), 8)
        # 두 번째 호출 시 동일 id 반환
        got2, is_new2 = resolve_id("NEW_PK_12345", id_map)
        self.assertEqual(got, got2)
        self.assertFalse(is_new2)

    def test_empty_pk_raises(self):
        with self.assertRaises(ValueError):
            generate_new_id("")


class TestIdCollisionAvoidance(unittest.TestCase):
    def test_conflict_with_existing_ids_uses_salt(self):
        # NEW_PK_12345 의 salt=0 결과값 사전 계산
        expected_base = generate_new_id("NEW_PK_12345")
        # 이미 그 id 가 사용 중이라고 가정 → salt 증가로 다른 값 반환
        alt = generate_new_id("NEW_PK_12345", existing_ids={expected_base})
        self.assertNotEqual(alt, expected_base)
        self.assertTrue(alt.startswith("o"))

    def test_resolve_id_avoids_map_values_collision(self):
        # id_map 에 있는 값과 겹치지 않도록 재생성되어야 함
        id_map = {"OTHER_PK": "o1234567"}
        # PK X 의 기본 해시값이 'o1234567' 라고 가정하고 강제 재현은 어려우므로
        # resolve_id 호출 후 id_map.values() 안에 중복 없는지 확인
        new_id, _ = resolve_id("X_PK_FIXTURE", id_map)
        self.assertNotEqual(new_id, "o1234567")
        self.assertEqual(len(set(id_map.values())), len(id_map))


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
