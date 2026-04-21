"""
update_apartments_slug.py — apartments.slug 전수 재계산 (현재 make_slug 규칙으로 동기화)

목적:
  - DB.slug ≠ make_slug 런타임 결과 불일치 4,287건 정리
  - "구기동-구기동-청구빌라" 같은 과거 버그 규칙 잔재 삭제
  - apartments.slug = SSOT 진실로 고정 → 이후 slug_utils 동결 정책 적용

비파괴 실행:
  1. 현재 apartments 전체를 _backup_apartments_slug.json 으로 백업
  2. 각 행을 make_danji_slug(현재 규칙)로 재계산
  3. 변경 필요한 행만 UPDATE (불필요한 쓰기 최소화)
  4. dry-run 옵션 지원 (--dry-run)

실행:
  python update_apartments_slug.py --dry-run   # 변경 예정만 보고 종료
  python update_apartments_slug.py             # 실제 DB UPDATE
"""
from __future__ import annotations
import os, sys, json, argparse, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_trades import sb_session, SB_HEADERS, SUPABASE_URL, SUPABASE_URL_FALLBACK, SUPABASE_KEY
from slug_utils import make_danji_slug

ROOT = os.path.dirname(os.path.abspath(__file__))


def connect_db() -> str:
    for url in [SUPABASE_URL, SUPABASE_URL_FALLBACK]:
        try:
            r = sb_session.get(
                f"{url}/rest/v1/apartments?select=kapt_code&limit=1",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=15,
            )
            if r.status_code == 200:
                return url
        except Exception:
            pass
    print("❌ DB 연결 실패")
    sys.exit(1)


def load_all_apartments(url: str) -> list:
    all_apts, offset = [], 0
    while True:
        resp = sb_session.get(
            f"{url}/rest/v1/apartments",
            headers=SB_HEADERS,
            params={
                "select": "kapt_code,kapt_name,slug,sgg,umd_nm,doro_juso",
                "limit": "1000",
                "offset": str(offset),
                "order": "kapt_code",
            },
            timeout=60,
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        all_apts.extend(data)
        offset += 1000
        if len(data) < 1000:
            break
    return all_apts


def compute_new_slug(apt: dict) -> str:
    """apartments 레코드 하나에서 make_danji_slug 입력을 재구성해 slug 생성"""
    name = apt.get("kapt_name") or ""
    sgg = apt.get("sgg") or ""
    umd_nm = apt.get("umd_nm") or ""
    location = f"{sgg} {umd_nm}" if sgg else umd_nm
    # did = kapt_code 소문자 (빌드/라우팅과 동일 규칙)
    did = (apt.get("kapt_code") or "").lower()
    address = apt.get("doro_juso") or ""
    return make_danji_slug(name, location, did, address)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="변경 예정만 출력, DB 쓰기 안 함")
    args = parser.parse_args()

    url = connect_db()
    print(f"✅ DB {url}")

    print("📦 apartments 로드 중...")
    apts = load_all_apartments(url)
    print(f"  총 {len(apts):,}건")

    # 백업
    backup_path = os.path.join(ROOT, "_backup_apartments_slug.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(
            [{"kapt_code": a.get("kapt_code"), "slug": a.get("slug")} for a in apts],
            f, ensure_ascii=False, indent=None,
        )
    print(f"✅ 백업 저장: {backup_path}")

    # 재계산
    to_update = []
    unchanged = 0
    null_before = 0
    same_after = 0
    for a in apts:
        kc = a.get("kapt_code") or ""
        if not kc:
            continue
        new_slug = compute_new_slug(a)
        if not new_slug:
            continue
        old_slug = a.get("slug") or ""
        if old_slug == new_slug:
            same_after += 1
            continue
        if not old_slug:
            null_before += 1
        to_update.append((kc, old_slug, new_slug))

    print()
    print(f"📊 분석 결과")
    print(f"  이미 일치 (변경 불필요)   : {same_after:,}")
    print(f"  변경 필요                 : {len(to_update):,}")
    print(f"    중 slug가 null이던 건 : {null_before:,}")
    print()

    if to_update:
        print("🔍 변경 샘플 (상위 10건):")
        for kc, old, new in to_update[:10]:
            print(f"  {kc}  {old!r}")
            print(f"         → {new!r}")
        print()

    if args.dry_run:
        print("⏸ --dry-run 모드 — DB 쓰기 생략")
        return

    if not to_update:
        print("✅ 변경할 항목 없음")
        return

    # PATCH 방식 (개별 row UPDATE). PostgREST upsert는 INSERT 경로를 거쳐 NOT NULL 위반.
    # PATCH ?kapt_code=eq.XXX 는 UPDATE만 수행 → NOT NULL 컬럼 안 건드림.
    print(f"✏️  DB PATCH 시작 ({len(to_update):,}건, 20 workers 병렬)...")
    patch_headers = {
        **SB_HEADERS,
        "Prefer": "return=minimal",
    }

    def patch_one(kc: str, new_slug: str) -> tuple[str, int, str]:
        for attempt in range(3):
            try:
                resp = sb_session.patch(
                    f"{url}/rest/v1/apartments",
                    headers=patch_headers,
                    params={"kapt_code": f"eq.{kc}"},
                    json={"slug": new_slug},
                    timeout=30,
                )
                if resp.status_code in (200, 204):
                    return (kc, resp.status_code, "")
                if attempt < 2:
                    time.sleep(1)
                else:
                    return (kc, resp.status_code, resp.text[:200])
            except Exception as e:
                if attempt < 2:
                    time.sleep(1)
                else:
                    return (kc, -1, str(e)[:200])
        return (kc, -1, "unreachable")

    updated = 0
    failed = 0
    fail_samples: list[tuple[str, int, str]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(patch_one, kc, new): (kc, new) for kc, _, new in to_update}
        for i, fut in enumerate(as_completed(futures), 1):
            kc, code, err = fut.result()
            if code in (200, 204):
                updated += 1
            else:
                failed += 1
                if len(fail_samples) < 10:
                    fail_samples.append((kc, code, err))
            if i % 1000 == 0:
                elapsed = time.time() - t0
                print(f"  진행 {i:,}/{len(to_update):,} ({elapsed:.1f}s, 실패 {failed})")

    elapsed = time.time() - t0
    print()
    print(f"✅ 완료: {updated:,}건 UPDATE, 실패 {failed:,}건, 소요 {elapsed:.1f}s")
    if fail_samples:
        print("실패 샘플:")
        for kc, code, err in fail_samples:
            print(f"  {kc}  [{code}] {err}")


if __name__ == "__main__":
    main()
