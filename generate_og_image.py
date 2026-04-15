"""
generate_og_image.py — og-image.png 재생성
"휙" 텍스트를 노란색(#facc15)으로 표시
"""
from playwright.sync_api import sync_playwright

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: #f1f2f6;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    gap: 24px;
  }
  .logo-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo-box {
    background: #facc15;
    border-radius: 10px;
    width: 52px; height: 52px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px; font-weight: 900; color: #1a1a2e;
  }
  .logo-text {
    font-size: 22px; color: #1a1a2e; font-weight: 500;
  }
  .main-text {
    text-align: center;
    font-size: 72px;
    font-weight: 900;
    color: #1a1a2e;
    line-height: 1.2;
  }
  .main-text .accent { color: #6366f1; }
  .main-text .yellow { color: #facc15; }
  .sub-text {
    font-size: 22px;
    color: #6b7280;
  }
  .tags {
    display: flex;
    gap: 12px;
    margin-top: 8px;
  }
  .tag {
    padding: 10px 20px;
    border-radius: 999px;
    font-size: 18px;
    font-weight: 500;
  }
  .tag-filled { background: #6366f1; color: white; }
  .tag-outline { border: 2px solid #d1d5db; color: #374151; background: white; }
</style>
</head>
<body>
  <div class="logo-row">
    <div class="logo-box">휙</div>
    <div class="logo-text">광고비 0원, AI 부동산</div>
  </div>
  <div class="main-text">
    아파트 <span class="accent">실거래가</span><br>
    이제 <span class="yellow">휙</span> 확인하세요
  </div>
  <div class="sub-text">국토교통부 공식 데이터 · 5년치 실거래 · 전국 아파트 단지</div>
  <div class="tags">
    <div class="tag tag-filled">매매·전세·월세</div>
    <div class="tag tag-outline">공급·전용면적</div>
    <div class="tag tag-outline">서울·수도권·5대 광역시</div>
    <div class="tag tag-outline">hwik.kr</div>
  </div>
</body>
</html>"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 630})
    page.set_content(HTML)
    page.wait_for_timeout(500)
    page.screenshot(path="og-image.png")
    browser.close()
    print("✅ og-image.png 생성 완료")
