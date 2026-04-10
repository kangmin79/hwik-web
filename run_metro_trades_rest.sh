#!/bin/bash
# 패치 이후: 대구 재집계 + 광주/대전/울산 초기수집
set -u
cd "$(dirname "$0")"
mkdir -p logs

echo "===== $(date '+%H:%M:%S') AGG daegu ====="
python -u sync_trades.py --aggregate-only --daegu > logs/trades_daegu_agg.log 2>&1
echo "  exit=$?"

for sido in gwangju daejeon ulsan; do
    echo "===== $(date '+%H:%M:%S') INIT $sido ====="
    python -u sync_trades.py --init --$sido > logs/trades_${sido}.log 2>&1
    echo "  exit=$?"
done

echo "===== ALL REST TRADES DONE ====="
