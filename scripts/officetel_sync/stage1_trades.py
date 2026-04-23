"""Stage 1. 국토부 오피스텔 실거래 5년 전수 수집.

병렬: 28 worker, 전역 25 QPS.
저장: COLLECT_ROOT/stage1_trades/sale|rent/{sigunguCd}_{YYYYMM}.jsonl
체크포인트: stage='stage1_sale' 또는 'stage1_rent', key='{sigunguCd}_{YYYYMM}'
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .checkpoint import Checkpoint
from .config import (
    COLLECT_ROOT,
    MOLIT_TRADE_RENT,
    MOLIT_TRADE_SALE,
    TRADE_WINDOW_YEARS,
    TRADE_WORKERS,
    stage_dir,
)
from .fetch.molit_client import fetch_all_pages
from .local_store import write_jsonl


@dataclass(frozen=True)
class TradeJob:
    sigungu_cd: str
    deal_ym: str           # YYYYMM
    deal_type: str         # 'sale' | 'rent'

    @property
    def key(self) -> str:
        return f"{self.sigungu_cd}_{self.deal_ym}"

    @property
    def url(self) -> str:
        return MOLIT_TRADE_SALE if self.deal_type == "sale" else MOLIT_TRADE_RENT

    def out_path(self) -> Path:
        return stage_dir(f"stage1_trades/{self.deal_type}") / f"{self.key}.jsonl"


def generate_ym_range(months_back: int, today: date | None = None) -> list[str]:
    today = today or date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(months_back + 1):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def build_jobs(sigungu_codes: list[str], months_back: int) -> list[TradeJob]:
    yms = generate_ym_range(months_back)
    out = []
    for sgg in sigungu_codes:
        for ym in yms:
            out.append(TradeJob(sgg, ym, "sale"))
            out.append(TradeJob(sgg, ym, "rent"))
    return out


def fetch_one(job: TradeJob) -> tuple[TradeJob, int]:
    """국토부 호출 + JSONL 저장. 빈 응답도 빈 파일 생성 (재실행 건너뛰기)."""
    rows = fetch_all_pages(job.url, {"LAWD_CD": job.sigungu_cd, "DEAL_YMD": job.deal_ym})
    # 메타 부착
    for r in rows:
        r["_sigungu_cd"] = job.sigungu_cd
        r["_deal_ym"] = job.deal_ym
        r["_deal_type"] = job.deal_type
    write_jsonl(job.out_path(), rows, mode="w")
    return job, len(rows)


def run(sigungu_codes: list[str], *, months_back: int) -> None:
    cp = Checkpoint(COLLECT_ROOT / "checkpoint.db")
    jobs = build_jobs(sigungu_codes, months_back)
    print(f"[stage1] 전체 작업 {len(jobs)}건 (시군구 {len(sigungu_codes)} × {len(generate_ym_range(months_back))}개월 × 2 type)")

    pending = []
    for j in jobs:
        stage_key = f"stage1_{j.deal_type}"
        if cp.is_done(stage_key, j.key):
            continue
        pending.append(j)
    print(f"[stage1] 체크포인트 확인 → 대기 {len(pending)}건")

    if not pending:
        print("[stage1] 전부 완료 상태")
        _print_summary(cp)
        return

    started = time.time()
    last_progress = [time.time()]
    done = [0]

    def _on_done(job: TradeJob, n_rows: int | None, err: Exception | None) -> None:
        done[0] += 1
        stage_key = f"stage1_{job.deal_type}"
        if err:
            cp.mark_error(stage_key, job.key, str(err))
        else:
            cp.mark_done(stage_key, job.key, n_rows or 0)
        now = time.time()
        if now - last_progress[0] >= 5.0 or done[0] == len(pending):
            elapsed = now - started
            rate = done[0] / elapsed if elapsed else 0
            eta = (len(pending) - done[0]) / rate if rate else 0
            err_txt = f" ERR={type(err).__name__}" if err else f" rows={n_rows}"
            print(f"[stage1] {done[0]}/{len(pending)} ({done[0]/len(pending)*100:.1f}%) "
                  f"{job.key}/{job.deal_type}{err_txt} | rate={rate:.1f}/s ETA={eta:.0f}s",
                  flush=True)
            last_progress[0] = now

    with ThreadPoolExecutor(max_workers=TRADE_WORKERS) as ex:
        futs = {ex.submit(fetch_one, j): j for j in pending}
        for fut in as_completed(futs):
            job = futs[fut]
            try:
                _, n_rows = fut.result()
                _on_done(job, n_rows, None)
            except Exception as e:
                _on_done(job, None, e)

    _print_summary(cp)


def _print_summary(cp: Checkpoint) -> None:
    for st in ("stage1_sale", "stage1_rent"):
        s = cp.stage_summary(st)
        print(f"[stage1:{st}] done={s['done']} error={s['error']} rows={s['rows']:,}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--months-back", type=int, default=TRADE_WINDOW_YEARS * 12,
                   help="현재 달 포함 거꾸로 N개월 (default: 5년=60)")
    p.add_argument("--sigungu", nargs="*",
                   help="특정 시군구만 (디버깅). 미지정 시 전국 (인벤토리 파일 필요)")
    args = p.parse_args()

    if args.sigungu:
        sigungu = args.sigungu
    else:
        # stage0_inventory/sigungu.json 필요 (별도 단계에서 생성)
        from .local_store import read_json
        inv = read_json(COLLECT_ROOT / "stage0_inventory" / "sigungu.json")
        if not inv:
            print("[stage1] 인벤토리 없음. 먼저 stage0_inventory.py 실행", file=sys.stderr)
            return 1
        sigungu = inv

    run(sigungu, months_back=args.months_back)
    return 0


if __name__ == "__main__":
    sys.exit(main())
