"""officetel_id 관리.

중요: 기존 DB의 id 공식 역공학 불가 (sha256/md5/crc32 등 전부 mismatch).
→ TRUNCATE 전에 기존 (mgm_bldrgst_pk → id) 매핑을 캐싱한 뒤 재사용.
→ 새 단지만 새 공식으로 id 생성.

이 전략으로 officetel_pyeongs(7,874 unique id)의 FK가 모두 유지됨.
"""
from __future__ import annotations

import hashlib
import json
import threading

from ..config import BACKUP_DIR
from .supabase_client import paginated_select

_ID_MAP_FILE = BACKUP_DIR / "existing_officetel_id_map.json"
_ID_GEN_LOCK = threading.Lock()                      # resolve_id 병렬 안전성


def snapshot_existing_ids() -> dict[str, str]:
    """현재 DB의 (mgm_bldrgst_pk → id) 매핑을 파일로 덤프.

    **TRUNCATE 실행 전에 반드시 호출**. 이후 복원/재생성 시 동일 id 재사용.
    반환: 매핑 dict
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    rows = paginated_select("officetels", select="id,mgm_bldrgst_pk")
    mapping = {
        r["mgm_bldrgst_pk"]: r["id"]
        for r in rows
        if r.get("mgm_bldrgst_pk") and r.get("id")
    }
    _ID_MAP_FILE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping


def load_id_map() -> dict[str, str]:
    """스냅샷 파일에서 로드. 없으면 빈 dict (최초 호출 시는 먼저 snapshot 필요)."""
    if not _ID_MAP_FILE.exists():
        return {}
    return json.loads(_ID_MAP_FILE.read_text(encoding="utf-8"))


def _hash_digits(mgm_bldrgst_pk: str, salt: int = 0) -> str:
    """sha256(pk + salt) hex 중 숫자만 뽑아 7자리."""
    key = f"{mgm_bldrgst_pk}:{salt}" if salt else mgm_bldrgst_pk
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    digits = "".join(c for c in h if c.isdigit())
    if len(digits) < 7:
        digits = str(int(h, 16))
    return digits[:7]


def generate_new_id(mgm_bldrgst_pk: str, *, existing_ids: set[str] | None = None) -> str:
    """기존 매핑에 없는 신규 단지용 id 생성.

    10^7 공간 + 생일역설로 대규모 수집 시 충돌 가능 → existing_ids 와 비교 후
    충돌 시 salt 증가시켜 재생성 (최대 100 시도).
    """
    if not mgm_bldrgst_pk:
        raise ValueError("mgm_bldrgst_pk 없음 → id 생성 불가")
    existing_ids = existing_ids if existing_ids is not None else set()
    for salt in range(100):
        candidate = "o" + _hash_digits(mgm_bldrgst_pk, salt)
        if candidate not in existing_ids:
            return candidate
    raise RuntimeError(
        f"id 충돌 100회 연속 — id 공간 포화 의심. mgm_bldrgst_pk={mgm_bldrgst_pk}"
    )


def resolve_id(mgm_bldrgst_pk: str, id_map: dict[str, str]) -> tuple[str, bool]:
    """매핑 있으면 기존 id, 없으면 충돌 검사 후 신규 생성.

    스레드 안전. 반환: (id, is_new)
    """
    with _ID_GEN_LOCK:
        existing = id_map.get(mgm_bldrgst_pk)
        if existing:
            return existing, False
        used = set(id_map.values())
        new_id = generate_new_id(mgm_bldrgst_pk, existing_ids=used)
        id_map[mgm_bldrgst_pk] = new_id
        return new_id, True
