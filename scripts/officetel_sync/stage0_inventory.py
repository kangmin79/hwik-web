"""Stage 0. 시군구 인벤토리 구축.

소스 우선순위:
  1. 국토부 법정동 코드 CSV (REPO_ROOT/국토교통부_법정동코드_*.csv) — 모든 시군구
  2. apartments DB 의 sgg_cd 컬럼 — 실데이터 기반 (앞 5자리)

산출: COLLECT_ROOT/stage0_inventory/sigungu.json (5자리 코드 list)
"""
from __future__ import annotations

import csv
import sys

from .config import REPO_ROOT, stage_dir
from .local_store import write_json


def _from_csv() -> list[str]:
    """REPO_ROOT 의 국토부 법정동 CSV 에서 5자리 시군구 코드 추출."""
    csvs = list(REPO_ROOT.glob("국토교통부_법정동코드*.csv"))
    if not csvs:
        return []
    csv_path = csvs[0]
    print(f"[stage0] 법정동 CSV 사용: {csv_path.name}")

    codes = set()
    # 인코딩 시도 순서
    for enc in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            with csv_path.open("r", encoding=enc) as f:
                reader = csv.reader(f)
                next(reader, None)                     # header skip
                for row in reader:
                    if len(row) >= 1:
                        code = row[0].strip()
                        # 10자리 법정동 코드 → 앞 5자리 = 시군구
                        if len(code) >= 5 and code.isdigit():
                            sgg5 = code[:5]
                            # 시군구 단위(끝 5자리 != 0): 광역시 구·시·군 단위
                            # '11000' 같은 시도 자체 코드는 제외
                            if not sgg5.endswith("000"):
                                codes.add(sgg5)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"[stage0] CSV 파싱 오류 ({enc}): {e}", file=sys.stderr)
            continue
    return sorted(codes)


def _from_db() -> list[str]:
    """apartments DB 에서 sgg_cd 추출 (보조)."""
    try:
        from .db.supabase_client import paginated_select
        rows = paginated_select("apartments", select="sgg_cd")
        codes = {r.get("sgg_cd")[:5] for r in rows if r.get("sgg_cd")}
        return sorted(c for c in codes if c and len(c) == 5)
    except Exception as e:
        print(f"[stage0] DB 보조 추출 실패: {e}", file=sys.stderr)
        return []


def build_inventory() -> list[str]:
    csv_codes = set(_from_csv())
    db_codes = set(_from_db()) if csv_codes else set()  # CSV 우선, DB는 보조 검증
    if csv_codes:
        merged = sorted(csv_codes)
        only_db = db_codes - csv_codes
        if only_db:
            print(f"[stage0] DB 에만 있고 CSV 에 없는 코드 {len(only_db)}개 추가")
            merged = sorted(csv_codes | db_codes)
        return merged
    if db_codes:
        return sorted(db_codes)
    raise RuntimeError("시군구 코드 소스 없음 (CSV 미존재 + DB 접근 실패)")


def main() -> int:
    out = build_inventory()
    print(f"[stage0] 시군구 {len(out)}개 추출")
    out_path = stage_dir("stage0_inventory") / "sigungu.json"
    write_json(out_path, out)
    print(f"[stage0] 저장: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
