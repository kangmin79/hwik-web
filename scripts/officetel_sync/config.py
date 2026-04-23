"""환경변수·상수 중앙화. 매직넘버 금지."""
import os
from datetime import datetime
from pathlib import Path

# ── Supabase ─────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_REST = f"{SUPABASE_URL}/rest/v1"

# 2026-04-23 사고: limit=10000 → Supabase 1000 클램프 → 첫 페이지만 처리
SUPABASE_REST_MAX_LIMIT = 1000
INSERT_BATCH_SIZE = 500

# ── 국토부 API ─────────────────────────────────────────────
GOV_SERVICE_KEY = os.environ.get("GOV_SERVICE_KEY", "")

MOLIT_TRADE_SALE = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"
MOLIT_TRADE_RENT = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent"
MOLIT_BLDG_RECAP = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo"
MOLIT_BLDG_TITLE = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
MOLIT_BLDG_EXPOS = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"

MOLIT_NUM_OF_ROWS = 1000
MOLIT_TIMEOUT_SEC = 15
MOLIT_MAX_RETRY = 3
MOLIT_PAGE_CAP = 3000                  # v6 파이프라인 기준 (2026-04-17 헬리오시티 잘림 사고 반영)

# 운영키 100만/일, 30 QPS 한도. 안전 마진 25 QPS.
MOLIT_GLOBAL_QPS = 25

# ── 카카오 ─────────────────────────────────────────────────
KAKAO_API_KEY = (os.environ.get("KAKAO_REST_API_KEY")
                 or os.environ.get("KAKAO_REST_KEY", ""))
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_GLOBAL_QPS = 50                  # 카카오 한도 내 안전 마진

# ── 행안부 좌표검색 API (카카오 address 한도 초과 대비) ──────────
JUSO_CONFIRM_KEY = os.environ.get("JUSO_CONFIRM_KEY", "")
JUSO_COORD_URL = "https://business.juso.go.kr/addrlink/addrCoordApi.do"
JUSO_GLOBAL_QPS = 3                    # E0007(다량요청) 빈발 → 보수적 하향
JUSO_WORKERS = 1

# ── 병렬 ──────────────────────────────────────────────────
TRADE_WORKERS = 28
BLDG_WORKERS = 28
KAKAO_WORKERS = 16
UPLOAD_WORKERS = 8

# ── 회로 차단기 ────────────────────────────────────────────
CIRCUIT_BREAKER_CONSEC_FAIL = 10       # 연속 실패 임계
CIRCUIT_BREAKER_COOL_SEC = 600         # 10분 대기 후 재개

# ── 10건 gate ────────────────────────────────────────────
MIN_TRADE_COUNT_5Y = 10
TRADE_WINDOW_YEARS = 5

# ── 검증 임계 ──────────────────────────────────────────────
UNMATCHED_TRADE_PCT_LIMIT = 0.01       # 1% 초과 → abort
ID_RECOVERY_PCT_LIMIT = 0.95           # 기존 id 회수율 95% 미달 → abort

# ── 시도 코드 (2자리, 시군구 매핑·로깅용) ──────────────────────
SIDO_CODES = {
    "11": "서울특별시", "26": "부산광역시", "27": "대구광역시",
    "28": "인천광역시", "29": "광주광역시", "30": "대전광역시",
    "31": "울산광역시", "36": "세종특별자치시", "41": "경기도",
    "43": "충청북도", "44": "충청남도", "46": "전라남도",
    "47": "경상북도", "48": "경상남도", "50": "제주특별자치도",
    "51": "강원특별자치도", "52": "전북특별자치도",
}

# ── 경로 ──────────────────────────────────────────────────
# REPO_ROOT/_backups 는 git 추적 안 함 (.gitignore 대상)
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = REPO_ROOT / "_backups" / "officetel"
LOG_DIR = REPO_ROOT / "logs" / "officetel_sync"

# 로컬 수집 작업 디렉토리. 환경변수 OFFI_COLLECT_ROOT 로 오버라이드.
COLLECT_ROOT = Path(os.environ.get(
    "OFFI_COLLECT_ROOT",
    f"c:/Users/강동욱/Desktop/officetel_collect_{datetime.now().strftime('%Y%m%d')}",
))


def stage_dir(stage: str) -> Path:
    """Stage 별 출력 디렉토리. 없으면 생성."""
    p = COLLECT_ROOT / stage
    p.mkdir(parents=True, exist_ok=True)
    return p
