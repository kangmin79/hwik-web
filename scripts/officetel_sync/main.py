"""오피스텔 재수집 오케스트레이션 (PC 로컬 실행).

수동 실행 가이드:

1. 환경변수 설정 (.env 또는 셸):
     GOV_SERVICE_KEY (운영키, 100만/일)
     KAKAO_REST_API_KEY
     SUPABASE_SERVICE_ROLE_KEY

2. python -m scripts.officetel_sync.main --stage all
   또는 단계별:
     python -m scripts.officetel_sync.main --stage 0   (시군구 인벤토리)
     python -m scripts.officetel_sync.main --stage 1   (실거래 5년)
     python -m scripts.officetel_sync.main --stage 1b  (주소 인벤토리)
     python -m scripts.officetel_sync.main --stage 2   (건축물대장)
     python -m scripts.officetel_sync.main --stage 3   (카카오 좌표)
     python -m scripts.officetel_sync.main --stage 4   (정제·매칭·게이트)
     python -m scripts.officetel_sync.main --stage 5   (검증)
     python -m scripts.officetel_sync.main --stage 6   (Supabase 업로드)

3. Stage 6 전 SQL 수동 실행:
     20260424100000_officetel_pyeongs_fk_drop.sql
     20260424140000_officetels_truncate_safe.sql
     touch _truncate_confirmed.marker
"""
from __future__ import annotations

import argparse
import sys
import time

from .config import COLLECT_ROOT


def _run_stage(name: str) -> int:
    """각 stage 의 main() 은 자체 argparse 가짐 → 호출 전 sys.argv 임시 비우기."""
    print(f"\n{'=' * 60}\n>>> {name}\n{'=' * 60}", flush=True)
    started = time.time()
    saved_argv = sys.argv
    sys.argv = [sys.argv[0]]
    try:
        if name == "0":
            from . import stage0_inventory as m
        elif name == "1":
            from . import stage1_trades as m
        elif name == "1b":
            from . import stage1b_extract_addresses as m
        elif name == "2":
            from . import stage2_bldg as m
        elif name == "3":
            from . import stage3_geocode as m
        elif name == "4":
            from . import stage4_normalize as m
        elif name == "5":
            from . import stage5_verify as m
        elif name == "6":
            from . import stage6_upload as m
        else:
            print(f"unknown stage: {name}", file=sys.stderr)
            return 1
        rc = m.main()
    finally:
        sys.argv = saved_argv
    elapsed = time.time() - started
    print(f"<<< stage {name} {'OK' if rc == 0 else 'FAIL'} in {elapsed:.1f}s", flush=True)
    return rc


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True,
                   choices=["all", "0", "1", "1b", "2", "3", "4", "5", "6"])
    args = p.parse_args()

    print(f"== COLLECT_ROOT = {COLLECT_ROOT} ==")

    if args.stage == "all":
        # Stage 6 (업로드)는 사용자 확인 후 수동 실행 — all 에 포함하지 않음
        for s in ("0", "1", "1b", "2", "3", "4", "5"):
            rc = _run_stage(s)
            if rc != 0:
                return rc
        print("\n" + "=" * 60)
        print("[main] Stage 0~5 완료. ⏸ Supabase 업로드 전 사용자 확인 필요.")
        print("=" * 60)
        print("\n검토할 로컬 산출물:")
        print(f"  {COLLECT_ROOT}/stage4/officetels.jsonl       (단지 마스터)")
        print(f"  {COLLECT_ROOT}/stage4/officetel_trades.jsonl (거래)")
        print(f"  {COLLECT_ROOT}/stage4/gate_report.json       (매칭률·회수율)")
        print(f"  {COLLECT_ROOT}/stage5/verify_report.json     (G1~G6)")
        print(f"  {COLLECT_ROOT}/stage4/unmatched_trades.jsonl (매칭 실패 분석)")
        print("\n사용자 확인 후 Stage 6 수동 실행:")
        print("  1) python -m scripts.officetel_sync.main --stage 6 --snapshot-only")
        print("  2) supabase SQL Editor: 20260424100000_officetel_pyeongs_fk_drop.sql")
        print("  3) supabase SQL Editor: 20260424140000_officetels_truncate_safe.sql")
        print(f"  4) touch {COLLECT_ROOT}/_truncate_confirmed.marker")
        print("  5) python -m scripts.officetel_sync.main --stage 6")
        return 0

    return _run_stage(args.stage)


if __name__ == "__main__":
    sys.exit(main())
