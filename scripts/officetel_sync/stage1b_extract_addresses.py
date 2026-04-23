"""Stage 1b. 실거래 JSONL에서 주소 인벤토리 추출.

목적: Stage 2(건축물대장 수집) 입력 — 거래가 실제로 발생한 주소만 수집.
산출: COLLECT_ROOT/stage1b_addresses/addresses.jsonl

각 row:
  {sgg_cd, umd_nm, jibun, offi_nm, sample_apt_seq?,
   bun: '0719', ji: '0024',                       # 건축물대장 API 인자
   _bjdong_cd: '10100',                           # 카카오로 보강 필요
   trade_count: 12}                               # 거래 빈도
"""
from __future__ import annotations

import re
import sys
from collections import Counter

from .config import stage_dir
from .local_store import read_jsonl, write_jsonl


_JIBUN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _parse_bun_ji(jibun: str) -> tuple[str, str] | None:
    """'719-24' → ('0719', '0024'), '719' → ('0719', '0000')."""
    if not jibun:
        return None
    m = _JIBUN_RE.match(jibun.strip())
    if not m:
        return None
    bun = m.group(1).zfill(4)
    ji = (m.group(2) or "0").zfill(4)
    return bun, ji


def _normalize_name(name: str) -> str:
    """단지명 정규화 — 매칭용 (공백/특수문자 제거)."""
    return re.sub(r"[\s\u00a0]+", "", name or "").strip()


def collect_addresses() -> list[dict]:
    """sale, rent JSONL 디렉토리 전수 스캔."""
    counter: Counter = Counter()
    sample_offi: dict[tuple, str] = {}    # (sgg, umd, jibun) → 가장 흔한 offiNm

    bases = [stage_dir("stage1_trades/sale"), stage_dir("stage1_trades/rent")]
    total_files = 0
    total_rows = 0

    for base in bases:
        if not base.exists():
            continue
        for jsonl_path in base.glob("*.jsonl"):
            total_files += 1
            for r in read_jsonl(jsonl_path):
                total_rows += 1
                sgg = r.get("sggCd") or r.get("_sigungu_cd")
                umd = r.get("umdNm")
                jibun = r.get("jibun")
                offi = r.get("offiNm")
                if not (sgg and umd and jibun and offi):
                    continue
                key = (sgg.strip(), umd.strip(), jibun.strip(), _normalize_name(offi))
                counter[key] += 1
                if key not in sample_offi:
                    sample_offi[key] = offi.strip()

    print(f"[stage1b] 스캔 파일 {total_files}, 거래 row {total_rows:,}")
    print(f"[stage1b] 고유 (sgg+umd+jibun+offi) = {len(counter):,}")

    out: list[dict] = []
    skipped_jibun = 0
    for (sgg, umd, jibun, offi_norm), n in counter.most_common():
        bun_ji = _parse_bun_ji(jibun)
        if not bun_ji:
            skipped_jibun += 1
            continue
        bun, ji = bun_ji
        out.append({
            "sgg_cd": sgg,
            "umd_nm": umd,
            "jibun": jibun,
            "bun": bun,
            "ji": ji,
            "offi_nm": sample_offi[(sgg, umd, jibun, offi_norm)],
            "offi_nm_norm": offi_norm,
            "trade_count": n,
        })
    print(f"[stage1b] 지번 파싱 실패 skip: {skipped_jibun}")
    print(f"[stage1b] 최종 인벤토리: {len(out):,}")
    return out


def main() -> int:
    rows = collect_addresses()
    if not rows:
        print("[stage1b] 인벤토리가 비어있음. Stage 1 실거래 수집 먼저 실행", file=sys.stderr)
        return 1
    out_path = stage_dir("stage1b_addresses") / "addresses.jsonl"
    write_jsonl(out_path, rows, mode="w")
    print(f"[stage1b] 저장: {out_path}")

    # bjdongCd 매핑 → Stage 2에서 카카오로 보강
    return 0


if __name__ == "__main__":
    sys.exit(main())
