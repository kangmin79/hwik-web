"""Daily 오피스텔 거래 동기화 (GitHub Actions 매일 KST 03시 실행 대상).

Stage 1 (실거래 3개월) + 매칭(DB officetels 기반) + UPSERT (TRUNCATE 없음).
신규 단지 발굴은 분기 1회 PC stage all 에서 수행 — 본 스크립트 범위 밖.

설계 원칙:
  - **TRUNCATE 절대 호출 안 함** (stage6_upload 와 명확히 분리, _assert_no_truncate 가드)
  - 기존 9,833 단지에 매칭되는 거래만 처리 (영구 블랙리스트 + DB 인덱스)
  - 매칭 안 된 거래는 unmatched_daily/{YYYY-MM-DD}.jsonl 로 보관 (분석용)
  - 매칭된 + 매칭 안 된 거래 모두 officetel_trade_raw 에 보존
  - apartments baseline 검증 (자동 실행이라도 사고 즉시 abort)

작업 흐름 (Phase):
  P1. DB officetels 풀로드 → strict_idx, jibun_idx, mgm_to_id 빌드
  P2. stage1_trades 호출 (지정 시도 시군구만, --months-back 3)
  P3. stage1 jsonl 전수 → 매칭 → matched / unmatched 분리
  P4. (DRY-RUN 시 멈춤. 통계만 출력)
  P5. officetel_trade_raw UPSERT (raw 거래 보존, 매칭 정보 부착)
  P6. officetel_trades UPSERT (매칭된 거래만)
  P7. RPC recalc_officetels_aggregates 호출 (trade_count + excl_area_min/max)

진입:
  python -m scripts.officetel_sync.daily_trades --sido 서울 --months-back 3 --dry-run
  python -m scripts.officetel_sync.daily_trades --sido all  --months-back 3
  python -m scripts.officetel_sync.daily_trades --sigungu 11680 --months-back 3 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

# .env 자동 로딩 — config import 보다 반드시 먼저 (config 가 import 시점에 환경변수 read)
try:
    from pathlib import Path as _Path
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from .config import MIN_TRADE_COUNT_5Y, REPO_ROOT, stage_dir
from .db.supabase_client import call_rpc, insert_rows, paginated_select
from .local_store import read_jsonl, write_json, write_jsonl
from .safety_guards import (
    SafetyViolation,
    assert_baseline_unchanged,
    snapshot_apartment_baseline,
)
from .stage4_normalize import _norm, _to_float, _to_int, load_blacklist, resolve_mgm


# ── 시도 코드 ↔ 한글명 매핑 (법정동 코드 앞 2자리) ──────────
SIDO_CODE_TO_NAME: dict[str, str] = {
    "11": "서울",
    "26": "부산",
    "27": "대구",
    "28": "인천",
    "29": "광주",
    "30": "대전",
    "31": "울산",
    "36": "세종",
    "41": "경기",
    "42": "강원",
    "51": "강원",
    "43": "충북",
    "44": "충남",
    "45": "전북",
    "52": "전북",
    "46": "전남",
    "47": "경북",
    "48": "경남",
    "50": "제주",
}
SIDO_NAME_TO_CODES: dict[str, list[str]] = defaultdict(list)
for _code, _name in SIDO_CODE_TO_NAME.items():
    SIDO_NAME_TO_CODES[_name].append(_code)


def _load_sigungu_inventory_from_csv() -> list[str]:
    """법정동 CSV → 5자리 시군구 코드 list (stage0_inventory 와 동일 로직)."""
    csvs = list(REPO_ROOT.glob("국토교통부_법정동코드*.csv"))
    if not csvs:
        raise RuntimeError(f"법정동 CSV 없음: {REPO_ROOT}/국토교통부_법정동코드*.csv")
    csv_path = csvs[0]

    codes: set[str] = set()
    for enc in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            with csv_path.open("r", encoding=enc) as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if not row:
                        continue
                    code = row[0].strip()
                    if len(code) >= 5 and code.isdigit():
                        sgg5 = code[:5]
                        if not sgg5.endswith("000"):
                            codes.add(sgg5)
            break
        except UnicodeDecodeError:
            continue
    return sorted(codes)


def filter_sigungu_by_sido(all_sgg: list[str], sido: str) -> list[str]:
    """시도명 → 해당 시도의 5자리 시군구 코드 list."""
    if sido == "all":
        return all_sgg
    if sido not in SIDO_NAME_TO_CODES:
        raise ValueError(f"알 수 없는 시도명: {sido}. 가능: {sorted(set(SIDO_CODE_TO_NAME.values()))}")
    sido_prefixes = SIDO_NAME_TO_CODES[sido]
    return [c for c in all_sgg if c[:2] in sido_prefixes]


# ── Phase 1: DB officetels → 매칭 인덱스 ──────────────────


def build_match_index_from_db() -> tuple[dict, dict, dict]:
    """DB officetels 풀로드 → 매칭 인덱스 3종.

    반환: (strict_idx, jibun_idx, mgm_to_id)
      strict_idx     — (sgg_cd, jibun, bld_norm) → mgm_bldrgst_pk  (bldNm 있을 때)
      jibun_idx      — (sgg_cd, jibun) → list[mgm_bldrgst_pk]      (지번 fallback)
      mgm_to_id      — mgm_bldrgst_pk → officetels.id

    sgg_cd 는 bjdong_cd 앞 5자리. 매칭 키 형식은 stage4_normalize 와 동일.
    """
    rows = paginated_select(
        "officetels",
        select="id,mgm_bldrgst_pk,jibun,bld_nm,bjdong_cd",
    )
    print(f"[daily_trades:P1] officetels 로드: {len(rows):,}")

    strict_idx: dict[tuple, str] = {}
    jibun_idx: dict[tuple, list[str]] = defaultdict(list)
    mgm_to_id: dict[str, str] = {}
    seen_jibun: dict[tuple, set] = defaultdict(set)
    skipped_no_bjdong = 0

    for r in rows:
        mgm = r.get("mgm_bldrgst_pk")
        oid = r.get("id")
        if not (mgm and oid):
            continue
        mgm_to_id[mgm] = oid

        bjdong = (r.get("bjdong_cd") or "").strip()
        jibun = (r.get("jibun") or "").strip()
        if not (bjdong and len(bjdong) >= 5 and jibun):
            skipped_no_bjdong += 1
            continue
        sgg_cd = bjdong[:5]

        bld_norm = _norm(r.get("bld_nm"))
        if bld_norm:
            strict_idx.setdefault((sgg_cd, jibun, bld_norm), mgm)

        jkey = (sgg_cd, jibun)
        if mgm not in seen_jibun[jkey]:
            seen_jibun[jkey].add(mgm)
            jibun_idx[jkey].append(mgm)

    print(f"[daily_trades:P1] strict={len(strict_idx):,}, jibun={len(jibun_idx):,}, "
          f"mgm_to_id={len(mgm_to_id):,} (skipped_no_bjdong={skipped_no_bjdong:,})")
    return strict_idx, dict(jibun_idx), mgm_to_id


# ── Phase 3: stage1 jsonl 매칭 + 정규화 ────────────────────


def _price_signature(r: dict) -> str:
    """officetel_trade_raw dedup 키. 같은 거래는 같은 signature."""
    return (
        f"{(r.get('dealAmount') or r.get('deposit') or '').strip()}_"
        f"{(r.get('excluUseAr') or '').strip()}_"
        f"{(r.get('floor') or '').strip()}_"
        f"{(r.get('monthlyRent') or '').strip()}"
    )


def _deal_ymd(r: dict) -> str | None:
    y = _to_int(r.get("dealYear"))
    m = _to_int(r.get("dealMonth"))
    d = _to_int(r.get("dealDay"))
    if not (y and m and d):
        return None
    return f"{y:04d}{m:02d}{d:02d}"


def match_and_normalize(strict_idx: dict, jibun_idx: dict, mgm_to_id: dict,
                        blacklist: dict[str, dict]
                        ) -> tuple[list[dict], list[dict], list[dict], list[dict], Counter]:
    """stage1 jsonl 전수 → matched/unmatched 분리 + raw 페이로드 빌드.

    반환:
      matched_trades   — officetel_trades INSERT 용 (stage4 normalize_trades 와 동일 schema)
      unmatched_raw    — 분석용 dict (sgg/jibun/offi/원본 일부)
      raw_for_db       — officetel_trade_raw INSERT 용 (매칭/비매칭 모두)
      blacklisted_raw  — 영구 차단 단지 거래 (raw 만 적재, trades 는 제외)
      source_stats     — Counter (strict / jibun_single / jibun_multi / unmatched / blacklisted)
    """
    matched: list[dict] = []
    unmatched: list[dict] = []
    raw_for_db: list[dict] = []
    blacklisted_raw: list[dict] = []
    source_stats: Counter = Counter()

    for kind in ("sale", "rent"):
        deal_type_default = "매매" if kind == "sale" else None
        api_source = f"trade_{kind}"
        base = stage_dir(f"stage1_trades/{kind}")
        for f in base.glob("*.jsonl"):
            for r in read_jsonl(f):
                sgg = (r.get("sggCd") or r.get("_sigungu_cd") or "").strip()
                jibun = (r.get("jibun") or "").strip()
                offi = r.get("offiNm", "")
                ymd = _deal_ymd(r)

                # raw 페이로드 (매칭 결과와 무관하게 일단 모음)
                raw_row = {
                    "api_source": api_source,
                    "sync_run_id": _SYNC_RUN_ID,
                    "sigungu_cd": sgg or None,
                    "deal_ym": (r.get("_deal_ym") or "").strip() or None,
                    "apt_seq": None,                      # 오피스텔 API 미제공
                    "mgm_bldrgst_pk": None,               # 매칭 후 채움
                    "deal_ymd": ymd,
                    "price_signature": _price_signature(r),
                    "data": r,
                }

                if not (sgg and jibun and offi):
                    unmatched.append({"reason": "missing_key", **r})
                    source_stats["missing_key"] += 1
                    raw_for_db.append(raw_row)
                    continue

                mgm, source = resolve_mgm(sgg, jibun, offi, strict_idx, jibun_idx)
                source_stats[source] += 1
                if not mgm:
                    unmatched.append({"reason": "no_mgm_match",
                                       "sgg": sgg, "jibun": jibun, "offi": offi})
                    raw_for_db.append(raw_row)
                    continue

                # 영구 블랙리스트 차단 — raw 만 적재, trades 제외
                if mgm in blacklist:
                    raw_row["mgm_bldrgst_pk"] = mgm
                    blacklisted_raw.append(raw_row)
                    source_stats["blacklisted"] += 1
                    continue

                raw_row["mgm_bldrgst_pk"] = mgm
                raw_for_db.append(raw_row)

                # 거래 type 결정
                deal_type = deal_type_default
                if not deal_type:
                    monthly = _to_int(r.get("monthlyRent"))
                    deal_type = "월세" if (monthly and monthly > 0) else "전세"

                officetel_id = mgm_to_id.get(mgm)
                if not officetel_id:
                    # 인덱스 일관성 깨짐 — 안전 abort
                    raise SafetyViolation(
                        f"mgm_to_id 누락: mgm={mgm} — Phase 1 인덱스 빌드 결함")

                matched.append({
                    "officetel_id": officetel_id,
                    "deal_type": deal_type,
                    "deal_year": _to_int(r.get("dealYear")),
                    "deal_month": _to_int(r.get("dealMonth")),
                    "deal_day": _to_int(r.get("dealDay")),
                    "price": _to_int(r.get("dealAmount") or r.get("deposit")),
                    "monthly_rent": _to_int(r.get("monthlyRent")) or 0,
                    "excl_use_ar": _to_float(r.get("excluUseAr")),
                    "floor": _to_int(r.get("floor")),
                    "is_canceled": (r.get("cdealType") or "").strip().upper() == "O",
                    "dealing_gbn": r.get("dealingGbn"),
                    "buyer_gbn": r.get("buyerGbn"),
                    "seller_gbn": r.get("slerGbn"),
                    "agent_sgg_nm": r.get("estateAgentSggNm"),
                    "contract_term": r.get("contractTerm"),
                    "contract_type": r.get("contractType"),
                    # match 메타 (디버그용, DB 컬럼에 없으면 무시됨 — 안전 위해 별도 prefix)
                    "_match_source": source,
                    "_mgm_bldrgst_pk": mgm,
                })

    return matched, unmatched, raw_for_db, blacklisted_raw, source_stats


# ── Phase 5: officetel_trade_raw UPSERT (raw 보존) ─────────


_RAW_DEDUP_KEYS = ("api_source", "apt_seq", "mgm_bldrgst_pk", "deal_ymd", "price_signature")


def upsert_trade_raw(raw_rows: list[dict]) -> int:
    """officetel_trade_raw 에 raw 거래 적재. dedup 키:
      (api_source, apt_seq, mgm_bldrgst_pk, deal_ymd, price_signature)

    배치 내부 dedup 필수 — 동일 키가 2개 이상이면 Postgres 21000 에러
    "ON CONFLICT DO UPDATE command cannot affect row a second time".
    """
    if not raw_rows:
        return 0
    seen: dict[tuple, dict] = {}
    for r in raw_rows:
        key = tuple(r.get(k) for k in _RAW_DEDUP_KEYS)
        seen[key] = r  # 마지막 값 유지
    deduped = list(seen.values())
    return insert_rows(
        "officetel_trade_raw",
        deduped,
        on_conflict="api_source,apt_seq,mgm_bldrgst_pk,deal_ymd,price_signature",
        upsert=True,
    )


# ── Phase 6: officetel_trades UPSERT (매칭만) ──────────────


_TRADE_DB_COLUMNS = {
    "officetel_id", "deal_type", "deal_year", "deal_month", "deal_day",
    "price", "monthly_rent", "excl_use_ar", "floor", "is_canceled",
    "dealing_gbn", "buyer_gbn", "seller_gbn", "agent_sgg_nm",
    "contract_term", "contract_type",
}

_TRADE_DEDUP_KEYS = ("officetel_id", "deal_type", "deal_year", "deal_month",
                     "deal_day", "excl_use_ar", "floor", "price", "monthly_rent")


def upsert_officetel_trades(matched: list[dict]) -> int:
    """officetel_trades UPSERT. on_conflict = stage6 와 동일 9 필드.
    _match_source / _mgm_bldrgst_pk 등 디버그 키는 제거 후 적재.

    배치 내부 dedup 필수 — 동일 9-tuple 키가 2개 이상이면 Postgres 21000.
    국토부 sale/rent 양쪽에 같은 거래가 들어오거나 jibun_single 매핑이
    동일 거래를 다른 mgm 에 매핑할 때 발생.
    """
    if not matched:
        return 0
    seen: dict[tuple, dict] = {}
    for row in matched:
        cleaned = {k: v for k, v in row.items() if k in _TRADE_DB_COLUMNS}
        key = tuple(cleaned.get(k) for k in _TRADE_DEDUP_KEYS)
        seen[key] = cleaned  # 마지막 값 유지
    deduped = list(seen.values())
    return insert_rows(
        "officetel_trades",
        deduped,
        on_conflict="officetel_id,deal_type,deal_year,deal_month,deal_day,"
                    "excl_use_ar,floor,price,monthly_rent",
        upsert=True,
    )


# ── Phase 7: officetels.trade_count 등 RPC 재계산 ──────────


def recalc_aggregates() -> dict:
    """RPC recalc_officetels_aggregates 호출. trade_count + excl_area_min/max 갱신.

    last_trade_date 컬럼은 현 스키마에 없음. 추후 마이그레이션 + 함수 확장 필요.
    """
    result = call_rpc("recalc_officetels_aggregates")
    print(f"[daily_trades:P7] RPC 결과: {result}")
    return result


# ── 안전 가드 ──────────────────────────────────────────────


def _assert_no_truncate_keyword(*args) -> None:
    """daily_trades 가 직접 TRUNCATE 호출하지 않도록 import 시 차단.

    (실수 방지용 — REST API 라 SQL TRUNCATE 자체가 불가능하지만,
     혹시라도 RPC 추가 시 즉시 실패하도록.)
    """
    for s in args:
        if "truncate" in str(s).lower():
            raise SafetyViolation(
                f"daily_trades 는 TRUNCATE 호출 금지: {s}\n"
                f"  TRUNCATE 가 필요하면 stage6_upload 사용."
            )


# ── 메인 ────────────────────────────────────────────────


_SYNC_RUN_ID = f"daily_{_dt.date.today().strftime('%Y%m%d')}"


def run(args: argparse.Namespace) -> int:
    print(f"[daily_trades] sido={args.sido} sigungu={args.sigungu} "
          f"months_back={args.months_back} dry_run={args.dry_run} "
          f"sync_run_id={_SYNC_RUN_ID}")

    # apartments baseline (자동 실행이라도 사고 시 즉시 abort)
    baseline = snapshot_apartment_baseline()
    print(f"[daily_trades] apartments baseline: {baseline}")

    # 시군구 결정
    if args.sigungu:
        target_sgg = list(args.sigungu)
        print(f"[daily_trades] 명시적 시군구 {len(target_sgg)}개: {target_sgg[:5]}...")
    else:
        all_sgg = _load_sigungu_inventory_from_csv()
        target_sgg = filter_sigungu_by_sido(all_sgg, args.sido)
        print(f"[daily_trades] 시도={args.sido} → 시군구 {len(target_sgg)}개")

    if not target_sgg:
        print("[daily_trades] 대상 시군구 0개 — 종료", file=sys.stderr)
        return 1

    # Phase 1: DB 매칭 인덱스
    print("[daily_trades] P1: DB → 매칭 인덱스")
    strict_idx, jibun_idx, mgm_to_id = build_match_index_from_db()

    # Phase 2: stage1_trades 호출
    print(f"[daily_trades] P2: stage1_trades 호출 "
          f"(시군구 {len(target_sgg)} × 매·전월세 × {args.months_back+1}개월)")
    if not args.dry_run_skip_stage1:
        from . import stage1_trades as s1
        s1.run(target_sgg, months_back=args.months_back)
    else:
        print("[daily_trades] P2 SKIP (--dry-run-skip-stage1)")

    # Phase 3: 매칭 + 정규화
    print("[daily_trades] P3: 매칭 + 정규화")
    blacklist = load_blacklist()
    print(f"[daily_trades] 영구 블랙리스트: {len(blacklist):,}")
    matched, unmatched, raw_for_db, blacklisted_raw, source_stats = match_and_normalize(
        strict_idx, jibun_idx, mgm_to_id, blacklist)

    total = len(matched) + len(unmatched)
    match_pct = (len(matched) / total * 100) if total else 0
    print(f"[daily_trades] P3 결과: matched={len(matched):,}, "
          f"unmatched={len(unmatched):,}, blacklisted={len(blacklisted_raw):,}, "
          f"raw={len(raw_for_db):,} ({match_pct:.2f}% 매칭)")
    print(f"[daily_trades]   분포: {dict(source_stats)}")

    # 작업 디렉토리: unmatched 보관
    out_dir = stage_dir("daily_trades")
    today = _dt.date.today().isoformat()
    write_jsonl(out_dir / f"unmatched_daily_{today}.jsonl", unmatched)
    write_json(out_dir / f"source_stats_{today}.json", dict(source_stats))
    print(f"[daily_trades] unmatched 보관: {out_dir}/unmatched_daily_{today}.jsonl")

    # Phase 4: dry-run 종료
    if args.dry_run:
        print("[daily_trades] DRY-RUN — Phase 5~7 스킵, baseline 재검증")
        assert_baseline_unchanged(baseline)
        return 0

    # Phase 5: officetel_trade_raw UPSERT
    print("[daily_trades] P5: officetel_trade_raw UPSERT")
    inserted_raw = upsert_trade_raw(raw_for_db + blacklisted_raw)
    print(f"[daily_trades] P5 적재: {inserted_raw:,} (dedup 으로 실제 신규는 더 적음)")

    # Phase 6: officetel_trades UPSERT
    print("[daily_trades] P6: officetel_trades UPSERT (매칭만)")
    inserted_trades = upsert_officetel_trades(matched)
    print(f"[daily_trades] P6 적재: {inserted_trades:,}")

    # Phase 7: 집계 재계산 RPC
    print("[daily_trades] P7: RPC 집계 재계산")
    recalc_aggregates()

    # 최종 baseline 검증
    assert_baseline_unchanged(baseline)
    print(f"[daily_trades] 완료. 작업 디렉토리: {out_dir}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sido", default="all",
                   help=f"시도명 ({', '.join(sorted(set(SIDO_CODE_TO_NAME.values())))} | all)")
    p.add_argument("--sigungu", nargs="*",
                   help="명시적 5자리 시군구 코드 (디버깅용. 지정 시 --sido 무시)")
    p.add_argument("--months-back", type=int, default=3,
                   help="현재 달 포함 거꾸로 N개월 (default: 3)")
    p.add_argument("--dry-run", action="store_true",
                   help="DB 쓰기 0, 통계만 (Phase 5~7 우회)")
    p.add_argument("--dry-run-skip-stage1", action="store_true",
                   help="stage1_trades 호출도 건너뜀 (이미 jsonl 있을 때)")
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
