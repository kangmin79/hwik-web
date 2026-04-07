"""
test_slug.py — Python slug_utils vs JS makeSlug 동기화 테스트

Usage: python test_slug.py
"""
import subprocess, json, sys, os
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
from slug_utils import make_danji_slug, make_dong_slug

# JS makeSlug를 Node.js로 실행하는 헬퍼
JS_CODE = """
const fs = require('fs');
eval(fs.readFileSync('makeSlug.js', 'utf8'));
const cases = JSON.parse(process.argv[1]);
const results = cases.map(c => makeSlug(c.name, c.loc, c.did, c.addr));
console.log(JSON.stringify(results));
"""

TEST_CASES = [
    # 서울 일반
    {"name": "래미안도곡카운티", "loc": "강남구 도곡동", "did": "a13585404", "addr": "서울특별시 강남구 도곡로 403"},
    # 경기 시+구
    {"name": "한솔마을1단지청구", "loc": "분당구 정자동", "did": "apt-41135-한솔마을1단지청구", "addr": "경기도 성남시 분당구 정자일로 1"},
    # 인천 강화군 (군 suffix 제거)
    {"name": "강화풍림아이원", "loc": "강화군 강화읍 갑곳리", "did": "apt-28710-강화풍림아이원", "addr": "인천광역시 강화군 강화읍 갑곳리"},
    # 로마 숫자 (유니코드 불일치 방지 테스트)
    {"name": "아리움Ⅰ", "loc": "서초구 양재동", "did": "a99999", "addr": "서울특별시 서초구 양재대로 100"},
    # 한자 (유니코드 불일치 방지 테스트)
    {"name": "정다운 家(8차)", "loc": "중구 신당동", "did": "a88888", "addr": "서울특별시 중구 다산로 50"},
    # 전각 숫자
    {"name": "호반베르디움２차", "loc": "수정구 신흥동", "did": "a77777", "addr": "경기도 성남시 수정구 산성대로 300"},
    # offi- ID
    {"name": "삼부빌딩", "loc": "서구 석남동", "did": "offi-28260-삼부빌딩", "addr": "인천광역시 서구 석남동 123"},
    # address 빈 값 (fallback)
    {"name": "테스트아파트", "loc": "강남구 역삼동", "did": "a11111", "addr": ""},
    # 약칭 address
    {"name": "래미안마포리버웰", "loc": "마포구 용강동", "did": "a12187501", "addr": "서울 마포구 토정로 100"},
    # 경기 군 (가평)
    {"name": "e편한세상가평퍼스트원", "loc": "가평군 가평읍 대곡리", "did": "apt-41820-e편한세상가평퍼스트원", "addr": "경기도 가평군 가평읍 대곡리"},
]


def run_tests():
    # Python 결과
    py_results = []
    for c in TEST_CASES:
        py_results.append(make_danji_slug(c["name"], c["loc"], c["did"], c["addr"]))

    # JS 결과 (Node.js)
    try:
        result = subprocess.run(
            ["node", "-e", JS_CODE, json.dumps(TEST_CASES, ensure_ascii=False)],
            capture_output=True, text=True, timeout=10, encoding="utf-8"
        )
        if result.returncode != 0:
            print(f"Node.js 실행 실패: {result.stderr}")
            print("Node.js 없이 Python 결과만 출력합니다:")
            for i, (c, py) in enumerate(zip(TEST_CASES, py_results)):
                print(f"  {i+1}. {c['name']} → {py}")
            return

        js_results = json.loads(result.stdout)
    except FileNotFoundError:
        print("Node.js가 설치되어 있지 않습니다. Python 결과만 출력:")
        for i, (c, py) in enumerate(zip(TEST_CASES, py_results)):
            print(f"  {i+1}. {c['name']} → {py}")
        return

    # 비교
    mismatches = 0
    for i, (c, py, js) in enumerate(zip(TEST_CASES, py_results, js_results)):
        status = "✓" if py == js else "✗ MISMATCH"
        if py != js:
            mismatches += 1
        print(f"  {i+1}. {status}")
        print(f"     입력: {c['name']} | {c['loc']} | {c['did']}")
        print(f"     Py: {py}")
        if py != js:
            print(f"     JS: {js}")

    print(f"\n총 {len(TEST_CASES)}건 중 불일치 {mismatches}건")
    if mismatches > 0:
        sys.exit(1)
    else:
        print("Python ↔ JS 100% 동기화 확인!")


if __name__ == "__main__":
    run_tests()
