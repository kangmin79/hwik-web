#!/usr/bin/env python3
"""
auto_fix.py — 빌드 실패 시 Claude API로 자동 분석 및 수정

exit 0 = 수정 적용 완료
exit 2 = 수정 불가 (외부 장애, 네트워크 오류 등 코드 문제 아님)
exit 1 = 에러 (API 키 없음, 파싱 실패 등)
"""
import os, sys, json, re, argparse
from pathlib import Path

try:
    import requests
except ImportError:
    os.system("pip install requests -q")
    import requests

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

# 수정 허용 파일 (Python 빌드·수집 스크립트만)
# danji/app.js, danji/style.css, .github/workflows/ 는 절대 건드리지 않음
FIXABLE_FILES = {
    "build_danji_pages.py",
    "build_danji_from_v2.py",
    "build_dong_pages.py",
    "build_gu_pages.py",
    "build_ranking_pages.py",
    "collect_trades_v2.py",
    "sync_trades.py",
    "verify_browser.py",
    "verify_data.py",
    "verify_seo.py",
}

MAX_LOG   = 5000   # 로그 최대 글자
MAX_FILE  = 10000  # 파일 최대 글자 (앞뒤 각 5000)
STATUS_FILE = "/tmp/autofix_status.txt"


def call_claude(system: str, user: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def extract_files_from_log(log: str) -> list:
    """에러 로그에서 관련 Python 파일명 추출"""
    found = []
    # Python traceback에서 파일 경로 추출
    for m in re.finditer(r'File "([^"]+\.py)"', log):
        name = Path(m.group(1)).name
        if name in FIXABLE_FILES:
            found.append(name)
    # 직접 언급된 파일명
    for name in FIXABLE_FILES:
        if name in log and name not in found:
            found.append(name)
    return list(dict.fromkeys(found))[:3]  # 중복 제거, 최대 3개


def read_file(path: str) -> str:
    try:
        content = Path(path).read_text(encoding="utf-8")
        if len(content) > MAX_FILE:
            half = MAX_FILE // 2
            skipped = len(content) - MAX_FILE
            content = (
                content[:half]
                + f"\n\n... ({skipped:,}자 생략 — 중간 부분) ...\n\n"
                + content[-half:]
            )
        return content
    except Exception as e:
        return f"(읽기 실패: {e})"


def apply_fix(fix: dict) -> bool:
    fname = fix.get("file", "").strip()
    old   = fix.get("old", "")
    new   = fix.get("new", "")

    if not fname or not old or old == new:
        return False

    # 안전 장치: 허용 파일 목록 외 수정 차단
    if fname not in FIXABLE_FILES:
        print(f"  [차단] 허용 목록 외 파일: {fname}")
        return False

    p = Path(fname)
    if not p.exists():
        print(f"  [!] 파일 없음: {fname}")
        return False

    content = p.read_text(encoding="utf-8")
    if old not in content:
        print(f"  [!] 교체 대상 코드를 찾지 못함: {fname}")
        print(f"      찾으려 한 코드 (앞 80자): {repr(old[:80])}")
        return False

    p.write_text(content.replace(old, new, 1), encoding="utf-8")
    print(f"  ✅ 수정 완료: {fname}")
    return True


def collect_logs(extra_log: str) -> str:
    """여러 로그 파일 합치기"""
    log_paths = [
        extra_log,
        "/tmp/log_danji_v2.txt",
        "/tmp/log_danji_pages.txt",
        "/tmp/log_dong.txt",
        "/tmp/log_gu.txt",
        "/tmp/log_ranking.txt",
        "/tmp/log_sitemap.txt",
        "verify_result.txt",
    ]
    combined = ""
    for path in log_paths:
        try:
            c = Path(path).read_text(encoding="utf-8").strip()
            if c:
                combined += f"\n=== {path} ===\n{c}\n"
        except:
            pass
    return combined


def main():
    parser = argparse.ArgumentParser(description="빌드 실패 자동 수정")
    parser.add_argument("--log", default="/tmp/build_fail.txt", help="실패 로그 경로")
    args = parser.parse_args()

    if not ANTHROPIC_KEY:
        print("❌ ANTHROPIC_API_KEY 없음")
        sys.exit(1)

    # 1. 로그 수집
    log_text = collect_logs(args.log)
    if not log_text.strip():
        print("❌ 수집된 로그 없음")
        sys.exit(1)

    log_tail = log_text[-MAX_LOG:]

    # 2. 관련 파일 추출
    rel_files = extract_files_from_log(log_tail)
    if not rel_files:
        # 로그에서 힌트 없으면 집계·빌드 두 핵심 스크립트만
        rel_files = ["build_danji_from_v2.py", "build_danji_pages.py"]
    print(f"분석 대상: {rel_files}")

    file_section = ""
    for fname in rel_files:
        file_section += f"\n### {fname}\n```python\n{read_file(fname)}\n```\n"

    # 3. Claude 호출
    system = (
        "당신은 GitHub Actions 빌드 실패를 분석하고 Python 코드를 수정하는 에이전트입니다.\n"
        "수정 가능: Python 로직 오류(KeyError, AttributeError, IndexError), "
        "잘못된 쿼리 파라미터, import 오류, 파일 경로 문제.\n"
        "수정 불가: 외부 API 장애, 네트워크 타임아웃, DB 스키마 변경 필요, 원인 불명확.\n"
        "old/new 코드는 공백·들여쓰기를 원본과 정확히 일치시켜야 합니다.\n"
        "JSON만 반환하세요. 마크다운 코드블록(```) 없이."
    )

    user = (
        f"## 빌드 실패 로그\n```\n{log_tail}\n```\n\n"
        f"## 소스 파일\n{file_section}\n\n"
        "## 응답 형식\n"
        "수정 가능한 경우:\n"
        '{"fixable": true, "fixes": [{"file": "파일명.py", "old": "정확한 기존 코드", "new": "수정 코드"}]}\n\n'
        "수정 불가인 경우:\n"
        '{"fixable": false, "reason": "이유 한 줄"}'
    )

    print("Claude 분석 중...")
    try:
        raw = call_claude(system, user)
        raw = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        result = json.loads(raw)
    except Exception as e:
        print(f"❌ Claude 응답 파싱 실패: {e}")
        Path(STATUS_FILE).write_text("error:파싱실패", encoding="utf-8")
        sys.exit(1)

    # 4. 수정 불가
    if not result.get("fixable"):
        reason = result.get("reason", "원인 불명")
        print(f"🔍 수정 불가: {reason}")
        Path(STATUS_FILE).write_text(f"not_fixable:{reason}", encoding="utf-8")
        sys.exit(2)

    # 5. 수정 적용
    fixes = result.get("fixes", [])
    if not fixes:
        print("❌ fixes 배열 없음")
        Path(STATUS_FILE).write_text("error:fixes없음", encoding="utf-8")
        sys.exit(1)

    applied = sum(1 for f in fixes if apply_fix(f))
    if applied == 0:
        print("❌ 적용된 수정 없음 (코드 불일치)")
        Path(STATUS_FILE).write_text("error:코드불일치", encoding="utf-8")
        sys.exit(1)

    Path(STATUS_FILE).write_text(f"fixed:{applied}개", encoding="utf-8")
    print(f"✅ {applied}개 수정 완료")


if __name__ == "__main__":
    main()
