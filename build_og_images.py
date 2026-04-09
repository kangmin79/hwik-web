#!/usr/bin/env python3
"""
build_og_images.py — 단지별 OG 이미지 자동 생성 (1200×630 PNG)

Supabase danji_pages → Playwright HTML→PNG → Supabase Storage 업로드
증분 빌드: og-manifest.json 해시 비교로 변경분만 재생성

Usage:
  python build_og_images.py          # 증분 빌드 (변경분만)
  python build_og_images.py --full   # 전체 재빌드
  python build_og_images.py --test   # 샘플 3개만 생성 (로컬 저장)
"""

import os, sys, json, hashlib, time
from urllib.parse import quote
import requests

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
DANJI_DIR = os.path.join(BASE_DIR, "danji")
MANIFEST_PATH = os.path.join(DANJI_DIR, "og-manifest.json")
STORAGE_BASE = f"{SUPABASE_URL}/storage/v1/object/og-images/danji"

CONCURRENCY = 8  # 동시 생성 수


# ── 유틸 함수 (build_danji_pages.py 와 동일) ──

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


def best_price_cat(d):
    """84㎡에 가장 가까운 거래 있는 면적 반환"""
    cats = d.get("categories") or []
    rt = d.get("recent_trade") or {}
    best, best_diff = None, 999
    for c in cats:
        if rt.get(c) and (rt[c].get("price") or 0) > 0:
            diff = abs(safe_int(c) - 84)
            if diff < best_diff:
                best_diff = diff
                best = c
    return best


def get_prop_type(did):
    return "오피스텔" if did.startswith("offi-") else "아파트"


# ── Supabase 조회 ──

def fetch_all_danji():
    all_data = []
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/danji_pages",
            headers={**SB_HEADERS, "Prefer": ""},
            params={
                "select": "id,complex_name,location,build_year,total_units,"
                          "categories,recent_trade,all_time_high,jeonse_rate,builder,updated_at",
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


# ── OG 데이터 추출 ──

def extract_og_data(d):
    """단지 레코드 → OG 이미지용 데이터 dict. 거래 없으면 None."""
    bc = best_price_cat(d)
    if not bc:
        return None

    rt = d.get("recent_trade") or {}
    sale = rt.get(bc) or {}
    jeonse = rt.get(f"{bc}_jeonse") or {}
    high = ((d.get("all_time_high") or {}).get(bc) or {})

    sale_price = sale.get("price")
    if not sale_price:
        return None

    area_int = safe_int(bc, 0)
    ppm = round(sale_price / area_int) if area_int > 0 else None

    # 최고가 대비 차이
    high_price = high.get("price")
    diff_text = ""
    if high_price and high_price > sale_price:
        gap = high_price - sale_price
        pct = round(gap / high_price * 100, 1)
        diff_text = f"최고 대비 -{format_price(gap)}({pct}%)"

    return {
        "id": d["id"],
        "name": d.get("complex_name", ""),
        "loc": d.get("location", ""),
        "units": d.get("total_units"),
        "year": d.get("build_year"),
        "builder": d.get("builder") or "",
        "prop_type": get_prop_type(d["id"]),
        "area": bc,
        "sale_price": format_price(sale_price),
        "sale_date": sale.get("date", ""),
        "sale_floor": sale.get("floor"),
        "jeonse_price": format_price(jeonse.get("price")) if jeonse.get("price") else None,
        "jeonse_date": jeonse.get("date", ""),
        "jeonse_floor": jeonse.get("floor"),
        "jeonse_rate": d.get("jeonse_rate"),
        "ppm": f"{ppm:,}만/㎡" if ppm else None,
        "diff_text": diff_text,
    }


# ── 해시 ──

def compute_data_hash(data):
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


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

def build_og_html(s):
    """OG 이미지용 HTML (1200×630)"""
    units_text = f"{s['units']:,}세대" if s.get("units") else ""
    year_text = f"{s['year']}년" if s.get("year") else ""
    builder_text = s.get("builder", "")

    sub_parts = [p for p in [s["loc"], units_text, year_text, builder_text] if p]
    sub_line = " · ".join(sub_parts)

    # 전세 카드 내용
    if s.get("jeonse_price"):
        jeonse_card = f"""
      <div class="card-label">최근 전세가</div>
      <div class="card-area">전용 {s['area']}㎡</div>
      <div class="card-value">{s['jeonse_price']}</div>
      <div class="card-detail">{s.get('jeonse_floor') or ''}층 · {s['jeonse_date']}</div>"""
    else:
        jeonse_card = f"""
      <div class="card-label">최근 전세가</div>
      <div class="card-area">전용 {s['area']}㎡</div>
      <div class="card-value empty">전세 거래 없음</div>"""

    # 전세가율
    jeonse_rate_text = f"{s['jeonse_rate']}%" if s.get("jeonse_rate") else "-"

    # ㎡당 매매가
    ppm_text = s.get("ppm") or "-"

    # 최고가 대비
    diff_html = f'<div class="card-diff">{s["diff_text"]}</div>' if s.get("diff_text") else ""

    # 층수 표시
    floor_text = f"{s['sale_floor']}층 · " if s.get("sale_floor") else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1200px; height:630px; font-family:'Noto Sans KR',sans-serif; background:#f8f8fa; overflow:hidden; }}

.header {{ background:#1a1a2e; padding:28px 48px 24px; }}
.header-top {{ display:flex; align-items:center; gap:14px; margin-bottom:10px; }}
.badge {{ background:#f5c842; color:#1a1a2e; font-weight:900; font-size:16px; padding:6px 16px; border-radius:8px; }}
.name {{ font-size:40px; font-weight:900; color:#fff; letter-spacing:-1px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:1000px; }}
.sub {{ font-size:15px; color:rgba(255,255,255,0.55); margin-top:2px; margin-left:62px; }}
.tabs {{ display:flex; align-items:center; gap:10px; margin-top:14px; }}
.tab {{ font-size:14px; font-weight:700; color:#fff; border-bottom:2px solid #f5c842; padding-bottom:2px; }}
.tab-dim {{ font-size:14px; color:rgba(255,255,255,0.35); }}
.accent-line {{ height:3px; background:linear-gradient(90deg, #6366f1, #f5c842); }}

.cards {{ display:flex; gap:20px; padding:24px 48px 0; }}
.card {{ border-radius:14px; padding:22px 26px; flex:1; }}
.card.primary {{ background:#ebf5ff; border:2px solid #4a90d9; flex:1.15; }}
.card.secondary {{ background:#f3f4f6; border:1px solid #e5e7eb; }}
.card-label {{ font-size:13px; color:#6b7280; margin-bottom:4px; font-weight:500; }}
.card-area {{ font-size:14px; color:#1a1a2e; font-weight:700; margin-bottom:6px; display:inline-block; background:#f5c842; padding:2px 10px; border-radius:12px; }}
.card-value {{ font-size:46px; font-weight:900; color:#1a1a2e; letter-spacing:-2px; line-height:1.15; }}
.card-value.empty {{ font-size:22px; color:#9ca3af; letter-spacing:0; margin-top:16px; }}
.card-detail {{ font-size:12px; color:#9ca3af; margin-top:8px; }}
.card-diff {{ font-size:14px; color:#e24b4a; font-weight:700; margin-top:4px; }}

.bottom-row {{ display:flex; gap:20px; margin:18px 48px 0; }}
.bottom-card {{ flex:1; background:#f3f4f6; border:1px solid #e5e7eb; border-radius:12px; padding:18px 24px; display:flex; align-items:center; justify-content:space-between; }}
.bottom-label {{ font-size:13px; color:#6b7280; font-weight:500; }}
.bottom-value {{ font-size:26px; font-weight:900; color:#1a1a2e; }}

.footer {{ position:absolute; bottom:0; left:0; right:0; padding:16px 48px; border-top:1px solid #e5e7eb; display:flex; justify-content:space-between; align-items:center; }}
.footer-source {{ font-size:12px; color:#9ca3af; }}
.footer-url {{ font-size:15px; font-weight:700; color:#6366f1; }}
</style></head>
<body>
  <div class="header">
    <div class="header-top">
      <span class="badge">휙</span>
      <span class="name">{s['name']}</span>
    </div>
    <div class="sub">{sub_line}</div>
    <div class="tabs">
      <span class="tab">매매</span>
      <span class="tab-dim">전세</span>
      <span class="tab-dim">월세</span>
    </div>
  </div>
  <div class="accent-line"></div>

  <div class="cards">
    <div class="card primary">
      <div class="card-label">최근 실거래가</div>
      <div class="card-area">전용 {s['area']}㎡</div>
      <div class="card-value">{s['sale_price']}</div>
      <div class="card-detail">{floor_text}{s['sale_date']}</div>
      {diff_html}
    </div>
    <div class="card secondary">
      {jeonse_card}
    </div>
  </div>

  <div class="bottom-row">
    <div class="bottom-card">
      <span class="bottom-label">전세가율</span>
      <span class="bottom-value">{jeonse_rate_text}</span>
    </div>
    <div class="bottom-card">
      <span class="bottom-label">㎡당 매매가</span>
      <span class="bottom-value">{ppm_text}</span>
    </div>
  </div>

  <div class="footer">
    <span class="footer-source">국토교통부 실거래가 · 매일 업데이트</span>
    <span class="footer-url">hwik.kr</span>
  </div>
</body></html>"""


# ── Supabase Storage 업로드 ──

def id_to_filename(danji_id):
    """ID → Storage 파일명 (MD5 해시, 한글 ID 호환)"""
    return hashlib.md5(danji_id.encode("utf-8")).hexdigest()


def upload_to_supabase(danji_id, png_bytes):
    fname = id_to_filename(danji_id)
    url = f"{STORAGE_BASE}/{fname}.png"
    resp = requests.post(url, headers={
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/png",
        "x-upsert": "true",
    }, data=png_bytes, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"  [!] 업로드 실패 {danji_id}: {resp.status_code} {resp.text[:200]}")
        return False
    return True


# ── Playwright 비동기 생성 ──

def generate_all(danji_list, manifest, full_rebuild=False, test_mode=False):
    """동기 방식 배치 생성 — 안정성 우선 (Playwright sync_api)"""
    from playwright.sync_api import sync_playwright

    to_generate = []
    for d in danji_list:
        og = extract_og_data(d)
        if not og:
            continue
        h = compute_data_hash(og)
        if not full_rebuild and manifest.get(og["id"]) == h:
            continue  # 변경 없음
        to_generate.append((og, h))

    total = len(to_generate)
    if total == 0:
        print("[OK] 변경된 단지 없음 -- OG 이미지 재생성 불필요")
        return manifest

    print(f"[*] OG 이미지 생성 시작: {total}개 {'(테스트 모드)' if test_mode else ''}")
    sys.stdout.flush()

    generated = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})

        for idx, (og_data, data_hash) in enumerate(to_generate):
            try:
                html = build_og_html(og_data)
                page.set_content(html)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(100)

                png = page.screenshot(
                    type="png",
                    clip={"x": 0, "y": 0, "width": 1200, "height": 630}
                )

                if test_mode:
                    out_path = os.path.join(BASE_DIR, f"og_test_{og_data['id']}.png")
                    with open(out_path, "wb") as f:
                        f.write(png)
                    print(f"  [OK] {og_data['name']} -> {out_path}")
                else:
                    ok = upload_to_supabase(og_data["id"], png)
                    if ok:
                        manifest[og_data["id"]] = data_hash
                        generated += 1
                    else:
                        failed += 1
                        continue

                if generated % 100 == 0 and generated > 0:
                    print(f"  진행: {generated}/{total}")
                    sys.stdout.flush()
                    # 주기적 매니페스트 저장 (크래시 대비)
                    if not test_mode:
                        save_manifest(manifest)

            except Exception as e:
                print(f"  [!] 생성 실패 {og_data.get('name', '?')}: {e}")
                failed += 1
                # 페이지 재생성 (에러 복구)
                try:
                    page.close()
                except Exception:
                    pass
                page = browser.new_page(viewport={"width": 1200, "height": 630})

        page.close()
        browser.close()

    print(f"[OK] OG 이미지 완료: 생성 {generated}개, 실패 {failed}개")
    return manifest


# ── 메인 ──

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    full_rebuild = mode == "--full"
    test_mode = mode == "--test"

    print("[*] 단지 데이터 조회 중...")
    danji_list = fetch_all_danji()
    print(f"  {len(danji_list)}개 단지 로드 완료")

    if test_mode:
        # 테스트 모드: 처음 3개만
        danji_list = danji_list[:50]  # 50개 중 거래 있는 것 몇 개 뽑힘
        manifest = {}
        full_rebuild = True
    else:
        manifest = load_manifest()

    manifest = generate_all(danji_list, manifest, full_rebuild, test_mode)

    if not test_mode:
        save_manifest(manifest)
        print(f"[*] 매니페스트 저장: {len(manifest)}개 항목")


if __name__ == "__main__":
    main()
