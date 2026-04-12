"""
slug_utils.py — 단지/동 slug 생성 유틸 (단일 소스)

build_danji_pages.py, build_dong_pages.py, sync_trades.py에서 import하여 사용.
JS makeSlug와 100% 동기화된 정규식 사용.
"""

import re

REGION_MAP = {
    # 정식 명칭
    "서울특별시": "서울", "인천광역시": "인천", "부산광역시": "부산",
    "대구광역시": "대구", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
    # 약칭 (DB에 혼재)
    "서울": "서울", "인천": "인천", "부산": "부산", "대구": "대구",
    "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
    "경기": "경기", "강원": "강원", "충북": "충북", "충남": "충남",
    "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남",
    "제주": "제주",
}

METRO_CITIES = {"서울", "인천", "부산", "대구", "광주", "대전", "울산"}


def clean(s):
    r"""JS \w는 ASCII만 ([A-Za-z0-9_]) → JS _cl()과 100% 동기화"""
    s = re.sub(r'[^A-Za-z0-9_\uAC00-\uD7A3]', '-', s or "")
    return re.sub(r'-+', '-', s).strip('-')


def detect_region(address):
    """도로명주소에서 지역 약칭 반환"""
    if not address:
        return ""
    for full, short in REGION_MAP.items():
        if address.strip().startswith(full):
            return short
    return ""


def _parse_region_parts(address):
    """address에서 지역/구시 파트 추출 → slug_parts 리스트 반환"""
    addr_parts = (address or "").split()
    region = REGION_MAP.get(addr_parts[0], "") if addr_parts else ""
    parts = []
    if not region:
        return parts, region

    parts.append(region)
    if region in METRO_CITIES:
        if len(addr_parts) > 1 and (addr_parts[1].endswith("구") or addr_parts[1].endswith("군")):
            parts.append(re.sub(r'군$', '', addr_parts[1]) if addr_parts[1].endswith("군") else addr_parts[1])
    elif region == "세종":
        pass
    else:
        # 도: 시/군 + 구
        if len(addr_parts) > 1:
            parts.append(re.sub(r'(시|군)$', '', addr_parts[1]))
        if len(addr_parts) > 2 and addr_parts[2].endswith("구"):
            parts.append(addr_parts[2])

    return parts, region


def make_danji_slug(name, location, did, address=""):
    """단지 slug 생성
    광역시: 서울-강남구-도곡동-래미안도곡카운티-a13585404
    도:     경기-성남-분당구-정자동-아파트명-id
    """
    slug_parts, region = _parse_region_parts(address)

    if not region:
        loc_parts = (location or "").split(" ")
        if loc_parts and loc_parts[0]:
            slug_parts.append(clean(loc_parts[0]))

    # 동 추가 (location에서 구/시 제외한 나머지)
    loc_parts = (location or "").split(" ", 1)
    if len(loc_parts) >= 2:
        for d in loc_parts[1].split(" "):
            slug_parts.append(clean(d))

    # offi-/apt- 형태는 ID에 이미 단지명 포함
    did_lower = (did or "").lower()
    if did_lower and (did_lower.startswith("offi-") or did_lower.startswith("apt-")):
        slug_parts.append(did_lower)
    else:
        slug_parts.append(clean(name))
        slug_parts.append(did_lower)

    return "-".join([clean(p) for p in slug_parts if p])


def gu_url_slug(region_label, gu_name):
    """구 페이지 URL 슬러그 생성 — build_gu_pages.py의 gu_filename()과 동일 규칙.

    - 서울/경기: gu_name 그대로 (공백은 하이픈)
    - 인천: 기본 gu_name, 단 '중구'는 '인천-중구' (서울 중구와 충돌 방지)
    - 5대 광역시(부산/대구/광주/대전/울산): '{label}-{gu}' (이름 충돌 방지)
    """
    if not gu_name:
        return ""
    slug = gu_name.replace(" ", "-")
    metro = {"부산", "대구", "광주", "대전", "울산"}
    if region_label in metro:
        return f"{region_label}-{slug}"
    if region_label == "인천" and gu_name == "중구":
        return "인천-중구"
    return slug


def extract_gu_from_address(address, two_token_gu_set=None):
    """도로명주소에서 정확한 '구/시' 이름을 추출.

    - 서울/광역시: "서울특별시 강남구 ..." → "강남구"
    - 경기 2토큰: "경기도 수원시 장안구 ..." → "수원시 장안구" (2토큰 세트에 있을 때)
    - 경기 1토큰: "경기도 의정부시 ..." → "의정부시"
    - 추출 실패: "" 반환

    two_token_gu_set 미지정 시 regions.GYEONGGI_TWO_TOKEN_GU 를 기본값으로 사용.
    """
    if two_token_gu_set is None:
        try:
            from regions import GYEONGGI_TWO_TOKEN_GU
            two_token_gu_set = GYEONGGI_TWO_TOKEN_GU
        except ImportError:
            two_token_gu_set = None
    if not address:
        return ""
    addr_parts = address.split()
    if len(addr_parts) < 2:
        return ""
    # 첫 번째 토큰은 지역명(서울특별시/경기도 등), 두 번째부터 행정구역
    # words[1] 이 "구/군" → 광역시 형태
    if addr_parts[1].endswith("구") or addr_parts[1].endswith("군"):
        return addr_parts[1]
    # words[1] 이 "시" 이고 words[2] 가 "구" → 2토큰 gu 가능성
    if len(addr_parts) >= 3 and addr_parts[1].endswith("시") and addr_parts[2].endswith("구"):
        candidate = f"{addr_parts[1]} {addr_parts[2]}"
        # two_token_gu_set 이 주어지면 해당 세트에 있을 때만 2토큰으로 인정
        if two_token_gu_set is None or candidate in two_token_gu_set:
            return candidate
        return addr_parts[1]
    # 일반 시/군 (의정부시, 가평군 등)
    if addr_parts[1].endswith("시") or addr_parts[1].endswith("군"):
        return addr_parts[1]
    return ""


def make_dong_slug(gu, dong, address=""):
    """동 slug 생성: 서울-강남구-도곡동"""
    addr_parts = (address or "").split()
    region = REGION_MAP.get(addr_parts[0], "") if addr_parts else ""

    parts = []
    if region:
        parts.append(region)
        if region not in METRO_CITIES and region != "세종":
            # 도: 시/군 + 구
            if len(addr_parts) > 1:
                parts.append(re.sub(r'(시|군)$', '', addr_parts[1]))
            if len(addr_parts) > 2 and addr_parts[2].endswith("구"):
                parts.append(addr_parts[2])
        else:
            # 광역시/세종: 구/군 (군 suffix 제거)
            if gu.endswith("군"):
                parts.append(re.sub(r'군$', '', gu))
            else:
                parts.append(gu)
    else:
        parts.append(gu)

    # 동 추가
    for d in dong.split(" "):
        parts.append(d)

    slug = "-".join(parts)
    slug = re.sub(r'[^A-Za-z0-9_\uAC00-\uD7A3]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug
