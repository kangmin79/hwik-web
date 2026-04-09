#!/usr/bin/env python3
"""
build_og_images_dong.py — 동별 OG 이미지 자동 생성 (1200x630 PNG)

Supabase danji_pages → 동별 집계 → Playwright HTML→PNG → Supabase Storage 업로드
증분 빌드: dong/og-manifest-dong.json 해시 비교로 변경분만 재생성

Usage:
  python build_og_images_dong.py          # 증분 빌드 (변경분만)
  python build_og_images_dong.py --full   # 전체 재빌드
  python build_og_images_dong.py --test   # 샘플 3개만 로컬 저장
"""

import os, sys, json, hashlib, time, html as html_mod
from collections import defaultdict
import requests
from slug_utils import make_dong_slug

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)


# ── 환경 변수 로드 ──
def _load_env():
    for fname in (".env", "env"):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DONG_DIR = os.path.join(BASE_DIR, "dong")
MANIFEST_PATH = os.path.join(DONG_DIR, "og-manifest-dong.json")
STORAGE_BASE = f"{SUPABASE_URL}/storage/v1/object/og-images/dong"

MIN_DANJI_WITH_TRADE = 3  # build_dong_pages.py와 동일


# ── 유틸 함수 ──

def esc(s):
    return html_mod.escape(str(s)) if s else ""


def format_price(manwon):
    if not manwon:
        return "-"
    try:
        manwon = int(manwon)
    except (ValueError, TypeError):
        return "-"
    if manwon <= 0:
        return "-"
    uk = manwon // 10000
    rest = manwon % 10000
    if uk > 0 and rest > 0:
        cheon = rest // 1000
        return f"{uk}억 {cheon}천" if cheon > 0 else f"{uk}억 {rest:,}"
    if uk > 0:
        return f"{uk}억"
    return f"{manwon:,}만"


def safe_int(s, default=999):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def best_trade(d):
    """84㎡에 가장 가까운 거래 있는 면적의 최근 거래 반환"""
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(safe_int(c) - 84)
            if diff < best_diff:
                best_diff = diff
                best = c
    if not best:
        return None, None
    return best, rt[best]


# ── Supabase 조회 ──

def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,address,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,updated_at",
                "order": "id",
                "offset": offset,
                "limit": 500,
            },
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else []
        if not data:
            break
        all_data.extend(data)
        offset += 500
        if len(data) < 500:
            break
        time.sleep(0.2)
    return all_data


# ── 동별 집계 ──

def group_by_dong(danji_list):
    """단지 리스트 → {(gu, dong): [danji...]} 그룹화"""
    groups = defaultdict(list)
    for d in danji_list:
        loc = d.get("location", "")
        parts = loc.split(" ", 1)
        if len(parts) < 2:
            continue
        gu = parts[0]
        dong = parts[1]
        groups[(gu, dong)].append(d)
    return groups


def extract_dong_og_data(gu, dong, danji_list):
    """동 그룹 → OG 이미지용 데이터. 거래 단지 3개 미만이면 None."""
    tradeable = []
    for d in danji_list:
        area, trade = best_trade(d)
        if area and trade:
            tradeable.append({
                "name": d.get("complex_name", ""),
                "area": area,
                "price": trade.get("price", 0),
            })

    if len(tradeable) < MIN_DANJI_WITH_TRADE:
        return None

    tradeable.sort(key=lambda x: x["price"], reverse=True)
    top3 = tradeable[:3]

    prices = [t["price"] for t in tradeable if t["price"] > 0]
    price_min = min(prices) if prices else 0
    price_max = max(prices) if prices else 0

    first_addr = danji_list[0].get("address", "") if danji_list else ""
    slug = make_dong_slug(gu, dong, first_addr)

    return {
        "slug": slug,
        "gu": gu,
        "dong": dong,
        "danji_count": len(tradeable),
        "top3": top3,
        "price_min": price_min,
        "price_max": price_max,
    }


# ── 해시 ──

def compute_data_hash(data):
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


def slug_to_filename(slug):
    return hashlib.md5(slug.encode("utf-8")).hexdigest()


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)


# ── OG HTML 템플릿 ──

def build_dong_og_html(s):
    """동 OG 이미지용 HTML (1200x630)"""
    # TOP 3 단지 행
    top_rows = ""
    for i, t in enumerate(s["top3"]):
        rank_bg = "#f5c842" if i == 0 else "#e5e7eb"
        rank_color = "#1a1a2e" if i == 0 else "#6b7280"
        top_rows += f"""
    <div class="rank-row">
      <span class="rank-num" style="background:{rank_bg};color:{rank_color};">{i+1}</span>
      <span class="rank-name">{esc(t['name'])}</span>
      <span class="rank-area">전용 {t['area']}㎡</span>
      <span class="rank-price">{format_price(t['price'])}</span>
    </div>"""

    price_range = f"{format_price(s['price_min'])} ~ {format_price(s['price_max'])}"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1200px; height:630px; font-family:'Noto Sans KR',sans-serif; background:#f8f8fa; overflow:hidden; }}

.header {{ background:#1a1a2e; padding:28px 48px 24px; }}
.header-top {{ display:flex; align-items:center; gap:14px; margin-bottom:10px; }}
.badge {{ background:#f5c842; color:#1a1a2e; font-weight:900; font-size:16px; padding:6px 16px; border-radius:8px; }}
.title {{ font-size:36px; font-weight:900; color:#fff; letter-spacing:-1px; }}
.sub {{ font-size:15px; color:rgba(255,255,255,0.55); margin-top:2px; margin-left:62px; }}
.accent-line {{ height:3px; background:linear-gradient(90deg, #6366f1, #f5c842); }}

.ranking {{ padding:24px 48px 0; }}
.ranking-title {{ font-size:15px; font-weight:700; color:#6b7280; margin-bottom:14px; }}
.rank-row {{ display:flex; align-items:center; gap:14px; padding:14px 20px; background:#fff; border:1px solid #e5e7eb; border-radius:12px; margin-bottom:10px; }}
.rank-num {{ width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:15px; flex-shrink:0; }}
.rank-name {{ font-size:18px; font-weight:700; color:#1a1a2e; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.rank-area {{ font-size:13px; color:#6b7280; font-weight:500; flex-shrink:0; }}
.rank-price {{ font-size:22px; font-weight:900; color:#1a1a2e; flex-shrink:0; letter-spacing:-1px; }}

.bottom-row {{ display:flex; gap:20px; margin:18px 48px 0; }}
.bottom-card {{ flex:1; background:#f3f4f6; border:1px solid #e5e7eb; border-radius:12px; padding:18px 24px; display:flex; align-items:center; justify-content:space-between; }}
.bottom-label {{ font-size:13px; color:#6b7280; font-weight:500; }}
.bottom-value {{ font-size:22px; font-weight:900; color:#1a1a2e; }}

.footer {{ position:absolute; bottom:0; left:0; right:0; padding:16px 48px; border-top:1px solid #e5e7eb; display:flex; justify-content:space-between; align-items:center; }}
.footer-source {{ font-size:12px; color:#9ca3af; }}
.footer-url {{ font-size:15px; font-weight:700; color:#6366f1; }}
</style></head>
<body>
  <div class="header">
    <div class="header-top">
      <span class="badge">휙</span>
      <span class="title">{esc(s['gu'])} {esc(s['dong'])} 아파트 시세</span>
    </div>
    <div class="sub">{s['danji_count']}개 단지 · 국토교통부 실거래가 · 매매가 높은 순</div>
  </div>
  <div class="accent-line"></div>

  <div class="ranking">
    <div class="ranking-title">매매가 TOP 3</div>
    {top_rows}
  </div>

  <div class="bottom-row">
    <div class="bottom-card">
      <span class="bottom-label">가격 분포</span>
      <span class="bottom-value">{price_range}</span>
    </div>
    <div class="bottom-card">
      <span class="bottom-label">거래 단지 수</span>
      <span class="bottom-value">{s['danji_count']}개</span>
    </div>
  </div>

  <div class="footer">
    <span class="footer-source">국토교통부 실거래가 · 매일 업데이트</span>
    <span class="footer-url">hwik.kr</span>
  </div>
</body></html>"""


# ── Supabase Storage 업로드 ──

def upload_to_supabase(slug, png_bytes):
    fname = slug_to_filename(slug)
    url = f"{STORAGE_BASE}/{fname}.png"
    resp = requests.post(url, headers={
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/png",
        "x-upsert": "true",
    }, data=png_bytes, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"  [!] upload fail {slug}: {resp.status_code} {resp.text[:200]}")
        return False
    return True


# ── 동기 생성 ──

def generate_all(dong_og_list, manifest, full_rebuild=False, test_mode=False):
    from playwright.sync_api import sync_playwright

    to_generate = []
    for og in dong_og_list:
        h = compute_data_hash(og)
        if not full_rebuild and manifest.get(og["slug"]) == h:
            continue
        to_generate.append((og, h))

    total = len(to_generate)
    if total == 0:
        print("[OK] 변경된 동 없음 -- OG 이미지 재생성 불필요")
        return manifest

    print(f"[*] 동 OG 이미지 생성 시작: {total}개 {'(test)' if test_mode else ''}")
    sys.stdout.flush()

    generated = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})

        for idx, (og_data, data_hash) in enumerate(to_generate):
            try:
                html = build_dong_og_html(og_data)
                page.set_content(html)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(100)

                png = page.screenshot(
                    type="png",
                    clip={"x": 0, "y": 0, "width": 1200, "height": 630}
                )

                if test_mode:
                    out_path = os.path.join(BASE_DIR, f"og_dong_test_{og_data['slug']}.png")
                    with open(out_path, "wb") as f:
                        f.write(png)
                    print(f"  [OK] {og_data['gu']} {og_data['dong']} -> {out_path}")
                else:
                    ok = upload_to_supabase(og_data["slug"], png)
                    if ok:
                        manifest[og_data["slug"]] = data_hash
                        generated += 1
                    else:
                        failed += 1
                        continue

                if generated % 50 == 0 and generated > 0:
                    print(f"  진행: {generated}/{total}")
                    sys.stdout.flush()
                    if not test_mode:
                        save_manifest(manifest)

            except Exception as e:
                print(f"  [!] 생성 실패 {og_data.get('gu','')} {og_data.get('dong','')}: {e}")
                failed += 1
                try:
                    page.close()
                except Exception:
                    pass
                page = browser.new_page(viewport={"width": 1200, "height": 630})

        page.close()
        browser.close()

    print(f"[OK] 동 OG 이미지 완료: 생성 {generated}개, 실패 {failed}개")
    return manifest


# ── 메인 ──

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    full_rebuild = mode == "--full"
    test_mode = mode == "--test"

    print("[*] 단지 데이터 조회 중...")
    danji_list = fetch_all_danji()
    print(f"  {len(danji_list)}개 단지 로드 완료")

    groups = group_by_dong(danji_list)
    print(f"  {len(groups)}개 동 그룹")

    dong_og_list = []
    for (gu, dong), dlist in groups.items():
        og = extract_dong_og_data(gu, dong, dlist)
        if og:
            dong_og_list.append(og)
    print(f"  OG 대상: {len(dong_og_list)}개 동 (거래 단지 {MIN_DANJI_WITH_TRADE}개 이상)")

    if test_mode:
        dong_og_list = dong_og_list[:3]
        manifest = {}
        full_rebuild = True
    else:
        manifest = load_manifest()

    manifest = generate_all(dong_og_list, manifest, full_rebuild, test_mode)

    if not test_mode:
        save_manifest(manifest)
        print(f"[*] 매니페스트 저장: {len(manifest)}개 항목")


if __name__ == "__main__":
    main()
