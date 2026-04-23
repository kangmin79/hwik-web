"""Stage 4. 정제 + 매칭 + 게이트.

처리 순서:
  1) recap+title+expos 합쳐 단지 마스터 후보 빌드 (mgm_pk 단위)
  2) (sgg, umd, jibun, offi_norm) → mgm_pk 매핑 인덱스 구축 (expos 기반)
  3) 실거래 JSONL 전수 → 매핑 적용 → unmatched 비율 계산
  4) 5년 10건 gate 적용 → 통과한 mgm_pk 집합
  5) 기존 DB id 회수율 (기존 8,684 중 몇 개가 재발견되는지) 검증
  6) 통과 시 normalized JSONL 생성

산출:
  stage4/officetels.jsonl              # 단지 마스터 (10건 통과)
  stage4/officetel_trades.jsonl        # 정규화 거래
  stage4/officetel_pyeongs.jsonl       # 공급면적 (보존 + 신규 후보)
  stage4/officetel_mgm_pk_map.jsonl    # 거래-단지 매핑 인덱스
  stage4/unmatched_trades.jsonl        # 매칭 실패 분석용
  stage4/gate_report.json              # 회수율/매칭률/통과수
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from collections import Counter
from pathlib import Path as _Path

from .config import (
    ID_RECOVERY_PCT_LIMIT,
    MIN_TRADE_COUNT_5Y,
    UNMATCHED_TRADE_PCT_LIMIT,
    stage_dir,
)
from .db.officetel_id import load_id_map, resolve_id
from .local_store import read_json, read_jsonl, write_json, write_jsonl

# 영구 블랙리스트: 한번이라도 게이트 fail 한 mgm 은 영원히 차단.
# git checkin 되어 매일 sync 마다 누적·재사용됨.
BLACKLIST_PATH = _Path(__file__).parent / "blacklist_mgm.json"


def load_blacklist() -> dict[str, dict]:
    if not BLACKLIST_PATH.exists():
        return {}
    return read_json(BLACKLIST_PATH, default={}) or {}


def save_blacklist(bl: dict[str, dict]) -> None:
    write_json(BLACKLIST_PATH, bl)


def _norm(name: str) -> str:
    """매칭용 정규화 — 공백·점·하이픈 제거 + 소문자."""
    return re.sub(r"[\s\u00a0\.\-]+", "", name or "").strip().lower()


def _to_int(v):
    if v is None or v == "":
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


# ── Phase 1: 단지 마스터 후보 빌드 (recap+title만, expos는 Phase 2에서 통합) ──
def build_complex_candidates_recap_title() -> dict[str, dict]:
    """recap+title 합쳐 mgm_pk → 단지 dict."""
    out: dict[str, dict] = {}

    # recap
    for f in stage_dir("stage2_bldg/recap").glob("*.jsonl"):
        for r in read_jsonl(f):
            mgm = r.get("mgmBldrgstPk")
            if not mgm:
                continue
            d = out.setdefault(mgm, {"mgm_bldrgst_pk": mgm})
            d["bld_nm"] = r.get("bldNm") or d.get("bld_nm")
            d["main_purps"] = r.get("mainPurpsCdNm") or d.get("main_purps")
            d["use_apr_day"] = r.get("useAprDay") or d.get("use_apr_day")
            d["build_year"] = _to_int((r.get("useAprDay") or "")[:4])
            d["tot_area"] = _to_float(r.get("totArea")) or d.get("tot_area")
            d["arch_area"] = _to_float(r.get("archArea")) or d.get("arch_area")
            d["grnd_flr"] = _to_int(r.get("grndFlrCnt")) or d.get("grnd_flr")
            d["ugrnd_flr"] = _to_int(r.get("ugrndFlrCnt")) or d.get("ugrnd_flr")
            d["hhld_cnt"] = _to_int(r.get("hhldCnt")) or d.get("hhld_cnt")
            d["ho_cnt"] = _to_int(r.get("hoCnt")) or d.get("ho_cnt")
            d["jibun_addr"] = r.get("platPlc") or d.get("jibun_addr")
            d["road_addr"] = r.get("newPlatPlc") or d.get("road_addr")
            d["bjdong_cd"] = r.get("bjdongCd") or d.get("bjdong_cd")

    # title — 단지 신규 추가 + 속성 보강
    for f in stage_dir("stage2_bldg/title").glob("*.jsonl"):
        for r in read_jsonl(f):
            mgm = r.get("mgmBldrgstPk")
            if not mgm:
                continue
            d = out.setdefault(mgm, {"mgm_bldrgst_pk": mgm})
            # title 에만 있는 단지를 위해 기본 필드 (recap 누락 케이스)
            d.setdefault("bld_nm", r.get("bldNm"))
            d.setdefault("main_purps", r.get("mainPurpsCdNm"))
            d.setdefault("use_apr_day", r.get("useAprDay"))
            if not d.get("build_year") and r.get("useAprDay"):
                d["build_year"] = _to_int((r.get("useAprDay") or "")[:4])
            d.setdefault("tot_area", _to_float(r.get("totArea")))
            d.setdefault("hhld_cnt", _to_int(r.get("hhldCnt")))
            d.setdefault("ho_cnt", _to_int(r.get("hoCnt")))
            d.setdefault("jibun_addr", r.get("platPlc"))
            d.setdefault("road_addr", r.get("newPlatPlc"))
            d.setdefault("bjdong_cd", r.get("bjdongCd"))
            d["strct_name"] = r.get("strctCdNm") or d.get("strct_name")
            d["bc_ratio"] = _to_float(r.get("bcRat")) or d.get("bc_ratio")
            d["vl_ratio"] = _to_float(r.get("vlRat")) or d.get("vl_ratio")
            psf = (_to_int(r.get("indrAutoUtcnt")) or 0) + (_to_int(r.get("oudrAutoUtcnt")) or 0)
            psm = (_to_int(r.get("indrMechUtcnt")) or 0) + (_to_int(r.get("oudrMechUtcnt")) or 0)
            if psf:
                d["parking_self"] = psf
            if psm:
                d["parking_mech"] = psm
            d["parking_total"] = (d.get("parking_self") or 0) + (d.get("parking_mech") or 0)
            d["elevator_ride"] = _to_int(r.get("rideUseElvtCnt")) or d.get("elevator_ride")
            d["elevator_emgen"] = _to_int(r.get("emgenUseElvtCnt")) or d.get("elevator_emgen")
            d["earthquake_rating"] = (r.get("sismcDsgnApplyYn") or
                                       r.get("earthquake_rating") or
                                       d.get("earthquake_rating"))

    return out


# ── Phase 2: expos 1회 스캔 — 단지 추가 + 매핑 인덱스 동시 빌드 ──
def build_indexes_from_expos(candidates: dict[str, dict]) -> tuple[dict, dict, dict, dict]:
    """expos 1회 스캔으로 단지 후보 보강 + 4종 인덱스 빌드.

    반환:
      strict_idx     — (sgg, jibun, bld_norm) → mgm   (bldNm 있을 때만)
      jibun_idx      — (sgg, jibun) → list[mgm]       (지번에 등록된 모든 mgm)
      mgm_to_complex — mgm → (sgg, jibun, bld_norm)   (좌표 매핑용 역인덱스)
      mgm_to_jibun   — mgm → (sgg, jibun)             (bldNm 없는 mgm도 포함)
    """
    from collections import defaultdict
    strict_idx: dict[tuple, str] = {}
    jibun_idx: dict[tuple, list[str]] = defaultdict(list)
    mgm_to_complex: dict[str, tuple] = {}
    mgm_to_jibun: dict[str, tuple] = {}
    seen_jibun_set: dict[tuple, set] = defaultdict(set)   # mgm dedup 가속화

    files = list(stage_dir("stage2_bldg/expos").glob("*.jsonl"))
    total_files = len(files)
    for i, f in enumerate(files, 1):
        if i % 1000 == 0:
            print(f"[stage4]    expos 진행 {i}/{total_files} ({i/total_files*100:.0f}%)", flush=True)
        for r in read_jsonl(f):
            mgm = r.get("mgmBldrgstPk")
            if not mgm:
                continue
            # 단지 후보 보강 (recap/title 누락 케이스)
            d = candidates.setdefault(mgm, {"mgm_bldrgst_pk": mgm})
            if not d.get("bld_nm"): d["bld_nm"] = r.get("bldNm")
            if not d.get("jibun_addr"): d["jibun_addr"] = r.get("platPlc")
            if not d.get("road_addr"): d["road_addr"] = r.get("newPlatPlc")
            if not d.get("bjdong_cd"): d["bjdong_cd"] = r.get("bjdongCd")

            sgg = r.get("sigunguCd", "")
            if not sgg:
                continue
            bun = (r.get("bun") or "").lstrip("0") or "0"
            ji = (r.get("ji") or "").lstrip("0") or "0"
            bld = _norm(r.get("bldNm"))
            jibun = f"{bun}-{ji}" if ji != "0" else bun

            if bld:
                strict_idx.setdefault((sgg, jibun, bld), mgm)
                mgm_to_complex.setdefault(mgm, (sgg, jibun, bld))
            jkey = (sgg, jibun)
            mgm_to_jibun.setdefault(mgm, jkey)
            if mgm not in seen_jibun_set[jkey]:
                seen_jibun_set[jkey].add(mgm)
                jibun_idx[jkey].append(mgm)
    return strict_idx, dict(jibun_idx), mgm_to_complex, mgm_to_jibun


def resolve_mgm(sgg: str, jibun: str, offi: str,
                strict_idx: dict, jibun_idx: dict) -> tuple[str | None, str]:
    """3단계 fallback 매칭. 반환: (mgm or None, source).

    source: 'strict' | 'jibun_single' | 'jibun_multi' | 'unmatched'
    """
    bld = _norm(offi)
    if (sgg, jibun, bld) in strict_idx:
        return strict_idx[(sgg, jibun, bld)], "strict"
    candidates = jibun_idx.get((sgg, jibun), [])
    if len(candidates) == 1:
        return candidates[0], "jibun_single"
    if candidates:
        return candidates[0], "jibun_multi"
    return None, "unmatched"


# ── Phase 3: 실거래 → mgm_pk 매핑 + 정규화 (3단계 fallback) ─────────────────
def normalize_trades(complex_candidates: dict[str, dict],
                     strict_idx: dict, jibun_idx: dict
                     ) -> tuple[list[dict], list[dict], Counter, Counter]:
    """매매·전월세 JSONL 전수 → 정규화 + 매칭.

    반환: (matched, unmatched, trade_counts, source_stats)
    """
    matched: list[dict] = []
    unmatched: list[dict] = []
    trade_counts: Counter = Counter()
    source_stats: Counter = Counter()

    for kind in ("sale", "rent"):
        deal_type_default = "매매" if kind == "sale" else None
        base = stage_dir(f"stage1_trades/{kind}")
        for f in base.glob("*.jsonl"):
            for r in read_jsonl(f):
                sgg = (r.get("sggCd") or r.get("_sigungu_cd") or "").strip()
                jibun = (r.get("jibun") or "").strip()
                offi = r.get("offiNm", "")
                if not (sgg and jibun and offi):
                    unmatched.append({"reason": "missing_key", **r})
                    source_stats["missing_key"] += 1
                    continue
                mgm, source = resolve_mgm(sgg, jibun, offi, strict_idx, jibun_idx)
                source_stats[source] += 1
                if not mgm:
                    unmatched.append({"reason": "no_mgm_match",
                                       "sgg": sgg, "jibun": jibun, "offi": offi})
                    continue
                # 거래 type 결정
                deal_type = deal_type_default
                if not deal_type:
                    monthly = _to_int(r.get("monthlyRent"))
                    deal_type = "월세" if (monthly and monthly > 0) else "전세"
                trade_counts[mgm] += 1
                matched.append({
                    "mgm_bldrgst_pk": mgm,
                    "match_source": source,
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
                })
    return matched, unmatched, trade_counts, source_stats


# ── Phase 4: 10건 gate + id 회수율 ─────────────────
def run_gates(complex_candidates: dict[str, dict], trade_counts: Counter,
              matched: list[dict], unmatched: list[dict],
              id_map: dict[str, str]) -> dict:
    total_trades = len(matched) + len(unmatched)
    unmatched_pct = len(unmatched) / total_trades if total_trades else 0
    print(f"[stage4] 매칭률 {1-unmatched_pct:.4%} (matched={len(matched):,}, unmatched={len(unmatched):,})")

    # 영구 블랙리스트 — 한번이라도 fail 한 mgm 은 평생 차단
    blacklist = load_blacklist()
    today = _dt.date.today().isoformat()
    bl_initial = len(blacklist)
    print(f"[stage4] 영구 블랙리스트 로드: {bl_initial:,}")

    # 게이트 1: 5년 누적 거래 ≥ MIN_TRADE_COUNT_5Y
    pass_trades = {mgm for mgm, n in trade_counts.items()
                   if n >= MIN_TRADE_COUNT_5Y and mgm in complex_candidates}
    fail_trade = [mgm for mgm in trade_counts
                  if mgm in complex_candidates and mgm not in pass_trades]
    print(f"[stage4] gate1 거래 ≥{MIN_TRADE_COUNT_5Y} 통과: {len(pass_trades):,} "
          f"(거래 미달 {len(fail_trade):,})")

    # 게이트 2: bld_nm 필수
    qualified_mgm = {mgm for mgm in pass_trades
                     if (complex_candidates[mgm].get("bld_nm") or "").strip()}
    fail_name = [mgm for mgm in pass_trades if mgm not in qualified_mgm]
    print(f"[stage4] gate2 bld_nm 필수 통과: {len(qualified_mgm):,} "
          f"(이름 없음 제외 {len(fail_name):,})")

    # 영구 블랙리스트 적용 — 게이트 통과해도 과거에 fail 한 적 있으면 drop
    blocked = qualified_mgm & set(blacklist.keys())
    if blocked:
        qualified_mgm -= blocked
        print(f"[stage4] 영구 블랙리스트 차단: {len(blocked):,} → 최종 통과 {len(qualified_mgm):,}")

    # 신규 fail mgm 을 블랙리스트에 추가 (다음 sync 부터 영원히 차단)
    new_added = 0
    for mgm in fail_trade:
        if mgm not in blacklist:
            blacklist[mgm] = {"reason": "trade_below_min", "first_seen": today}
            new_added += 1
    for mgm in fail_name:
        if mgm not in blacklist:
            blacklist[mgm] = {"reason": "no_bld_nm", "first_seen": today}
            new_added += 1
    if new_added:
        save_blacklist(blacklist)
        print(f"[stage4] 블랙리스트 신규 추가 {new_added:,} → 총 {len(blacklist):,}")

    # id 회수율 — 기존 매핑 8,684 중 재발견된 비율
    if id_map:
        recovered = sum(1 for mgm in id_map.keys() if mgm in qualified_mgm)
        recovery_pct = recovered / len(id_map)
        print(f"[stage4] 기존 id 회수율 {recovery_pct:.4%} ({recovered}/{len(id_map)})")
    else:
        recovery_pct = 1.0
        print("[stage4] id_map 비어있음 - 회수율 검사 스킵")

    return {
        "matched": len(matched),
        "unmatched": len(unmatched),
        "unmatched_pct": unmatched_pct,
        "qualified_complex": len(qualified_mgm),
        "id_recovery_pct": recovery_pct,
        "qualified_mgm": list(qualified_mgm),
    }


def _apply_phase5(qualified: set[str], candidates: dict[str, dict],
                  trade_counts: Counter, mgm_to_complex: dict, mgm_to_jibun: dict,
                  id_map: dict[str, str]) -> list[dict]:
    """Phase 5 좌표 적용 + officetels dict 리스트 생성.

    좌표 lookup 3단계 fallback:
      1) coord_cache[mgm] (직접)
      2) coord_by_complex[mgm_to_complex[mgm]] ((sgg, jibun, bld))
      3) coord_by_jibun[mgm_to_jibun[mgm]]     ((sgg, jibun))
    """
    coord_cache = read_json(stage_dir("stage3_geocode") / "coords_cache.json", default={}) or {}

    coord_by_complex: dict[tuple, dict] = {}
    coord_by_jibun: dict[tuple, dict] = {}
    for mgm, c in coord_cache.items():
        if not (c.get("jibun_lat") or c.get("road_lat")):
            continue
        ck = mgm_to_complex.get(mgm)
        if ck:
            coord_by_complex.setdefault(ck, c)
        jk = mgm_to_jibun.get(mgm)
        if jk:
            coord_by_jibun.setdefault(jk, c)
    print(f"[stage4] 좌표 인덱스: cache={len(coord_cache):,} mgm → "
          f"complex={len(coord_by_complex):,}, jibun={len(coord_by_jibun):,}")

    officetels_out = []
    hit_mgm = hit_complex = hit_jibun = 0
    for mgm in qualified:
        d = dict(candidates[mgm])
        d["trade_count"] = trade_counts[mgm]
        d["property_type"] = "offi"

        c = coord_cache.get(mgm)
        source = "mgm" if c and (c.get("jibun_lat") or c.get("road_lat")) else None
        if not source:
            ck = mgm_to_complex.get(mgm)
            if ck and ck in coord_by_complex:
                c = coord_by_complex[ck]
                source = "complex"
        if not source:
            jk = mgm_to_jibun.get(mgm)
            if jk and jk in coord_by_jibun:
                c = coord_by_jibun[jk]
                source = "jibun"

        if source:
            d.update({
                "jibun_addr": c.get("jibun_addr") or d.get("jibun_addr"),
                "jibun_lat": c.get("jibun_lat"),
                "jibun_lng": c.get("jibun_lng"),
                "road_addr": c.get("road_addr") or d.get("road_addr"),
                "road_lat": c.get("road_lat"),
                "road_lng": c.get("road_lng"),
                "coord_precision": c.get("coord_precision", "missing"),
                "coord_match_source": source,
            })
            if source == "mgm": hit_mgm += 1
            elif source == "complex": hit_complex += 1
            elif source == "jibun": hit_jibun += 1

        offi_id, _ = resolve_id(mgm, id_map)
        d["id"] = offi_id
        officetels_out.append(d)

    total = len(officetels_out)
    hit = hit_mgm + hit_complex + hit_jibun
    print(f"[stage4] 좌표 보유: {hit:,}/{total:,} ({hit/total*100:.1f}%) "
          f"[mgm={hit_mgm:,}, complex={hit_complex:,}, jibun={hit_jibun:,}]")
    return officetels_out


def run(phase5_only: bool = False) -> int:
    out_dir = stage_dir("stage4")

    print("[stage4] Phase 1: 단지 후보 빌드 (recap+title)", flush=True)
    candidates = build_complex_candidates_recap_title()
    print(f"[stage4]  → recap+title 후보 {len(candidates):,}", flush=True)

    print("[stage4] Phase 2: expos 1회 스캔 (단지 추가 + 매핑 인덱스 동시)", flush=True)
    strict_idx, jibun_idx, mgm_to_complex, mgm_to_jibun = build_indexes_from_expos(candidates)
    print(f"[stage4]  → 최종 후보 {len(candidates):,}, strict {len(strict_idx):,}, "
          f"jibun {len(jibun_idx):,}, mgm_to_complex {len(mgm_to_complex):,}, "
          f"mgm_to_jibun {len(mgm_to_jibun):,}", flush=True)

    id_map = load_id_map()

    if phase5_only:
        # 기존 officetels.jsonl 에서 qualified + trade_counts 복원
        existing = list(read_jsonl(out_dir / "officetels.jsonl"))
        qualified = {d["mgm_bldrgst_pk"] for d in existing}
        trade_counts = Counter({d["mgm_bldrgst_pk"]: d["trade_count"] for d in existing})
        print(f"[stage4] (phase5-only) 기존 officetels.jsonl 에서 {len(qualified):,} 단지 로드")

        officetels_out = _apply_phase5(qualified, candidates, trade_counts,
                                       mgm_to_complex, mgm_to_jibun, id_map)
        write_jsonl(out_dir / "officetels.jsonl", officetels_out)
        print(f"[stage4] officetels.jsonl 재작성: {len(officetels_out):,}")

        # officetel_trades.jsonl 은 qualified 변동 없으면 그대로 유지
        # (mgm list가 같으므로 재작성 불필요)
        return 0

    print("[stage4] Phase 3: 거래 정규화 + 매칭")
    matched, unmatched, trade_counts, source_stats = normalize_trades(
        candidates, strict_idx, jibun_idx)
    print(f"[stage4] 매칭 분포: {dict(source_stats)}")

    print("[stage4] Phase 4: 게이트")
    report = run_gates(candidates, trade_counts, matched, unmatched, id_map)
    report["match_sources"] = dict(source_stats)

    write_json(out_dir / "gate_report.json", {k: v for k, v in report.items() if k != "qualified_mgm"})
    write_jsonl(out_dir / "unmatched_trades.jsonl", unmatched)

    if report["unmatched_pct"] > UNMATCHED_TRADE_PCT_LIMIT:
        print(f"[stage4] ABORT: 매칭 실패율 {report['unmatched_pct']:.4%} > {UNMATCHED_TRADE_PCT_LIMIT:.4%}",
              file=sys.stderr)
        return 1
    if report["id_recovery_pct"] < ID_RECOVERY_PCT_LIMIT and id_map:
        print(f"[stage4] ABORT: id 회수율 {report['id_recovery_pct']:.4%} < {ID_RECOVERY_PCT_LIMIT:.4%}",
              file=sys.stderr)
        return 1

    qualified = set(report["qualified_mgm"])
    print("[stage4] 게이트 통과 - Phase 5: officetels/trades JSONL 생성")

    officetels_out = _apply_phase5(qualified, candidates, trade_counts,
                                   mgm_to_complex, mgm_to_jibun, id_map)
    write_jsonl(out_dir / "officetels.jsonl", officetels_out)
    print(f"[stage4] officetels.jsonl: {len(officetels_out):,}")

    qualified_trades = [t for t in matched if t["mgm_bldrgst_pk"] in qualified]
    mgm_to_id = {d["mgm_bldrgst_pk"]: d["id"] for d in officetels_out}
    for t in qualified_trades:
        t["officetel_id"] = mgm_to_id[t["mgm_bldrgst_pk"]]
    write_jsonl(out_dir / "officetel_trades.jsonl", qualified_trades)
    print(f"[stage4] officetel_trades.jsonl: {len(qualified_trades):,}")

    # 매핑 인덱스 저장
    map_rows = [{"sgg_cd": k[0], "jibun": k[1], "offi_nm_norm": k[2], "mgm_bldrgst_pk": v}
                for k, v in strict_idx.items()]
    write_jsonl(out_dir / "officetel_mgm_pk_map.jsonl", map_rows)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["all", "5"], default="all",
                   help="'5': Phase 1+2+5만 실행 (좌표 재적용, Phase 3 스킵)")
    args = p.parse_args()
    return run(phase5_only=(args.phase == "5"))


if __name__ == "__main__":
    sys.exit(main())
