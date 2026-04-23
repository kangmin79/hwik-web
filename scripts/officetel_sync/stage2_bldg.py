"""Stage 2. 건축물대장 3 API (총괄·표제·전유) 병렬 수집.

입력: stage1b_addresses/addresses.jsonl (sgg+umd+jibun+offi)
1) 카카오로 bjdongCd 보강 (캐시)
2) 3 API 병렬 호출
3) 산출:
   - stage2_bldg/recap/{key}.jsonl
   - stage2_bldg/title/{key}.jsonl
   - stage2_bldg/expos/{key}.jsonl
   - stage2_bldg/bjdong_cache.jsonl
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .checkpoint import Checkpoint
from .config import (
    BLDG_WORKERS,
    COLLECT_ROOT,
    MOLIT_BLDG_EXPOS,
    MOLIT_BLDG_RECAP,
    MOLIT_BLDG_TITLE,
    stage_dir,
)
from .fetch.kakao_client import KakaoError, address_search, parse_address_doc
from .fetch.molit_client import fetch_all_pages
from .local_store import read_jsonl, read_json, write_json, write_jsonl


@dataclass(frozen=True)
class BldgAddress:
    sgg_cd: str
    bjdong_cd: str
    bun: str
    ji: str
    offi_nm: str

    @property
    def key(self) -> str:
        return f"{self.sgg_cd}_{self.bjdong_cd}_{self.bun}_{self.ji}"

    def params(self) -> dict:
        return {
            "sigunguCd": self.sgg_cd,
            "bjdongCd": self.bjdong_cd,
            "bun": self.bun,
            "ji": self.ji,
        }


# ── bjdongCd 보강 ─────────────────────────────────────
def enrich_bjdong_codes(rows: list[dict]) -> list[BldgAddress]:
    """sgg+umd → bjdong_cd 카카오 매핑.

    sgg_cd+umd_nm 단위로 1회씩만 호출 (캐시).
    """
    cache_path = stage_dir("stage2_bldg") / "bjdong_cache.json"
    cache = read_json(cache_path, default={}) or {}
    misses = []

    sgg_umd_to_bjd: dict[str, str] = {**cache}
    todo_keys = []
    for r in rows:
        k = f"{r['sgg_cd']}|{r['umd_nm']}"
        if k not in sgg_umd_to_bjd:
            todo_keys.append(k)
    todo_keys = list(dict.fromkeys(todo_keys))   # dedup, 순서 유지
    print(f"[stage2:bjdong] 캐시 {len(cache)}개, 신규 조회 {len(todo_keys)}개")

    if todo_keys:
        for i, k in enumerate(todo_keys):
            sgg_cd, umd_nm = k.split("|", 1)
            sido = _sido_name_for(sgg_cd)
            sgg_name = _sgg_name_for(sgg_cd)
            query = f"{sido} {sgg_name} {umd_nm}".strip()
            try:
                doc = address_search(query)
            except KakaoError as e:
                print(f"[stage2:bjdong] 카카오 오류 ({query}): {e}", file=sys.stderr)
                continue
            if doc:
                p = parse_address_doc(doc)
                if p["bjdong_cd"]:
                    sgg_umd_to_bjd[k] = p["bjdong_cd"]
            if (i + 1) % 100 == 0:
                write_json(cache_path, sgg_umd_to_bjd)
                print(f"[stage2:bjdong] {i+1}/{len(todo_keys)} 진행", flush=True)
        write_json(cache_path, sgg_umd_to_bjd)
        misses = [k for k in todo_keys if k not in sgg_umd_to_bjd]
        if misses:
            print(f"[stage2:bjdong] 매핑 실패 {len(misses)}개: {misses[:5]}")

    out: list[BldgAddress] = []
    skipped = 0
    for r in rows:
        k = f"{r['sgg_cd']}|{r['umd_nm']}"
        bjd = sgg_umd_to_bjd.get(k)
        if not bjd:
            skipped += 1
            continue
        out.append(BldgAddress(
            sgg_cd=r["sgg_cd"],
            bjdong_cd=bjd,
            bun=r["bun"],
            ji=r["ji"],
            offi_nm=r["offi_nm"],
        ))
    print(f"[stage2:bjdong] 변환 성공 {len(out)} / 실패 {skipped}")
    # 동일 (sgg+bjd+bun+ji) 중복 제거 — 같은 지번에 단지 여러 개여도 호출 1회
    dedup = {a.key: a for a in out}
    print(f"[stage2:bjdong] 중복 제거 후 호출 대상 {len(dedup)}개")
    return list(dedup.values())


def _sido_name_for(sgg_cd: str) -> str:
    from .config import SIDO_CODES
    return SIDO_CODES.get(sgg_cd[:2], "")


def _sgg_name_for(sgg_cd: str) -> str:
    """국토부 법정동 CSV 에서 코드→이름 (지연 로드)."""
    return _SGG_NAME_CACHE.get(sgg_cd, "")


_SGG_NAME_CACHE: dict[str, str] = {}


def _load_sgg_names() -> None:
    if _SGG_NAME_CACHE:
        return
    import csv
    from .config import REPO_ROOT
    csvs = list(REPO_ROOT.glob("국토교통부_법정동코드*.csv"))
    if not csvs:
        return
    for enc in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            with csvs[0].open("r", encoding=enc) as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 2:
                        code = row[0].strip()
                        name = row[1].strip()
                        if len(code) >= 5 and code.isdigit():
                            sgg = code[:5]
                            # 시도+시군구만 추출 (읍면동 제외)
                            if code[5:] == "00000":
                                # 시도 자체
                                continue
                            if code.endswith("00000"):
                                _SGG_NAME_CACHE.setdefault(sgg, name)
                                continue
                            # 시군구 단위 row: 두 번째 토큰까지만
                            parts = name.split()
                            if len(parts) >= 2:
                                _SGG_NAME_CACHE.setdefault(sgg, parts[1])
            return
        except UnicodeDecodeError:
            continue


# ── 병렬 호출 ─────────────────────────────────────
_API_TARGETS = (
    ("recap", MOLIT_BLDG_RECAP),
    ("title", MOLIT_BLDG_TITLE),
    ("expos", MOLIT_BLDG_EXPOS),
)


def fetch_one(addr: BldgAddress, api_kind: str, url: str) -> tuple[BldgAddress, str, int]:
    rows = fetch_all_pages(url, addr.params())
    for r in rows:
        r["_addr_key"] = addr.key
    out_path = stage_dir(f"stage2_bldg/{api_kind}") / f"{addr.key}.jsonl"
    write_jsonl(out_path, rows, mode="w")
    return addr, api_kind, len(rows)


def run() -> None:
    _load_sgg_names()
    addresses_path = stage_dir("stage1b_addresses") / "addresses.jsonl"
    src = list(read_jsonl(addresses_path))
    if not src:
        print("[stage2] stage1b 인벤토리 비어있음", file=sys.stderr)
        sys.exit(1)
    print(f"[stage2] stage1b 로드: {len(src)}")

    addrs = enrich_bjdong_codes(src)
    if not addrs:
        print("[stage2] bjdongCd 보강 실패 (카카오 키 점검)", file=sys.stderr)
        sys.exit(1)

    cp = Checkpoint(COLLECT_ROOT / "checkpoint.db")
    tasks = []
    for a in addrs:
        for kind, url in _API_TARGETS:
            stage_key = f"stage2_{kind}"
            if not cp.is_done(stage_key, a.key):
                tasks.append((a, kind, url))
    total_full = len(addrs) * len(_API_TARGETS)
    print(f"[stage2] 작업 {len(tasks)}/{total_full} (기존 {total_full - len(tasks)} 완료)")

    if not tasks:
        _print_summary(cp)
        return

    started = time.time()
    last = [time.time()]
    done = [0]

    def _on_done(addr: BldgAddress, kind: str, n: int | None, err: Exception | None) -> None:
        done[0] += 1
        sk = f"stage2_{kind}"
        if err:
            cp.mark_error(sk, addr.key, str(err))
        else:
            cp.mark_done(sk, addr.key, n or 0)
        now = time.time()
        if now - last[0] >= 5.0 or done[0] == len(tasks):
            elapsed = now - started
            rate = done[0] / elapsed if elapsed else 0
            eta = (len(tasks) - done[0]) / rate if rate else 0
            err_txt = f" ERR={type(err).__name__}" if err else f" rows={n}"
            print(f"[stage2] {done[0]}/{len(tasks)} ({done[0]/len(tasks)*100:.1f}%) "
                  f"{addr.key}/{kind}{err_txt} | rate={rate:.1f}/s ETA={eta:.0f}s",
                  flush=True)
            last[0] = now

    with ThreadPoolExecutor(max_workers=BLDG_WORKERS) as ex:
        futs = {ex.submit(fetch_one, a, k, u): (a, k) for (a, k, u) in tasks}
        for fut in as_completed(futs):
            addr, kind = futs[fut]
            try:
                _, _, n = fut.result()
                _on_done(addr, kind, n, None)
            except Exception as e:
                _on_done(addr, kind, None, e)

    _print_summary(cp)


def _print_summary(cp: Checkpoint) -> None:
    for k in ("stage2_recap", "stage2_title", "stage2_expos"):
        s = cp.stage_summary(k)
        print(f"[stage2:{k}] done={s['done']} error={s['error']} rows={s['rows']:,}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.parse_args()
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
