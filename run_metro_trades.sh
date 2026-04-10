#!/bin/bash
# 5대 광역시 실거래가 수집 + 집계 (초기 36개월)
set -u
cd "$(dirname "$0")"
mkdir -p logs

for sido in busan daegu gwangju daejeon ulsan; do
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') START trades $sido ====="
    python -u sync_trades.py --init --$sido > logs/trades_${sido}.log 2>&1
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') DONE  trades $sido (exit=$?) ====="
done

echo "===== ALL TRADES DONE ====="
