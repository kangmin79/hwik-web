# -*- coding: utf-8 -*-
"""
네이버 블로그 자동 포스팅
hwik_engine.py 생성 결과물 → 네이버 블로그 포스팅

구조:
  [상단] hwik_engine.py 자동생성 원고 (위치지도/실거래가/전문가의견)
  [중간] 중개사 업로드 사진 + Vision 자동 설명글
  [하단] 중개사 명함 + 네이버 지도

사용법:
  python naver_blog_post.py --apt "신내동 신내동성4차" --photos C:/사진폴더
  python naver_blog_post.py --apt "신내동 신내동성4차"  (사진 없이 상단 원고만)
"""

import os
import sys
import re
import time
import json
import base64
import requests
import argparse
import glob
import tempfile
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageEnhance
    PIL_OK = True
except ImportError:
    PIL_OK = False
    print("⚠️ PIL 없음 — pip install Pillow 설치 권장 (사진 보정 기능 비활성)")

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_HAIKU, anthropic_headers

# ── 중개사 정보 (로그인 시 blog_web.py에서 자동 주입됨) ──
# 직접 실행 시에는 아래 값을 채워서 사용
AGENT_INFO = {
    "name":          "",   # 담당자 이름
    "office":        "",   # 부동산명
    "phone":         "",   # 연락처
    "address":       "",   # 주소
    "naver_map_url": "",   # 네이버 지도 단축 URL
    "lat":           0.0,
    "lon":           0.0,
}

# ── 출력 기본 경로 ────────────────────────────────────────
OUTPUT_BASE = os.path.join(os.path.expanduser("~"), "Desktop", "원고")


# ========================================================
# docx 텍스트 추출
# ========================================================
def extract_docx_text(path):
    """docx 파일에서 순수 텍스트 추출"""
    try:
        from docx import Document
        doc = Document(path)
        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                lines.append(text)
        return "\n".join(lines)
    except Exception as e:
        print(f"  ⚠️ docx 읽기 오류 ({os.path.basename(path)}): {e}")
        return ""


# ========================================================
# 원고 폴더에서 필요한 파일 로드
# ========================================================
def load_output_dir(apt_name, output_base=None):
    """원고 폴더에서 이미지/텍스트 로드"""
    base = output_base or OUTPUT_BASE

    # 폴더 탐색 (단지명 일부 매칭)
    apt_clean = apt_name.replace(" ", "")
    candidates = []
    if os.path.exists(base):
        for d in os.listdir(base):
            if apt_clean in d.replace(" ", "") or d.replace(" ", "") in apt_clean:
                candidates.append(os.path.join(base, d))

    if not candidates:
        print(f"❌ 원고 폴더를 찾을 수 없습니다: {apt_name}")
        print(f"   경로: {base}")
        return None

    folder = candidates[0]
    print(f"📂 원고 폴더: {folder}")

    result = {
        "folder":   folder,
        "images":   {},
        "texts":    {},
        "apt_name": os.path.basename(folder),
    }

    # 이미지 로드
    for f in os.listdir(folder):
        fpath = os.path.join(folder, f)
        fl = f.lower()
        if "위치지도" in f:
            result["images"]["simple_map"] = fpath
        elif "매매가" in f and ("시세지도" in f or "라벨" in f):
            result["images"]["deal_label"] = fpath
        elif "전세가" in f and ("시세지도" in f or "라벨" in f):
            result["images"]["rent_label"] = fpath
        elif "실거래가" in f and ("추이" in f or "그래프" in f):
            result["images"]["chart"] = fpath

    # 텍스트 (docx) 로드
    docx_map = {
        "01_블로그제목":  "title",
        "02_아파트개요":  "overview",
        "03_매매카드":    "sale_card",
        "04_매매전문가":  "sale_expert",
        "05_전세카드":    "rent_card",
        "06_전세전문가":  "rent_expert",
        "07_월세카드":    "wolse_card",
        "08_학교정보":    "school",
        "09_종합의견":    "summary",
    }
    for f in os.listdir(folder):
        if not f.endswith(".docx"):
            continue
        fpath = os.path.join(folder, f)
        for key, label in docx_map.items():
            if key in f:
                result["texts"][label] = extract_docx_text(fpath)
                break

    print(f"  이미지: {list(result['images'].keys())}")
    print(f"  텍스트: {list(result['texts'].keys())}")
    return result


# ========================================================
# Claude Vision — 사진 분류 + 설명글 생성
# ========================================================
SPACE_ORDER = ["외관", "거실", "주방", "방", "욕실", "다용도실", "기타"]

def enhance_photo(src_path):
    """
    사진 살짝 보정 (밝기/대비/채도/선명도)
    보정된 임시 파일 경로 반환 — PIL 없으면 원본 경로 반환
    """
    if not PIL_OK:
        return src_path
    try:
        img = Image.open(src_path).convert("RGB")
        img = ImageEnhance.Brightness(img).enhance(1.08)   # 밝기 +8%
        img = ImageEnhance.Contrast(img).enhance(1.10)     # 대비 +10%
        img = ImageEnhance.Color(img).enhance(1.12)        # 채도 +12%
        img = ImageEnhance.Sharpness(img).enhance(1.15)    # 선명도 +15%
        suffix = Path(src_path).suffix.lower() or ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        img.save(tmp.name, quality=92)
        img.close()
        return tmp.name
    except Exception as e:
        print(f"  ⚠️ 사진 보정 실패 ({Path(src_path).name}): {e}")
        return src_path


def analyze_photos_with_vision(photo_paths, apt_name):
    """
    사진들을 Vision으로 분류 + 설명글 생성
    반환: [{"path": ..., "space": ..., "caption": ...}, ...]
    """
    if not photo_paths:
        return []

    print(f"\n🔍 Vision 사진 분석 중 ({len(photo_paths)}장)...")

    # 사진 보정 + 리사이즈 후 base64 변환
    images_b64 = []
    enhanced_paths = []
    for path in photo_paths:
        try:
            enhanced = enhance_photo(path)
            enhanced_paths.append(enhanced)
            # Vision API용 리사이즈 (긴 변 1200px 이하로)
            if PIL_OK:
                try:
                    img = Image.open(enhanced)
                    w, h = img.size
                    max_side = 1200
                    if max(w, h) > max_side:
                        ratio = max_side / max(w, h)
                        img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
                        tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        img.save(tmp2.name, "JPEG", quality=85)
                        enhanced = tmp2.name
                except Exception:
                    pass
            with open(enhanced, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = Path(path).suffix.lower()
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
            images_b64.append({"path": enhanced, "b64": b64, "mime": mime})
            print(f"  📷 {Path(path).name} ({len(data)//1024}KB)")
        except Exception as e:
            print(f"  ⚠️ 이미지 로드 실패: {path} — {e}")

    if not images_b64:
        return []

    def _analyze_one(img_data, apt_name, is_first):
        """사진 1장 Vision 분석"""
        first_hint = f" '{apt_name}'을 이 사진 설명에 자연스럽게 1회 포함." if is_first else ""
        content = [
            {"type": "image", "source": {"type": "base64",
             "media_type": img_data["mime"], "data": img_data["b64"]}},
            {"type": "text", "text": f"""이 사진은 아파트/오피스텔 매물 사진입니다.{first_hint}

아래 JSON 형식으로만 답하세요. 다른 텍스트 없이 JSON만:
{{
  "space": "외관|거실|주방|방|욕실|다용도실|기타 중 하나",
  "caption": "공인중개사가 직접 방문해서 쓰는 블로그 스타일 2~3문장. 사진 안에서 100% 확실하게 보이는 것만 묘사. 창밖 뷰 풍경 절대 언급 금지. 애매하면 쓰지 말 것. 추측 표현 금지. 특수문자 이모지 기호 사용 금지. 색상은 반드시 한글로만 표기(베이지 아이보리 등). 매번 다른 시작 어구와 문체를 사용하고 정형화된 표현을 피할 것. 짧고 자연스럽게."
}}"""}
        ]
        for attempt in range(3):
            try:
                res = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=anthropic_headers(),
                    json={"model": ANTHROPIC_MODEL_HAIKU,
                          "max_tokens": 500,
                          "messages": [{"role": "user", "content": content}]},
                    timeout=60
                )
                if res.status_code in (502, 529):
                    time.sleep(3); continue
                if res.status_code != 200:
                    return {"space": "기타", "caption": ""}
                text = res.json()["content"][0]["text"].strip()
                if "```" in text:
                    text = text.split("```")[1].replace("json","").strip()
                parsed = json.loads(text)
                caption = parsed.get("caption", "")
                # 특수문자/이모지 제거
                caption = re.sub(r'[◆◇▶▷●○■□★☆♦♣♠♥•·※†‡]', '', caption)
                caption = re.sub(r'[^\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F\w\s.,!?~\'"()%/·\-]', '', caption)
                caption = caption.strip()
                return {"space": parsed.get("space","기타"), "caption": caption}
            except Exception as e:
                if attempt < 2: time.sleep(2)
        return {"space": "기타", "caption": ""}

    # 사진별 병렬 분석 (최대 3장 동시 — API rate limit 고려)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _analyze_wrapper(i, img):
        print(f"  🔍 사진{i+1}/{len(images_b64)} 분석 중...")
        r = _analyze_one(img, apt_name, is_first=(i==0))
        print(f"     → {r['space']}: {r['caption'][:50]}...")
        return i, {"path": img["path"], "space": r["space"], "caption": r["caption"]}

    results = [None] * len(images_b64)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_analyze_wrapper, i, img)
                   for i, img in enumerate(images_b64)]
        for f in as_completed(futures):
            try:
                idx, result = f.result()
                results[idx] = result
            except Exception as e:
                print(f"  ⚠️ 사진 분석 오류: {e}")

    results = [r for r in results if r is not None]

    # 공간 순서로 정렬
    def sort_key(r):
        space = r["space"]
        return SPACE_ORDER.index(space) if space in SPACE_ORDER else 99
    results.sort(key=sort_key)
    print(f"  ✅ 분류 완료: {[r['space'] for r in results]}")

    # ── 2차: 전체 흐름 다듬기 (자연스러운 연결) ──
    if len(results) >= 2:
        results = _refine_captions_flow(results, apt_name)

    return results


def _refine_captions_flow(results, apt_name):
    """
    개별 캡션들을 전체적으로 다듬어서 자연스러운 흐름으로 만듦.
    중개사가 직접 블로그에 쓴 것처럼.
    """
    caption_list = []
    for i, r in enumerate(results):
        caption_list.append(f"{i+1}. [{r['space']}] {r['caption']}")
    captions_text = "\n".join(caption_list)

    prompt = f"""아래는 '{apt_name}' 매물 사진 {len(results)}장의 설명글입니다.
이 글들을 공인중개사가 직접 매물을 방문해서 블로그에 올리는 글처럼 다듬어주세요.

규칙:
- 각 사진 설명은 반드시 2~3문장 유지 (더 길게 쓰지 말 것)
- 사진 순서대로 자연스럽게 이어지도록 (집에 들어가는 흐름: 외관→현관→거실→주방→방→욕실)
- 첫 사진은 "직접 방문해봤는데" 같은 도입, 마지막은 가볍게 마무리
- 중간 사진들은 이전 공간에서 다음 공간으로 자연스럽게 연결
- 절대 과장하지 말 것. 있는 그대로만 묘사
- AI가 쓴 느낌 나는 표현 금지: "돋보입니다", "인상적입니다", "눈길을 끕니다", "특히", "무엇보다" 같은 표현 쓰지 말 것
- 특수문자, 이모지 사용 금지
- 말투: "~했어요", "~더라고요", "~있었어요" (자연스러운 구어체)

현재 설명:
{captions_text}

아래 JSON 배열로만 답하세요. 다른 텍스트 없이:
[
  "다듬은 1번 설명",
  "다듬은 2번 설명",
  ...
]"""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=anthropic_headers(),
            json={"model": ANTHROPIC_MODEL_HAIKU,
                  "max_tokens": 1500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60
        )
        if res.status_code != 200:
            print("  ⚠️ 흐름 다듬기 실패 (API 에러), 원본 유지")
            return results

        text = res.json()["content"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        refined = json.loads(text)

        if len(refined) == len(results):
            for i, caption in enumerate(refined):
                # 특수문자/이모지 제거
                caption = re.sub(r'[◆◇▶▷●○■□★☆♦♣♠♥•·※†‡]', '', caption)
                caption = re.sub(r'[^\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F\w\s.,!?~\'"()%/·\-]', '', caption)
                results[i]["caption"] = caption.strip()
            print("  ✅ 캡션 흐름 다듬기 완료")
        else:
            print(f"  ⚠️ 개수 불일치 ({len(refined)} vs {len(results)}), 원본 유지")
    except Exception as e:
        print(f"  ⚠️ 흐름 다듬기 실패: {e}, 원본 유지")

    return results


# ========================================================
# 네이버 지도 정적 이미지 URL 생성
# ========================================================
def get_naver_map_url(lat, lon, name):
    """네이버 정적 지도 URL (사무실 위치)"""
    return (
        f"https://simg.pstatic.net/static.map/v2/map/staticmap.bin"
        f"?caller=smarteditor"
        f"&markers=pos%3A{lon}%20{lat}%7CviewSizeRatio%3A0.7%7Ctype%3Ad%7Ccolor%3A0x11cc73%7Csize%3Amid"
        f"&w=700&h=315&scale=2"
    )


# ========================================================
# 블로그 포스팅 내용 조합
# ========================================================
def build_post_content(output_data, photo_results, agent_info):
    """
    포스팅 순서:
    제목 / 아파트개요 / 위치지도 / 매매카드 / 매매지도 / 매매전문가의견
    / 전세카드 / 전세지도 / 전세전문가의견 / 월세카드
    / 실거래가그래프 / 학교정보 / 종합의견
    / 중개사배너 / 중개사무실 네이버지도
    """
    apt_name = output_data["apt_name"]
    texts    = output_data["texts"]
    images   = output_data["images"]

    title = texts.get("title", f"{apt_name} 실거래가 시세")
    sections = []

    # ── 1. 아파트 개요 ────────────────────────────────────
    if texts.get("overview"):
        sections.append({"type": "text", "text": texts["overview"]})

    # ── 2. 위치지도 ───────────────────────────────────────
    if images.get("simple_map"):
        sections.append({"type": "image", "path": images["simple_map"],
                         "alt": f"{apt_name} 위치지도"})

    # ── 3. 매매카드 ───────────────────────────────────────
    if texts.get("sale_card"):
        sections.append({"type": "text", "text": texts["sale_card"]})

    # ── 4. 매매가 라벨지도 ────────────────────────────────
    if images.get("deal_label"):
        sections.append({"type": "image", "path": images["deal_label"],
                         "alt": f"{apt_name} 매매가 시세지도"})

    # ── 5. 매매 전문가 의견 ───────────────────────────────
    if texts.get("sale_expert"):
        sections.append({"type": "text", "text": texts["sale_expert"]})

    # ── 6. 전세카드 ───────────────────────────────────────
    if texts.get("rent_card"):
        sections.append({"type": "text", "text": texts["rent_card"]})

    # ── 7. 전세가 라벨지도 ────────────────────────────────
    if images.get("rent_label"):
        sections.append({"type": "image", "path": images["rent_label"],
                         "alt": f"{apt_name} 전세가 시세지도"})

    # ── 8. 전세 전문가 의견 ───────────────────────────────
    if texts.get("rent_expert"):
        sections.append({"type": "text", "text": texts["rent_expert"]})

    # ── 9. 월세카드 ───────────────────────────────────────
    if texts.get("wolse_card"):
        sections.append({"type": "text", "text": texts["wolse_card"]})

    # ── 10. 실거래가 그래프 ───────────────────────────────
    if images.get("chart"):
        sections.append({"type": "image", "path": images["chart"],
                         "alt": f"{apt_name} 실거래가 추이"})

    # ── 11. 학교 정보 ─────────────────────────────────────
    if texts.get("school"):
        sections.append({"type": "text", "text": texts["school"]})

    # ── 12. 종합 의견 ─────────────────────────────────────
    if texts.get("summary"):
        sections.append({"type": "text", "text": texts["summary"]})

    # ── 13. 중개사 매물 사진 (추가 이미지 있을 때) ─────────
    if photo_results:
        sections.append({
            "type": "text",
            "text": f"📸 {apt_name} 단지 사진도 준비했습니다."
        })
        for pr in photo_results:
            sections.append({"type": "image", "path": pr["path"],
                             "alt": f"{apt_name} {pr['space']}"})
            if pr.get("caption"):
                sections.append({"type": "text", "text": pr["caption"]})

    # ── 14. 중개사 배너 ───────────────────────────────────
    sections.append({"type": "divider", "text": "─" * 30})
    banner_text = (
        f"📍 {agent_info['office']}\n"
        f"👤 {agent_info['name']}\n"
        f"📞 {agent_info['phone']}\n"
        f"🏢 {agent_info['address']}"
    )
    sections.append({"type": "text", "text": banner_text})

    # ── 15. 중개사무실 네이버 지도 ────────────────────────
    map_url = get_naver_map_url(agent_info["lat"], agent_info["lon"], agent_info["office"])
    sections.append({"type": "map_image", "url": map_url,
                     "alt": f"{agent_info['office']} 위치"})

    # 공감/댓글 유도
    sections.append({
        "type": "text",
        "text": "\n─────────────────\n💗 유익했다면 공감 클릭!\n💬 궁금한 단지는 댓글로!\n다음 포스팅 주제 선정에 반영됩니다 ✨",
    })

    return {"title": title, "sections": sections}


# ========================================================
# 네이버 블로그 포스팅 (Selenium)
# ========================================================
def post_to_naver_blog(post_content, headless=False):
    """
    네이버 블로그에 포스팅
    Selenium Smart Editor 3 활용
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import pyperclip
    except ImportError:
        print("❌ selenium 또는 pyperclip 미설치")
        print("   pip install selenium pyperclip --break-system-packages")
        return False

    # ── 미리보기 출력 (실제 포스팅 전 확인) ─────────────
    print(f"\n{'='*50}")
    print(f"▶ 포스팅 미리보기")
    print(f"  제목: {post_content['title']}")
    print(f"  섹션: {len(post_content['sections'])}개")
    for s in post_content["sections"]:
        if s["type"] == "image":
            print(f"    🖼️  {os.path.basename(s['path'])}")
        elif s["type"] == "text":
            preview = s["text"][:40].replace("\n", " ")
            print(f"    📝  {preview}...")
        elif s["type"] == "map_image":
            print(f"    🗺️  네이버 지도")
    print(f"{'='*50}\n")

    confirm = input("위 내용으로 포스팅하시겠습니까? (y/n): ").strip().lower()
    if confirm != "y":
        print("포스팅 취소")
        return False

    print("🚀 네이버 블로그 포스팅 시작...")

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1280,900")

    driver = webdriver.Chrome(options=opts)
    wait   = WebDriverWait(driver, 20)

    try:
        # 1. 네이버 로그인 확인
        driver.get("https://www.naver.com")
        time.sleep(2)

        # 로그인 상태 확인
        try:
            driver.find_element(By.CSS_SELECTOR, ".MyView-module__link_login___HpHMW")
            print("  ⚠️ 네이버 로그인이 필요합니다")
            input("  로그인 후 엔터를 눌러주세요...")
        except:
            print("  ✅ 로그인 확인")

        # 2. 블로그 글쓰기 페이지
        driver.get("https://blog.naver.com/GoPost.naver?blogId=&categoryNo=0")
        time.sleep(3)

        # iframe 전환 (스마트에디터)
        wait.until(EC.frame_to_be_available_and_switch_to_it(
            (By.CSS_SELECTOR, "iframe#mainFrame")
        ))
        time.sleep(1)

        # 3. 제목 입력
        title_input = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".se-title-input")
        ))
        title_input.click()
        title_input.send_keys(post_content["title"])
        print(f"  ✅ 제목 입력: {post_content['title']}")
        time.sleep(0.5)

        # 4. 본문 클릭 (에디터 활성화)
        body = driver.find_element(By.CSS_SELECTOR, ".se-main-container")
        body.click()
        time.sleep(0.5)

        # 5. 섹션별 내용 입력
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)

        for i, section in enumerate(post_content["sections"]):
            stype = section["type"]

            if stype == "text" or stype == "divider":
                text = section.get("text", "")
                # 클립보드로 붙여넣기 (한글 깨짐 방지)
                pyperclip.copy(text)
                body.click()
                time.sleep(0.2)
                actions.key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
                time.sleep(0.3)
                body.send_keys(Keys.RETURN)

            elif stype in ("image", "map_image"):
                if stype == "image":
                    img_path = section["path"]
                    if not os.path.exists(img_path):
                        print(f"  ⚠️ 이미지 없음: {img_path}")
                        continue
                    _insert_image_selenium(driver, wait, img_path)
                else:
                    # 네이버 지도는 URL 이미지 삽입
                    _insert_image_url_selenium(driver, wait, section["url"])

                time.sleep(0.5)
                body.send_keys(Keys.RETURN)

            print(f"  [{i+1}/{len(post_content['sections'])}] {stype} 입력 완료")
            time.sleep(0.2)

        # 6. 발행
        print("\n  발행 버튼 클릭...")
        publish_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".publish_btn__QAh9y, .btn_publish")
        ))
        publish_btn.click()
        time.sleep(2)

        # 발행 확인 팝업
        try:
            confirm_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".confirm_btn, .btn_confirm")
            ))
            confirm_btn.click()
            time.sleep(3)
        except:
            pass

        print("  ✅ 포스팅 완료!")
        return True

    except Exception as e:
        print(f"  ❌ 포스팅 오류: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        time.sleep(2)
        driver.quit()


def _insert_image_selenium(driver, wait, img_path):
    """이미지 파일 삽입"""
    try:
        from selenium.webdriver.common.by import By
        # 이미지 버튼 클릭
        img_btn = driver.find_element(By.CSS_SELECTOR, 
            ".se-toolbar-item-imageUpload, [data-name='imageUpload']")
        img_btn.click()
        time.sleep(1)

        # 파일 선택
        file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
        file_input.send_keys(os.path.abspath(img_path))
        time.sleep(2)
    except Exception as e:
        print(f"    ⚠️ 이미지 삽입 오류: {e}")


def _insert_image_url_selenium(driver, wait, url):
    """URL 이미지 삽입 (네이버 지도)"""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        # 링크 이미지 삽입
        img_btn = driver.find_element(By.CSS_SELECTOR,
            ".se-toolbar-item-imageByUrl, [data-name='imageByUrl']")
        img_btn.click()
        time.sleep(1)

        url_input = driver.find_element(By.CSS_SELECTOR, ".se-image-url-input input")
        url_input.send_keys(url)
        url_input.send_keys(Keys.RETURN)
        time.sleep(2)
    except Exception as e:
        print(f"    ⚠️ URL 이미지 삽입 오류: {e}")


# ========================================================
# 메인
# ========================================================
def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 포스팅")
    parser.add_argument("--apt",     required=True, help="단지명 (예: '신내동 신내동성4차')")
    parser.add_argument("--photos",  default=None,  help="매물 사진 폴더 경로")
    parser.add_argument("--output",  default=None,  help="원고 폴더 경로 (기본: 바탕화면/원고)")
    parser.add_argument("--preview", action="store_true", help="미리보기만 (포스팅 안함)")
    args = parser.parse_args()

    print(f"{'='*50}")
    print(f"🔷 네이버 블로그 자동 포스팅")
    print(f"   단지: {args.apt}")
    print(f"{'='*50}\n")

    # 1. 원고 폴더 로드
    output_data = load_output_dir(args.apt, args.output)
    if not output_data:
        sys.exit(1)

    # 2. 매물 사진 Vision 분석
    photo_results = []
    if args.photos:
        photo_dir = args.photos
        if os.path.isdir(photo_dir):
            exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
            photo_paths = []
            for ext in exts:
                photo_paths.extend(glob.glob(os.path.join(photo_dir, ext)))
            photo_paths = sorted(photo_paths)[:15]  # 최대 15장
            print(f"📸 사진 {len(photo_paths)}장 발견")
            if photo_paths:
                photo_results = analyze_photos_with_vision(photo_paths, output_data["apt_name"])
        else:
            print(f"⚠️ 사진 폴더를 찾을 수 없습니다: {photo_dir}")

    # 3. 포스팅 내용 조합
    post_content = build_post_content(output_data, photo_results, AGENT_INFO)

    if args.preview:
        print("\n▶ 미리보기 모드")
        print(f"제목: {post_content['title']}")
        for s in post_content["sections"]:
            if s["type"] == "image":
                print(f"  🖼️  {os.path.basename(s['path'])}")
            elif s["type"] == "text":
                print(f"  📝  {s['text'][:60].replace(chr(10),' ')}...")
        return

    # 4. 포스팅
    post_to_naver_blog(post_content)

    input("\n종료하려면 엔터...")


if __name__ == "__main__":
    main()