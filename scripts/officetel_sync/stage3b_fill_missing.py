"""Stage 3b. 누락 좌표 보강 — 카카오 address.json.

배경: qualified 11,192 complex 중 약 8,300개가 Stage 3 캐시와 교차하지 않아
좌표 누락. stage4/officetels.jsonl 에는 jibun_addr/road_addr 이 이미
정규화되어 있으므로, expos 재스캔 없이 주소로 kakao address_search 호출.

응답 → coords_cache.json (stage3 포맷과 동일) 에 mgm_pk 키로 누적.
이후 `python -m scripts.officetel_sync.stage4_normalize --phase 5` 로 반영.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import KAKAO_WORKERS, stage_dir
from .fetch.kakao_client import KakaoError, address_search, parse_address_doc
from .local_store import read_json, read_jsonl, write_json, write_jsonl


def _geocode(mgm: str, jibun_q: str, road_q: str) -> tuple[str, dict | None, str | None]:
    coord = {
        "mgm_bldrgst_pk": mgm,
        "jibun_addr": "", "jibun_lat": None, "jibun_lng": None,
        "road_addr": "", "road_lat": None, "road_lng": None,
        "coord_precision": "missing",
        "coord_source": "kakao",
    }
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
        if coord["jibun_lat"] or coord["road_lat"]:
            return mgm, coord, None
        return mgm, None, "no_docs"
    except KakaoError as e:
        return mgm, None, str(e)[:120]


def _flush(cache_path, cache) -> None:
    write_json(cache_path, cache)
    out_jsonl = stage_dir("stage3_geocode") / "coords.jsonl"
    write_jsonl(out_jsonl, list(cache.values()), mode="w")


def run() -> int:
    ogt_path = stage_dir("stage4") / "officetels.jsonl"
    cache_path = stage_dir("stage3_geocode") / "coords_cache.json"

    officetels = list(read_jsonl(ogt_path))
    cache = read_json(cache_path, default={}) or {}
    print(f"[stage3b] officetels 로드: {len(officetels):,}")
    print(f"[stage3b] 기존 cache: {len(cache):,} mgm")

    pending: list[tuple[str, str, str]] = []
    for d in officetels:
        if d.get("jibun_lat") or d.get("road_lat"):
            continue
        mgm = d["mgm_bldrgst_pk"]
        c = cache.get(mgm)
        if c and (c.get("jibun_lat") or c.get("road_lat")):
            continue
        jibun_q = d.get("jibun_addr") or ""
        road_q = d.get("road_addr") or ""
        if not (jibun_q or road_q):
            continue
        pending.append((mgm, jibun_q, road_q))

    print(f"[stage3b] 좌표 없는 qualified mgm (주소 보유): {len(pending):,}")
    if not pending:
        print("[stage3b] 할 일 없음")
        _flush(cache_path, cache)
        return 0

    started = time.time()
    last = [time.time()]
    done = [0]
    ok = [0]
    fail = [0]
    fail_reasons: Counter = Counter()
    fail_samples: list = []

    with ThreadPoolExecutor(max_workers=KAKAO_WORKERS) as ex:
        futs = {ex.submit(_geocode, mgm, j, r): (mgm, j, r) for mgm, j, r in pending}
        for fut in as_completed(futs):
            mgm, coord, err = fut.result()
            done[0] += 1
            if coord:
                cache[mgm] = coord
                ok[0] += 1
            else:
                fail[0] += 1
                fail_reasons[err or "unknown"] += 1
                if err and err != "no_docs" and len(fail_samples) < 5:
                    fail_samples.append((mgm, err))
            now = time.time()
            if now - last[0] >= 5.0 or done[0] == len(pending):
                elapsed = now - started
                rate = done[0] / elapsed if elapsed else 0
                eta = (len(pending) - done[0]) / rate if rate else 0
                print(f"[stage3b] {done[0]}/{len(pending)} "
                      f"({done[0]/len(pending)*100:.1f}%) ok={ok[0]} fail={fail[0]} "
                      f"rate={rate:.1f}/s ETA={eta:.0f}s", flush=True)
                last[0] = now
                _flush(cache_path, cache)

    _flush(cache_path, cache)
    print(f"[stage3b] 완료: ok={ok[0]:,} fail={fail[0]:,} cache 총 {len(cache):,} mgm")
    print(f"[stage3b] 실패 원인 상위:")
    for reason, n in fail_reasons.most_common(10):
        print(f"  {n:>6}  {reason}")
    if fail_samples:
        print(f"[stage3b] 실패 샘플(비-no_docs):")
        for mgm, err in fail_samples:
            print(f"  mgm={mgm} err={err}")
    return 0


def main() -> int:
    argparse.ArgumentParser().parse_args()
    return run()


if __name__ == "__main__":
    sys.exit(main())
