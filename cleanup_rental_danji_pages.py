# -*- coding: utf-8 -*-
"""
cleanup_rental_danji_pages.py — danji_pages 테이블에서 임대 단지 row 일괄 삭제 (one-shot)

판별 규칙 (sync_trades / build_danji_from_v2와 동일한 이중 방어):
  1) apartments.trade_type == '임대'
  2) apartments.kapt_name 또는 danji_pages.complex_name 에 '임대' 포함

실행:
  python cleanup_rental_danji_pages.py --dry     # 삭제 대상만 출력
  python cleanup_rental_danji_pages.py           # 실제 삭제
"""

import os, sys, argparse, time
import requests

for fname in (".env", "env"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SB_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SB_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SB_KEY:
    sys.exit("SUPABASE_SERVICE_ROLE_KEY 없음")

H = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}


def sb_get(table, params, limit=1000):
    rows, offset = [], 0
    while True:
        p = {**params, "limit": str(limit), "offset": str(offset)}
        r = requests.get(f"{SB_URL}/rest/v1/{table}", headers=H, params=p, timeout=30)
        if r.status_code != 200:
            print(f"  GET {table} {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        if not data:
            break
        rows.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="삭제 대상만 출력")
    args = parser.parse_args()

    print("1) apartments.trade_type='임대' 로드")
    apt_rental = sb_get("apartments", {
        "select": "kapt_code,kapt_name",
        "trade_type": "eq.임대",
    })
    rental_kapt = {(r.get("kapt_code") or "").lower() for r in apt_rental if r.get("kapt_code")}
    print(f"   apartments 임대: {len(rental_kapt):,}건")

    print("2) apartments.kapt_name LIKE '%임대%' 로드 (이중 방어)")
    apt_name_rental = sb_get("apartments", {
        "select": "kapt_code,kapt_name",
        "kapt_name": "ilike.*임대*",
    })
    name_kapt = {(r.get("kapt_code") or "").lower() for r in apt_name_rental if r.get("kapt_code")}
    print(f"   이름 임대: {len(name_kapt):,}건")

    print("3) danji_pages 로드")
    pages = sb_get("danji_pages", {"select": "id,complex_name"})
    print(f"   danji_pages 전체: {len(pages):,}건")

    targets = []
    for p in pages:
        pid = (p.get("id") or "").lower()
        name = p.get("complex_name") or ""
        if pid in rental_kapt or pid in name_kapt or "임대" in name:
            targets.append(p)

    print(f"\n삭제 대상: {len(targets):,}건")
    for t in targets[:10]:
        print(f"  - {t['id']} / {t['complex_name']}")
    if len(targets) > 10:
        print(f"  ... (+{len(targets)-10}건)")

    if args.dry:
        print("\n[DRY] 실제 삭제 안 함")
        return

    if not targets:
        print("삭제할 row 없음")
        return

    print(f"\n실제 삭제 진행...")
    deleted, failed = 0, 0
    for t in targets:
        pid = t["id"]
        r = requests.delete(
            f"{SB_URL}/rest/v1/danji_pages?id=eq.{pid}",
            headers=H, timeout=30,
        )
        if r.status_code in (200, 204):
            deleted += 1
        else:
            failed += 1
            print(f"  실패 {pid}: {r.status_code} {r.text[:200]}")
        if deleted % 50 == 0 and deleted:
            print(f"  진행: {deleted}/{len(targets)}")

    print(f"\n완료: {deleted:,}건 삭제 / {failed}건 실패")


if __name__ == "__main__":
    main()
