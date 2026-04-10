#!/bin/bash
# 5대 광역시 모든 시군구에 대해 sync_pyeongs 순차 실행
set -u
cd "$(dirname "$0")"
mkdir -p logs

# 부산
BUSAN="26110 26140 26170 26200 26230 26260 26290 26320 26350 26380 26410 26440 26470 26500 26530 26710"
# 대구
DAEGU="27110 27140 27170 27200 27230 27260 27290 27710 27720"
# 광주
GWANGJU="29110 29140 29155 29170 29200"
# 대전
DAEJEON="30110 30140 30170 30200 30230"
# 울산
ULSAN="31110 31140 31170 31200 31710"

ALL="$BUSAN $DAEGU $GWANGJU $DAEJEON $ULSAN"

for gu in $ALL; do
    echo "===== $(date '+%H:%M:%S') sync_pyeongs --gu $gu ====="
    python -u sync_pyeongs.py --gu $gu >> logs/sync_pyeongs_metro.log 2>&1
done

echo "===== ALL PYEONGS DONE ====="
