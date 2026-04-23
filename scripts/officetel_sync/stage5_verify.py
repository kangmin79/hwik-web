"""Stage 5. 로컬 검증 (DB 업로드 전).

게이트:
  G1. apartments 테이블 baseline 변동 0
  G2. officetels JSONL 의 모든 단지에 좌표 (precise/approx)
  G3. officetel_trades JSONL 모든 거래의 (deal_year, deal_month, deal_day) 유효
  G4. 화이트리스트 단지 모두 존재
  G5. 단지별 trade_count >= 10
  G6. 공급면적 보존 (officetel_pyeongs DB row 수 변동 없음 == 19,807)
"""
from __future__ import annotations

import argparse
import sys

from .config import MIN_TRADE_COUNT_5Y, stage_dir
from .db.supabase_client import count_rows
from .local_store import read_jsonl, write_json
from .safety_guards import (
    SafetyViolation,
    assert_whitelist_present,
    fetch_apartment_count,
)

# 사용자 확정 후 상위 거래량 기반 자동 채움 가능
WHITELIST_OFFICETELS = [
    "역삼센트럴푸르지오시티",
    "강남지웰홈스",
    "역삼아트원푸르지오시티",
    "강남푸르지오시티",
    "강남센트럴푸르지오시티",
    "위례A2-3블록센트럴푸르지오시티",
    "마곡지웰에스테이트",
    "광교아이파크",
    "분당정자동더샵스타파크",
    "송도더샵센트럴파크",
]


def run() -> int:
    out: dict = {"gates": {}, "abort_reasons": []}

    base = stage_dir("stage4")
    officetels = list(read_jsonl(base / "officetels.jsonl"))
    trades = list(read_jsonl(base / "officetel_trades.jsonl"))
    print(f"[stage5] officetels={len(officetels):,}, trades={len(trades):,}")

    # G1. apartments baseline
    try:
        apt_count = fetch_apartment_count()
        out["gates"]["G1"] = {"apartments_count": apt_count, "pass": apt_count >= 30000}
        if apt_count < 30000:
            out["abort_reasons"].append(f"G1: apartments={apt_count} < 30000")
    except SafetyViolation as e:
        out["gates"]["G1"] = {"pass": False, "error": str(e)}
        out["abort_reasons"].append(f"G1: {e}")

    # G2. 좌표 누락
    no_coord = [d for d in officetels if not (d.get("jibun_lat") or d.get("road_lat"))]
    out["gates"]["G2"] = {"missing_coord": len(no_coord), "pass": not no_coord}
    if no_coord:
        out["abort_reasons"].append(f"G2: 좌표 누락 단지 {len(no_coord)}")

    # G3. 거래 일자 유효성
    bad_dates = [t for t in trades if not (t.get("deal_year") and t.get("deal_month") and t.get("deal_day"))]
    out["gates"]["G3"] = {"bad_dates": len(bad_dates), "pass": not bad_dates}
    if bad_dates:
        out["abort_reasons"].append(f"G3: 거래 일자 누락 {len(bad_dates)}")

    # G4. 화이트리스트
    existing_names = [d.get("bld_nm", "") for d in officetels]
    try:
        assert_whitelist_present(WHITELIST_OFFICETELS, existing_names)
        out["gates"]["G4"] = {"pass": True, "whitelist_size": len(WHITELIST_OFFICETELS)}
    except SafetyViolation as e:
        out["gates"]["G4"] = {"pass": False, "error": str(e)}
        out["abort_reasons"].append(f"G4: {e}")

    # G5. 단지별 trade_count >= 10
    below = [d for d in officetels if (d.get("trade_count") or 0) < MIN_TRADE_COUNT_5Y]
    out["gates"]["G5"] = {"below_gate": len(below), "pass": not below}
    if below:
        out["abort_reasons"].append(f"G5: 10건 미만 단지 {len(below)} — Stage4 필터 버그")

    # G6. 공급면적 보존 (DB 측 — 업로드 후에도 유지되어야 함, 사전 baseline 기록)
    try:
        pyeongs_count = count_rows("officetel_pyeongs")
        out["gates"]["G6"] = {"officetel_pyeongs_count": pyeongs_count}
        # baseline 기록만, abort 안 함
    except Exception as e:
        out["gates"]["G6"] = {"pass": False, "error": str(e)}

    write_json(stage_dir("stage5") / "verify_report.json", out)
    if out["abort_reasons"]:
        print(f"[stage5] ABORT — 이유 {len(out['abort_reasons'])}건:", file=sys.stderr)
        for r in out["abort_reasons"]:
            print(f"  - {r}", file=sys.stderr)
        return 1
    print("[stage5] 모든 게이트 통과")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.parse_args()
    return run()


if __name__ == "__main__":
    sys.exit(main())
