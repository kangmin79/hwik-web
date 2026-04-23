"""Stage 3. 단지 좌표 보강 (카카오).

입력: stage2_bldg/expos/*.jsonl 에서 추출한 (mgmBldrgstPk, platPlc, newPlatPlc)
캐시: COLLECT_ROOT/stage3_geocode/coords_cache.json (mgm_pk → coord dict)
산출: stage3_geocode/coords.jsonl

기존 officetel_test/*/geocode_cache.json 이 있으면 우선 이전 캐시 import.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .checkpoint import Checkpoint
from .config import COLLECT_ROOT, KAKAO_WORKERS, stage_dir
from .fetch.kakao_client import KakaoError, address_search, parse_address_doc
from .local_store import read_json, read_jsonl, write_json, write_jsonl

_OLD_CACHE_DIR = Path("c:/Users/강동욱/Desktop/officetel_test")


def _import_old_caches() -> dict[str, dict]:
    """기존 officetel_test/*/geocode_cache.json 들을 합쳐 mgm_pk → coord 캐시 시도.

    이전 캐시 구조 미상이라 로드 가능한 형태만 흡수.
    """
    out: dict[str, dict] = {}
    if not _OLD_CACHE_DIR.exists():
        return out
    for p in _OLD_CACHE_DIR.glob("*/geocode_cache.json"):
        try:
            data = read_json(p, default={}) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if isinstance(v, dict) and (v.get("lat") or v.get("y")):
                out[k] = v
    return out


def _extract_complex_addresses() -> list[dict]:
    """stage1b 거래 인벤토리(18,906)와 매칭되는 mgm_pk만 추출.

    expos 전체(508k)는 같은 지번의 모든 건물 포함 → 좌표 호출 낭비.
    거래가 실제 발생한 단지(sgg+jibun+bld_norm 매칭) 만 좌표 필요.
    """
    import re
    def _norm(s: str) -> str:
        return re.sub(r"[\s\u00a0]+", "", s or "").strip().lower()

    # stage1b 인벤토리 키셋
    inv_keys: set[tuple[str, str, str]] = set()
    inv_path = stage_dir("stage1b_addresses") / "addresses.jsonl"
    for r in read_jsonl(inv_path):
        inv_keys.add((r["sgg_cd"], r["jibun"], _norm(r["offi_nm"])))
    print(f"[stage3] stage1b 인벤토리 키 {len(inv_keys):,}")

    # expos 에서 매칭되는 단지 추출 → 단지(sgg+jibun+bld) 단위로 1개 mgm_pk만 keep
    # 한 단지에 호별 mgm_pk 가 평균 20개 → 좌표는 같으니 대표만 호출
    base = stage_dir("stage2_bldg/expos")
    seen_complex: dict[tuple, dict] = {}     # (sgg, jibun, bld) → 대표 row
    scanned = 0
    for f in base.glob("*.jsonl"):
        for r in read_jsonl(f):
            scanned += 1
            mgm = r.get("mgmBldrgstPk")
            if not mgm:
                continue
            sgg = r.get("sigunguCd", "")
            bun = (r.get("bun") or "").lstrip("0") or "0"
            ji = (r.get("ji") or "").lstrip("0") or "0"
            bld = _norm(r.get("bldNm"))
            jibun = f"{bun}-{ji}" if ji != "0" else bun
            key = (sgg, jibun, bld)
            if key not in inv_keys or key in seen_complex:
                continue
            seen_complex[key] = {
                "mgm_bldrgst_pk": mgm,
                "plat_plc": r.get("platPlc", "").strip(),
                "new_plat_plc": r.get("newPlatPlc", "").strip(),
                "bld_nm": r.get("bldNm", "").strip(),
            }
    print(f"[stage3] expos {scanned:,} row 스캔 → 거래 매칭 단지 {len(seen_complex):,}")
    return list(seen_complex.values())


def geocode_one(item: dict) -> tuple[str, dict | None, Exception | None]:
    """지번 + 도로명 둘 다 시도. 더 정확한 쪽 채택."""
    mgm = item["mgm_bldrgst_pk"]
    jibun_q = item.get("plat_plc")
    road_q = item.get("new_plat_plc")

    coord = {"mgm_bldrgst_pk": mgm,
             "jibun_addr": "", "jibun_lat": None, "jibun_lng": None,
             "road_addr": "", "road_lat": None, "road_lng": None,
             "coord_precision": "missing"}
    try:
        if jibun_q:
            doc = address_search(jibun_q)
            if doc:
                p = parse_address_doc(doc)
                coord["jibun_addr"] = p["jibun_addr"]
                coord["jibun_lat"] = p["lat"]
                coord["jibun_lng"] = p["lng"]
                if p["road_addr"]:
                    coord["road_addr"] = p["road_addr"]
                    coord["road_lat"] = p["road_lat"]
                    coord["road_lng"] = p["road_lng"]
                coord["coord_precision"] = "precise"
        if not coord["road_lat"] and road_q:
            doc = address_search(road_q)
            if doc:
                p = parse_address_doc(doc)
                coord["road_addr"] = p["road_addr"] or p["jibun_addr"]
                coord["road_lat"] = p["lat"]
                coord["road_lng"] = p["lng"]
                if not coord["jibun_lat"]:
                    coord["jibun_lat"] = p["lat"]
                    coord["jibun_lng"] = p["lng"]
                coord["coord_precision"] = "precise"
        return mgm, coord, None
    except KakaoError as e:
        return mgm, None, e


def run() -> None:
    items = _extract_complex_addresses()
    print(f"[stage3] 단지 후보 {len(items)}")

    # 캐시 로드
    cache_path = stage_dir("stage3_geocode") / "coords_cache.json"
    cache = read_json(cache_path, default={}) or {}

    # 이전 officetel_test 캐시 흡수
    old = _import_old_caches()
    if old:
        print(f"[stage3] 기존 officetel_test 캐시 흡수 시도: {len(old)} (구조 미일치 시 무시)")

    cp = Checkpoint(COLLECT_ROOT / "checkpoint.db")
    pending = []
    skipped_cache = 0
    for it in items:
        mgm = it["mgm_bldrgst_pk"]
        if mgm in cache or cp.is_done("stage3_geocode", mgm):
            skipped_cache += 1
            continue
        pending.append(it)
    print(f"[stage3] 캐시 적중 {skipped_cache}, 신규 호출 {len(pending)}")

    if not pending:
        _flush(cache_path, cache)
        return

    started = time.time()
    last = [time.time()]
    done = [0]

    with ThreadPoolExecutor(max_workers=KAKAO_WORKERS) as ex:
        futs = {ex.submit(geocode_one, it): it for it in pending}
        for fut in as_completed(futs):
            mgm, coord, err = fut.result()
            done[0] += 1
            if err:
                cp.mark_error("stage3_geocode", mgm, str(err))
            else:
                if coord:
                    cache[mgm] = coord
                cp.mark_done("stage3_geocode", mgm, 1)
            now = time.time()
            if now - last[0] >= 5.0 or done[0] == len(pending):
                elapsed = now - started
                rate = done[0] / elapsed if elapsed else 0
                eta = (len(pending) - done[0]) / rate if rate else 0
                print(f"[stage3] {done[0]}/{len(pending)} ({done[0]/len(pending)*100:.1f}%) "
                      f"rate={rate:.1f}/s ETA={eta:.0f}s",
                      flush=True)
                last[0] = now
                # 주기 저장
                _flush(cache_path, cache)

    _flush(cache_path, cache)


def _flush(cache_path: Path, cache: dict) -> None:
    write_json(cache_path, cache)
    out_jsonl = stage_dir("stage3_geocode") / "coords.jsonl"
    write_jsonl(out_jsonl, list(cache.values()), mode="w")


def main() -> int:
    p = argparse.ArgumentParser()
    p.parse_args()
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
