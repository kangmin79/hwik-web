#!/bin/bash
# 5대 광역시 순차 시드 (upsert). 각 단계 실패해도 다음 진행.
set -u
cd "$(dirname "$0")"
mkdir -p logs

for sido in busan daegu gwangju daejeon ulsan; do
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') START $sido ====="
    python -u seed_apartments.py --sido $sido > logs/seed_${sido}.log 2>&1
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') DONE  $sido (exit=$?) ====="
done

echo "===== ALL SEED DONE ====="
