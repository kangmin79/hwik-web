#!/usr/bin/env python3
"""
build_all.py — SEO 정적 페이지 전체 빌드 (올바른 순서 보장)

순서가 중요한 이유:
  build_danji_pages.py 가 DONG_SLUGS/GU_SLUGS 를 파일 시스템에서 읽기 때문에
  dong/gu 페이지를 먼저 빌드해야 danji 페이지에 올바른 링크가 생긴다.
  sitemap 은 HTML 파일 목록 기반이므로 모든 빌드 후 마지막에 실행.

Usage:
  python build_all.py          # 전체 빌드 (DB 집계 포함)
  python build_all.py --no-db  # DB 집계(build_danji_from_v2) 생략, HTML만 재빌드
  python build_all.py --no-og  # OG 이미지 생성 생략 (빠른 빌드)
"""

import sys, subprocess, argparse

def run(cmd):
    print(f"\n{'='*60}")
    print(f"▶ {cmd}")
    print('='*60)
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n[FAIL] '{cmd}' 실패 (exit {result.returncode})")
        sys.exit(result.returncode)

def main():
    parser = argparse.ArgumentParser(description="SEO 정적 페이지 전체 빌드")
    parser.add_argument("--no-db", action="store_true", help="DB 집계 생략")
    parser.add_argument("--no-og", action="store_true", help="OG 이미지 생성 생략")
    args = parser.parse_args()

    # 1. DB 집계 (danji_pages 뷰 갱신)
    if not args.no_db:
        run("python build_danji_from_v2.py")

    # 2. dong/gu 페이지 먼저 빌드 (danji가 이 목록에 의존)
    run("python build_dong_pages.py")
    run("python build_gu_pages.py")

    # 3. danji 페이지 빌드 (DONG_SLUGS/GU_SLUGS 완비 후)
    run("python build_danji_pages.py")

    # 4. OG 이미지 (선택)
    if not args.no_og:
        run("python build_og_images.py")
        run("python build_og_images_dong.py")

    # 5. 랭킹
    run("python build_ranking_pages.py")

    # 6. sitemap — 모든 HTML 완성 후 마지막
    run("python sync_trades.py --sitemap-only")

    print("\n[OK] 전체 빌드 완료")

if __name__ == "__main__":
    main()
