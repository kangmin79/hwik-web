"""관련 검색어 섹션의 앵커 텍스트 다양성 검증 (footer-link 스팸 방지).

규칙:
  - 단일 앵커 텍스트가 전체의 80%를 초과하면 FAIL
  - 전체 unique 앵커 수 < 10 이면 WARN
  - 랜덤 300개 단지 샘플링
"""
import os, re, random, sys, io
from collections import Counter

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DANJI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danji")
SAMPLE_SIZE = 300
FAIL_RATIO = 0.80
WARN_UNIQUE = 10

def extract_anchors(html):
    """<nav aria-label="관련 검색어"> ... </nav> 블록에서 <a> 텍스트 추출"""
    m = re.search(r'<nav aria-label="관련 검색어"[^>]*>(.*?)</nav>', html, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    return re.findall(r'<a [^>]+>([^<]+)</a>', block)

def main():
    files = [f for f in os.listdir(DANJI_DIR) if f.endswith(".html")]
    if not files:
        print("ERROR: danji/ 비어있음")
        sys.exit(1)
    total = len(files)
    sample_n = min(SAMPLE_SIZE, total)
    random.seed(20260419)
    sample = random.sample(files, sample_n)

    counter = Counter()
    pages_with_nav = 0
    for fn in sample:
        with open(os.path.join(DANJI_DIR, fn), encoding="utf-8") as f:
            html = f.read()
        anchors = extract_anchors(html)
        if anchors:
            pages_with_nav += 1
        for a in anchors:
            counter[a.strip()] += 1

    total_anchors = sum(counter.values())
    unique_n = len(counter)
    print(f"샘플: {sample_n} / 전체 {total}")
    print(f"nav 블록 있는 페이지: {pages_with_nav}/{sample_n}")
    print(f"총 앵커 수: {total_anchors}")
    print(f"고유 앵커 텍스트: {unique_n}")
    print()
    print("상위 15개 앵커 분포:")
    top_ratio_fail = False
    for text, cnt in counter.most_common(15):
        ratio = cnt / total_anchors if total_anchors else 0
        flag = " ❌ FAIL" if ratio > FAIL_RATIO else ""
        print(f"  {cnt:>5} ({ratio*100:.1f}%) — {text}{flag}")
        if ratio > FAIL_RATIO:
            top_ratio_fail = True

    print()
    exit_code = 0
    if pages_with_nav < sample_n * 0.5:
        print(f"❌ FAIL: nav 블록이 샘플의 50% 미만 ({pages_with_nav}/{sample_n})")
        exit_code = 1
    if top_ratio_fail:
        print(f"❌ FAIL: 단일 앵커가 {FAIL_RATIO*100:.0f}% 초과 — footer-link 스팸 신호")
        exit_code = 1
    if unique_n < WARN_UNIQUE:
        print(f"⚠ WARN: 고유 앵커 {unique_n}개 — 다양성 부족 (최소 {WARN_UNIQUE}개 권장)")
    if exit_code == 0:
        print(f"✅ PASS: 앵커 다양성 건강 (단일 최대 {counter.most_common(1)[0][1]/total_anchors*100:.1f}%, 고유 {unique_n}개)")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
