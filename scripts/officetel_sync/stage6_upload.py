"""Stage 6. Supabase 업로드.

순서 (FK + apartment baseline 보호):
  1. apartments baseline 측정
  2. id_map 스냅샷 (TRUNCATE 전 마지막 보험)
  3. officetel_pyeongs FK drop  ← 마이그레이션 미적용 시 수동 안내
  4. TRUNCATE officetels, officetel_trades, officetel_trade_raw
  5. INSERT officetels  (배치 500, 체크포인트)
  6. INSERT officetel_trades
  7. officetel_pyeongs FK restore
  8. apartments baseline 재검증

오피스텔 외 테이블은 절대 건드리지 않음 (assert_not_apartment_table).
"""
from __future__ import annotations

import argparse
import sys

from .checkpoint import Checkpoint
from .config import COLLECT_ROOT, INSERT_BATCH_SIZE, MIN_TRADE_COUNT_5Y, stage_dir
from .db.officetel_id import snapshot_existing_ids
from .db.supabase_client import count_rows, insert_rows
from .local_store import read_jsonl, write_json
from .safety_guards import (
    SafetyViolation,
    assert_baseline_unchanged,
    assert_umd_is_dong,
    snapshot_apartment_baseline,
)


def _confirm_marker_exists() -> None:
    marker = COLLECT_ROOT / "_truncate_confirmed.marker"
    if not marker.exists():
        raise SafetyViolation(
            f"TRUNCATE 마커 파일 없음: {marker}\n"
            f"순서:\n"
            f" 1. python -m scripts.officetel_sync.stage6_upload --snapshot-only\n"
            f" 2. supabase/migrations/20260424100000_officetel_pyeongs_fk_drop.sql 수동 실행\n"
            f" 3. supabase/migrations/20260424140000_officetels_truncate_safe.sql 수동 실행\n"
            f" 4. touch {marker}\n"
            f" 5. 본 명령 재실행"
        )


def _upload_batched(table: str, rows: list[dict], on_conflict: str,
                    cp: Checkpoint, stage_key: str) -> int:
    total = len(rows)
    inserted = 0
    for i in range(0, total, INSERT_BATCH_SIZE):
        batch_key = f"{stage_key}:{i}"
        if cp.is_done(stage_key, batch_key):
            inserted += min(INSERT_BATCH_SIZE, total - i)
            continue
        chunk = rows[i:i + INSERT_BATCH_SIZE]
        try:
            insert_rows(table, chunk, on_conflict=on_conflict, upsert=True)
            cp.mark_done(stage_key, batch_key, len(chunk))
            inserted += len(chunk)
            if (i // INSERT_BATCH_SIZE) % 10 == 0:
                print(f"  [{table}] {inserted}/{total} ({inserted/total*100:.1f}%)", flush=True)
        except Exception as e:
            cp.mark_error(stage_key, batch_key, str(e))
            raise
    print(f"  [{table}] DONE {inserted}/{total}")
    return inserted


def run(args) -> int:
    base = stage_dir("stage4")
    officetels = list(read_jsonl(base / "officetels.jsonl"))
    trades = list(read_jsonl(base / "officetel_trades.jsonl"))
    print(f"[stage6] officetels={len(officetels):,}, trades={len(trades):,}")
    if not officetels:
        print("[stage6] officetels 비어있음. Stage 4 결과 없음.", file=sys.stderr)
        return 1

    # 적재 직전 게이트 재검증 — 이름 없는 단지 / 거래 부족 단지는 절대 업로드 금지
    bad_name = [d for d in officetels if not (d.get("bld_nm") or "").strip()]
    bad_trade = [d for d in officetels if (d.get("trade_count") or 0) < MIN_TRADE_COUNT_5Y]
    if bad_name or bad_trade:
        raise SafetyViolation(
            f"[stage6] 게이트 위반 — 업로드 중단:\n"
            f"  bld_nm 없음: {len(bad_name):,}건 (예: {[d.get('id') for d in bad_name[:3]]})\n"
            f"  trade_count<{MIN_TRADE_COUNT_5Y}: {len(bad_trade):,}건\n"
            f"  → stage4_normalize 재실행으로 정리 필요"
        )

    # umd 자리에 자치구(*구)가 들어가는 사고 방지 (2026-04-25 사고 재발 방지)
    assert_umd_is_dong(officetels)

    # trades 측 보호: officetels 화이트리스트에 없는 officetel_id는 제거
    valid_ids = {d["id"] for d in officetels}
    before = len(trades)
    trades = [t for t in trades if t.get("officetel_id") in valid_ids]
    if before != len(trades):
        print(f"[stage6] trades 정리: {before-len(trades):,}건 제외 (whitelist 외)")

    # Stage 6.0: snapshot only (TRUNCATE 전 마지막 보험)
    if args.snapshot_only:
        baseline = snapshot_apartment_baseline()
        write_json(stage_dir("stage6") / "apartment_baseline_before.json", baseline)
        m = snapshot_existing_ids()
        print(f"[stage6] id_map snapshot: {len(m)}, baseline: {baseline}")
        return 0

    # 본 업로드
    _confirm_marker_exists()

    baseline = snapshot_apartment_baseline()
    print(f"[stage6] apartments baseline: {baseline}")

    cp = Checkpoint(COLLECT_ROOT / "checkpoint.db")

    # 1. officetels INSERT
    print("[stage6] officetels 적재 시작...")
    _upload_batched("officetels", officetels, on_conflict="id",
                    cp=cp, stage_key="stage6_officetels")

    # 중간 baseline 검증
    assert_baseline_unchanged(baseline)

    # 2. officetel_trades INSERT
    print("[stage6] officetel_trades 적재 시작...")
    _upload_batched("officetel_trades", trades,
                    on_conflict="officetel_id,deal_type,deal_year,deal_month,deal_day,excl_use_ar,floor,price,monthly_rent",
                    cp=cp, stage_key="stage6_trades")

    # 최종 baseline 검증
    assert_baseline_unchanged(baseline)

    # 공급면적 row 수 보존 확인
    pyeongs_after = count_rows("officetel_pyeongs")
    print(f"[stage6] officetel_pyeongs row: {pyeongs_after}")

    print("[stage6] 완료. FK 복원 마이그레이션 수동 실행:")
    print("  supabase/migrations/20260424160000_officetel_pyeongs_fk_restore.sql")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot-only", action="store_true",
                   help="id 매핑·baseline 스냅샷만 (TRUNCATE 전 사전)")
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
