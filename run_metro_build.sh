#!/bin/bash
# HTML 페이지 + OG 이미지 + sitemap 빌드
set -u
cd "$(dirname "$0")"
mkdir -p logs

echo "===== $(date '+%H:%M:%S') build_danji_pages ====="
python -u build_danji_pages.py > logs/build_danji.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') build_dong_pages ====="
python -u build_dong_pages.py > logs/build_dong.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') build_gu_pages ====="
python -u build_gu_pages.py > logs/build_gu.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') build_ranking_pages ====="
python -u build_ranking_pages.py > logs/build_ranking.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') build_og_images ====="
python -u build_og_images.py > logs/build_og.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') build_og_images_dong ====="
python -u build_og_images_dong.py > logs/build_og_dong.log 2>&1
echo "  exit=$?"

echo "===== $(date '+%H:%M:%S') sitemap ====="
python -u sync_trades.py --sitemap-only > logs/sitemap.log 2>&1
echo "  exit=$?"

echo "===== ALL BUILD DONE ====="
