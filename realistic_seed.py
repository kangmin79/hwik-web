# -*- coding: utf-8 -*-
"""
휙 리얼리스틱 시드 데이터 생성
- 1단계: 기존 테스트 데이터 삭제
- 2단계: 5명 가상 중개사 × 30개 매물 = 150개
- 3단계: 내 계정 매물 100개
- 4단계: 공유방 3개 + 매물 공유
- 5단계: 손님 20명 + 타임라인 메모
"""
import os, sys, json, uuid, random, string, requests
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# .env 로드
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = "https://api.hwik.kr"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_SERVICE_KEY:
    print("SUPABASE_SERVICE_ROLE_KEY missing"); sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}
HEADERS_REP = {**HEADERS, "Prefer": "return=representation"}

MY_USER_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"

# ========== 데이터 풀 ==========

AGENTS = [
    {"business_name": "한강공인중개사", "name": "김영수", "phone": "010-1111-2222", "district": "마포구"},
    {"business_name": "미래부동산",     "name": "이지은", "phone": "010-3333-4444", "district": "강남구"},
    {"business_name": "열린공인중개사", "name": "박성호", "phone": "010-5555-6666", "district": "송파구"},
    {"business_name": "하나부동산",     "name": "최민지", "phone": "010-7777-8888", "district": "서초구"},
    {"business_name": "성원공인중개사", "name": "정태우", "phone": "010-9999-0000", "district": "용산구"},
]

MY_AGENT = {"business_name": "스마일부동산", "name": "스마일부동산", "phone": "010-4763-2531"}

DISTRICTS = {
    "마포구": ["공덕동","합정동","서교동","상수동","망원동","연남동","도화동","대흥동","성산동","상암동"],
    "강남구": ["역삼동","삼성동","대치동","논현동","신사동","청담동","압구정동","도곡동","개포동","일원동"],
    "송파구": ["잠실동","문정동","가락동","석촌동","방이동","풍납동","거여동","둔촌동"],
    "서초구": ["서초동","반포동","방배동","잠원동","양재동","내곡동"],
    "용산구": ["이태원동","한남동","이촌동","용산동","후암동","원효로"],
    "성동구": ["성수동","왕십리","행당동","금호동","옥수동"],
    "광진구": ["건대입구","구의동","자양동","화양동"],
    "영등포구": ["여의도동","당산동","문래동","양평동","신길동"],
    "강동구": ["천호동","둔촌동","강일동","암사동","고덕동"],
    "동작구": ["사당동","노량진동","상도동","흑석동"],
    "관악구": ["신림동","봉천동"],
    "종로구": ["종로","광화문","삼청동","혜화동"],
    "중구": ["명동","충무로","을지로","신당동"],
    "강서구": ["마곡동","화곡동","등촌동","발산동","가양동"],
    "양천구": ["목동","신월동","신정동"],
    "구로구": ["구로동","신도림동","개봉동"],
    "노원구": ["상계동","중계동","하계동","공릉동"],
    "서대문구": ["신촌동","연희동","홍은동"],
    "은평구": ["응암동","불광동","녹번동","수색동","진관동"],
    "중랑구": ["면목동","상봉동","망우동"],
    "도봉구": ["방학동","쌍문동","창동"],
    "동대문구": ["전농동","답십리","장안동","회기동","청량리"],
    "성북구": ["길음동","돈암동","정릉동","장위동"],
    "금천구": ["가산동","독산동","시흥동"],
    "강북구": ["미아동","번동","수유동"],
}

# 실제 서울 아파트 단지명
APT_COMPLEXES = {
    "마포구": ["래미안 푸르지오","마포 래미안","마포 자이","e편한세상 마포","DMC 래미안","마포 힐스테이트","마포 프레스티지","공덕 자이","DMC 파크뷰자이","마포 리버파크"],
    "강남구": ["아크로리버파크","대치 래미안","역삼 아이파크","타워팰리스","삼성 래미안","압구정 현대","도곡 렉슬","개포 자이","역삼 푸르지오","청담 자이"],
    "송파구": ["잠실 엘스","잠실 리센츠","잠실 트리지움","파크리오","헬리오시티","올림픽파크 포레온","잠실 레이크팰리스","잠실 주공5단지","가락 삼성래미안","석촌 푸르지오"],
    "서초구": ["반포 자이","래미안 퍼스티지","서초 힐스테이트","잠원 한신","방배 래미안","서초 푸르지오","반포 래미안","서초 자이","래미안 서초 에스티지","서초 롯데캐슬"],
    "용산구": ["용산 센트럴파크","한남 더힐","이촌 래미안","용산 파크타워","용산 푸르지오","한강로 자이","이촌 코오롱","용산 e편한세상","한남 리버힐","이태원 푸르지오"],
    "성동구": ["성수 자이","옥수 하이페리온","행당 한진","금호 두산위브","왕십리 텐즈힐","성수 래미안","옥수 래미안","금호 래미안","행당 래미안","성수 한신"],
    "영등포구": ["여의도 자이","여의도 시범","당산 래미안","영등포 푸르지오","여의도 한양","당산 자이","신길 래미안","여의도 리첸시아","영등포 롯데캐슬","당산 SK뷰"],
    "강동구": ["고덕 래미안","둔촌 자이","천호 래미안","암사 한강","강일 리버파크","고덕 자이","둔촌 래미안","천호 힐스테이트","강동 래미안","고덕 아이파크"],
    "동작구": ["래미안 에버리치","이수 힐스테이트","상도 자이","사당 래미안","노량진 래미안","사당 푸르지오","상도 래미안","대방 래미안","동작 자이","사당 자이"],
    "관악구": ["관악 드림타운","봉천 래미안","신림 푸르지오","관악 삼성","봉천 자이","신림 자이"],
    "노원구": ["중계 래미안","상계 주공","노원 롯데캐슬","하계 래미안","중계 아이파크","상계 래미안"],
    "강서구": ["마곡 힐스테이트","발산 래미안","화곡 푸르지오","마곡 자이","가양 래미안","등촌 자이"],
    "양천구": ["목동 신시가지","목동 래미안","신정 래미안","목동 자이","목동 힐스테이트"],
    "서대문구": ["서대문 래미안","연희 자이","신촌 힐스테이트","홍은 래미안","연희 래미안"],
    "은평구": ["은평 뉴타운 힐스테이트","응암 래미안","불광 롯데캐슬","녹번 래미안","진관 푸르지오"],
    "종로구": ["종로 래미안","경희궁자이","종로 자이","혜화 래미안"],
    "중구": ["신당 래미안","약수 하이페리온","을지로 센트럴","충무로 자이"],
    "구로구": ["구로 파크푸르지오","신도림 래미안","개봉 롯데캐슬","구로 래미안"],
    "중랑구": ["중랑 포레나","면목 래미안","상봉 자이","면목 힐스테이트"],
    "도봉구": ["창동 래미안","방학 자이","쌍문 래미안","도봉 힐스테이트"],
    "동대문구": ["한화꿈에그린","전농 래미안","답십리 래미안","청량리 자이"],
    "성북구": ["길음 래미안","돈암 자이","정릉 래미안","장위 푸르지오"],
    "금천구": ["가산 래미안","독산 자이","시흥 래미안"],
    "강북구": ["미아 래미안","수유 자이","번동 래미안"],
    "광진구": ["건대 스타시티","광진 자이","자양 래미안","구의 현대"],
}

OFFICETEL_NAMES = ["SK오피스텔","트라팰리스","메트로오피스텔","리버오피스텔","센트럴오피스텔",
    "스타오피스텔","프라임오피스텔","캐슬오피스텔","나루오피스텔","그린오피스텔",
    "더힐오피스텔","센트럴타워","골든타워","실버타워","블루타워"]
VILLA_NAMES = ["빌라","투룸빌라","원룸","투룸","쓰리룸","다세대","연립주택"]
COMMERCIAL_NAMES = ["1층 상가","코너상가","메인상가","점포","카페상가","음식점상가"]
OFFICE_NAMES = ["사무실","지식산업센터","업무용오피스","코워킹스페이스"]

SUBWAY_STATIONS = [
    "강남역","역삼역","삼성역","선릉역","교대역","서초역","잠실역","종합운동장역",
    "합정역","홍대입구역","상수역","망원역","공덕역","마포역","여의도역","당산역",
    "건대입구역","왕십리역","성수역","뚝섬역","이태원역","녹사평역","한남역",
    "신림역","사당역","노량진역","천호역","강동역","신도림역","구로디지털단지역",
    "상봉역","회기역","청량리역","답십리역","마곡역","발산역","목동역",
]

FEATURES_POOL = {
    "apartment": [
        ["남향","역세권","올수리","주차가능"],["동향","학군우수","베란다확장","주차2대"],
        ["남동향","신축","풀옵션","시스템에어컨"],["서향","리모델링","드레스룸","즉시입주"],
        ["정남향","한강뷰","고층","주차가능"],["남향","공원뷰","올수리","엘리베이터"],
        ["탁트인전망","시티뷰","풀옵션","주차2대"],["남향","초역세권","올수리","즉시입주"],
        ["더블역세권","학원가","주차가능","베란다확장"],["산뷰","정원","경비실","주차가능"],
    ],
    "officetel": [
        ["역세권","풀옵션","신축"],["빌트인","고층","주차가능"],
        ["초역세권","풀옵션","시스템에어컨"],["역세권","올수리","즉시입주"],
        ["신축","풀옵션","빌트인"],["더블역세권","주차가능","고층"],
    ],
    "room": [
        ["원룸","풀옵션","역세권"],["투룸","올수리","주차가능"],
        ["쓰리룸","올수리","베란다확장"],["원룸","신축","풀옵션"],
        ["투룸","역세권","애견가능"],["복층","루프탑","올수리"],
        ["투룸","풀옵션","즉시입주"],["원룸","역세권","즉시입주"],
    ],
    "commercial": [
        ["1층","대로변","역세권"],["1층","주차가능","대로변"],
        ["역세권","1층"],["대로변","코너","주차가능"],
    ],
    "office": [
        ["역세권","엘리베이터","주차가능"],["역세권","엘리베이터"],
        ["신축","주차가능","엘리베이터"],["역세권","엘리베이터","시티뷰"],
    ],
}

# ========== 헬퍼 함수 ==========

def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def random_date(days_back=30):
    return (datetime.now() - timedelta(days=random.randint(0, days_back), hours=random.randint(0,23), minutes=random.randint(0,59))).isoformat()

def gen_price(category, trade_type):
    """현실적인 가격 생성 (억 단위)"""
    if trade_type == "매매":
        prices = {
            "apartment": [3,4,5,6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,28,30,35,40,45,50],
            "officetel": [1.5,1.8,2,2.2,2.5,2.8,3,3.2,3.5,4,4.5,5],
            "room": [1.5,2,2.5,3,3.5,4,4.5,5],
            "commercial": [3,4,5,6,7,8,9,10,12,15,18,20],
            "office": [3,4,5,6,7,8,10,12],
        }
    elif trade_type == "전세":
        prices = {
            "apartment": [2,3,4,5,6,7,8,9,10,11,12,14,15,18],
            "officetel": [1,1.2,1.5,1.8,2,2.2,2.5,2.8,3,3.5],
            "room": [0.5,0.7,0.8,1,1.2,1.5,1.8,2,2.2,2.5,3],
            "commercial": [1,1.5,2,2.5,3,4,5],
            "office": [0.5,0.8,1,1.2,1.5,2,2.5,3],
        }
    else:
        return None  # 월세는 별도 처리
    return random.choice(prices.get(category, [1]))

def format_price(eok, trade_type, category):
    """가격을 문자열로 포맷"""
    if trade_type == "월세":
        deposit_ranges = {
            "apartment": ([3000,5000,7000,10000],[100,120,130,150,180,200,250]),
            "officetel": ([300,500,1000,1500,2000],[40,45,50,55,60,65,70,75,80,90,100,120]),
            "room": ([200,300,500,700,1000,1500],[30,35,40,45,50,55,60,65,70,80]),
            "commercial": ([2000,3000,5000,7000,10000],[100,120,150,180,200,250,300,400,500]),
            "office": ([1000,2000,3000,5000],[80,100,120,150,180,200,250,300]),
        }
        deposits, monthlys = deposit_ranges.get(category, ([1000],[50]))
        dep = random.choice(deposits)
        mon = random.choice(monthlys)
        return f"보증금{dep:,}/월{mon}", mon
    # 매매/전세
    if eok >= 1:
        base = int(eok)
        remainder = int(round((eok - base) * 10000))
        if remainder > 0:
            return f"{base}억 {remainder:,}", int(eok * 10000)
        return f"{base}억", int(eok * 10000)
    return f"{int(eok * 10000):,}만", int(eok * 10000)

def gen_area(category):
    areas = {
        "apartment": [18,20,22,24,25,27,28,29,30,32,33,34,35,38,40,42,45,50,59],
        "officetel": [6,7,8,9,10,11,12,13,14,15,16,18],
        "room": [4,5,6,7,8,9,10,11,12,13,14,15,16,18,20],
        "commercial": [8,10,12,15,18,20,25,30,35,40],
        "office": [8,10,12,15,18,20,25,30,35,40,50],
    }
    return f"{random.choice(areas.get(category, [20]))}평"

def gen_floor(category):
    if category == "apartment":
        dong = random.choice([101,102,103,104,105,106,107,108,109,110])
        floor = random.randint(2, 28)
        return f"{dong}동 {floor}층"
    if category == "commercial":
        return random.choice(["1층","지하1층","2층"])
    return f"{random.randint(2, 20)}층"

def gen_complex_name(category, gu, dong):
    dong_short = dong.replace("동","").replace("리","").replace("로","")
    if category == "apartment":
        pool = APT_COMPLEXES.get(gu, [f"{dong_short} 래미안", f"{dong_short} 자이", f"{dong_short} 힐스테이트"])
        return random.choice(pool)
    elif category == "officetel":
        return f"{dong_short} {random.choice(OFFICETEL_NAMES)}"
    elif category == "room":
        return f"{dong_short} {random.choice(VILLA_NAMES)}"
    elif category == "commercial":
        return f"{dong_short} {random.choice(COMMERCIAL_NAMES)}"
    else:
        return f"{dong_short} {random.choice(OFFICE_NAMES)}"

def gen_comment(category, trade_type, gu, dong, station):
    templates = {
        "apartment": [
            f"{station} 도보 {random.randint(2,10)}분, 실거주 추천 매물이에요.",
            f"{dong} 생활권, 학군 좋고 교통 편리합니다.",
            f"{gu} 인기 단지, {trade_type} 매물 나오면 금방 빠져요.",
            f"올수리 완료, 바로 입주 가능합니다. 깨끗해요.",
            f"로얄층 남향 매물이에요. {dong} 생활 인프라 최고.",
            f"{station} 초역세권, 출퇴근 편리한 매물이에요.",
            f"조용한 동네에 햇빛 잘 들어요. 주차도 여유.",
            f"이 가격에 이 컨디션 쉽게 안 나와요. 서두르세요.",
        ],
        "officetel": [
            f"{station} 초역세권, 직장인 최적 매물이에요.",
            f"{dong} 1인 가구 인기 오피스텔. 관리 잘 되어 있어요.",
            f"풀옵션이라 짐만 들어오면 됩니다. 즉시입주 가능.",
            f"신축이라 모든 게 새것이에요. 보안도 철저합니다.",
            f"{station} 도보 {random.randint(2,5)}분, 출퇴근 걱정 없어요.",
        ],
        "room": [
            f"{station} 인근 가성비 좋은 매물이에요.",
            f"{dong} 조용한 주택가, 깨끗하게 수리했어요.",
            f"대학생/사회초년생 추천합니다. 관리비 저렴해요.",
            f"올수리 완료, 깔끔한 매물이에요. 역세권이라 교통 편리.",
            f"주변에 편의시설 많고 치안도 좋아요.",
        ],
        "commercial": [
            f"{station} 유동인구 많은 1층 입지예요.",
            f"{dong} 상권, 모든 업종 가능합니다.",
            f"현재 임차인 있어 수익 안정적이에요.",
            f"대로변 코너 자리, 가시성 좋은 상가예요.",
            f"주변 상권 활성화 지역이에요. 투자가치 높아요.",
        ],
        "office": [
            f"{station} 인근, 교통 편리한 사무실이에요.",
            f"{dong} 업무지구, 기업 밀집 지역입니다.",
            f"소규모 스타트업에 적합한 사무실이에요.",
            f"엘리베이터, 주차 완비된 깔끔한 사무실.",
            f"IT기업 밀집지역, 인재 채용에도 유리한 입지.",
        ],
    }
    return random.choice(templates.get(category, [f"{gu} {dong} 좋은 매물입니다."]))

def gen_memo(category, trade_type):
    memos = [
        "집주인 010-XXXX-XXXX, 네고 가능성 있음",
        "즉시입주 가능, 임대인 협조적",
        "전세보험 가입 가능 확인 완료",
        "반려동물 소형 가능 (대형 불가)",
        "장기 계약 시 월세 5만원 할인 가능",
        "관리비 별도 15만원 (난방비 포함)",
        "주차 1대 포함, 추가 주차 월 10만원",
        "올수리 2024년, 보일러 교체 완료",
        "융자 없음, 깨끗한 매물",
        "매도인 급매 의향, 네고 2천만원 가능",
        "현재 공실, 바로 계약 가능",
        "이전 세입자 깨끗하게 사용, 하자 없음",
        "집주인 해외 거주, 관리인 통해 연락",
        "보증보험 가입 필수 조건",
        "2년 이상 계약 희망",
        "입주 시 도배/장판 교체 가능",
        "층간소음 민원 이력 없음",
        "경비실 24시간 운영, 택배 보관 가능",
    ]
    return random.choice(memos)

def batch_insert(table, data, batch_size=50):
    """배치 INSERT, 성공 수 반환"""
    success = 0
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            json=batch
        )
        if resp.status_code in (200, 201):
            success += len(batch)
        else:
            print(f"  FAIL {table} batch {i}: {resp.status_code} {resp.text[:200]}")
    return success

def batch_delete(table, query_params):
    """조건부 DELETE"""
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{query_params}",
        headers=HEADERS
    )
    return resp.status_code in (200, 204)

# ========== 매물 생성 ==========

def make_card(category, trade_type, gu, agent_info):
    """매물 카드 1개 생성"""
    dongs = DISTRICTS.get(gu, [""])
    dong = random.choice(dongs)
    location = f"{gu} {dong}"
    complex_name = gen_complex_name(category, gu, dong)
    station = random.choice(SUBWAY_STATIONS)
    features = random.choice(FEATURES_POOL.get(category, [["역세권"]]))
    area = gen_area(category)
    floor = gen_floor(category)
    comment = gen_comment(category, trade_type, gu, dong, station)
    memo = gen_memo(category, trade_type)
    move_in = random.choice([None, None, "즉시입주", "입주협의", "2026년 4월", "2026년 5월", "2026년 6월"])

    if trade_type == "월세":
        price_str, price_number = format_price(None, "월세", category)
    else:
        eok = gen_price(category, trade_type)
        price_str, price_number = format_price(eok, trade_type, category)

    search_text = f"{trade_type} {price_str} {location} {complex_name} {area} {floor} {' '.join(features)}"

    color = "mint" if trade_type == "전세" else "coral" if trade_type == "매매" else "blue"

    return {
        "id": gen_id(),
        "agent_id": MY_USER_ID,
        "style": "memo",
        "color": color,
        "property": {
            "type": trade_type,
            "price": price_str,
            "location": location,
            "complex": complex_name,
            "area": area,
            "floor": floor,
            "features": features,
            "category": category,
            "moveIn": move_in,
        },
        "agent": {
            "name": agent_info["business_name"],
            "business_name": agent_info["business_name"],
            "phone": agent_info["phone"],
        },
        "private_note": {"memo": memo},
        "agent_comment": comment,
        "search_text": search_text,
        "price_number": price_number,
        "photos": None,
        "embedding": None,
        "trade_status": random.choices(["계약가능","계약중"], weights=[85,15])[0],
        "created_at": random_date(30),
    }

def generate_agent_cards(agent):
    """중개사 1명 기준 30개 매물 생성"""
    gu = agent["district"]
    cards = []
    # 아파트 10 (매매4, 전세4, 월세2)
    for _ in range(4): cards.append(make_card("apartment", "매매", gu, agent))
    for _ in range(4): cards.append(make_card("apartment", "전세", gu, agent))
    for _ in range(2): cards.append(make_card("apartment", "월세", gu, agent))
    # 오피스텔 6 (매매2, 전세2, 월세2)
    for _ in range(2): cards.append(make_card("officetel", "매매", gu, agent))
    for _ in range(2): cards.append(make_card("officetel", "전세", gu, agent))
    for _ in range(2): cards.append(make_card("officetel", "월세", gu, agent))
    # 원투룸/빌라 6 (전세3, 월세3)
    for _ in range(3): cards.append(make_card("room", "전세", gu, agent))
    for _ in range(3): cards.append(make_card("room", "월세", gu, agent))
    # 상가 4 (매매2, 월세2)
    for _ in range(2): cards.append(make_card("commercial", "매매", gu, agent))
    for _ in range(2): cards.append(make_card("commercial", "월세", gu, agent))
    # 사무실 4 (전세2, 월세2)
    for _ in range(2): cards.append(make_card("office", "전세", gu, agent))
    for _ in range(2): cards.append(make_card("office", "월세", gu, agent))
    return cards

def generate_my_cards():
    """내 계정 매물 100개 (서울 전 지역)"""
    all_gus = list(DISTRICTS.keys())
    cards = []
    # 아파트 30
    for _ in range(30):
        gu = random.choice(all_gus)
        tt = random.choice(["매매","매매","매매","전세","전세","전세","전세","월세","월세"])
        cards.append(make_card("apartment", tt, gu, MY_AGENT))
    # 오피스텔 20
    for _ in range(20):
        gu = random.choice(all_gus)
        tt = random.choice(["매매","전세","전세","월세","월세"])
        cards.append(make_card("officetel", tt, gu, MY_AGENT))
    # 원투룸 20
    for _ in range(20):
        gu = random.choice(all_gus)
        tt = random.choice(["전세","전세","월세","월세","월세"])
        cards.append(make_card("room", tt, gu, MY_AGENT))
    # 상가 15
    for _ in range(15):
        gu = random.choice(all_gus)
        tt = random.choice(["매매","매매","월세","월세","월세"])
        cards.append(make_card("commercial", tt, gu, MY_AGENT))
    # 사무실 15
    for _ in range(15):
        gu = random.choice(all_gus)
        tt = random.choice(["전세","전세","월세","월세","월세"])
        cards.append(make_card("office", tt, gu, MY_AGENT))
    return cards

# ========== 손님 생성 ==========

CLIENT_DATA = [
    {"name":"김서연","request":"마포구 전세 아파트 구합니다 예산 5억 이내 30평대 역세권 4월 입주","category":"apartment","trade_type":"전세","location":"마포구","price_number":50000,"features":["역세권","아파트"]},
    {"name":"박준혁","request":"강남 매매 아파트 찾습니다 20억~30억 40평대 한강뷰","category":"apartment","trade_type":"매매","location":"강남구","price_number":250000,"features":["한강뷰","아파트"]},
    {"name":"이하은","request":"송파구 잠실 전세 아파트 원해요 8억 이내 25평 이상 역세권","category":"apartment","trade_type":"전세","location":"송파구","price_number":80000,"features":["역세권","아파트"]},
    {"name":"정우진","request":"강남역 월세 오피스텔 보증금 1천 월세 80 이하 역세권 풀옵션","category":"officetel","trade_type":"월세","location":"강남구","price_number":80,"features":["역세권","풀옵션","오피스텔"]},
    {"name":"최수아","request":"홍대 전세 투룸 2억5천 이내 올수리 베란다확장","category":"room","trade_type":"전세","location":"마포구","price_number":25000,"features":["올수리","베란다확장"]},
    {"name":"강민준","request":"서초 반포 매매 아파트 35억 예산 50평대 한강뷰","category":"apartment","trade_type":"매매","location":"서초구","price_number":350000,"features":["한강뷰","아파트"]},
    {"name":"윤지아","request":"합정역 월세 원룸 보증금 500 월세 45 이하 풀옵션 여성전용","category":"room","trade_type":"월세","location":"마포구","price_number":45,"features":["풀옵션","역세권"]},
    {"name":"임태현","request":"여의도 전세 오피스텔 3억 이내 15평 이상 직장인","category":"officetel","trade_type":"전세","location":"영등포구","price_number":30000,"features":["역세권","오피스텔"]},
    {"name":"한소희","request":"용산 이촌동 전세 아파트 10억 예산 한강뷰 30평대","category":"apartment","trade_type":"전세","location":"용산구","price_number":100000,"features":["한강뷰","아파트"]},
    {"name":"오준서","request":"성수동 월세 오피스텔 보증금 1천 월세 75 이하 신축","category":"officetel","trade_type":"월세","location":"성동구","price_number":75,"features":["신축","역세권"]},
    {"name":"배지민","request":"강남 대로변 1층 상가 보증금 1억 월세 500 이하 프랜차이즈","category":"commercial","trade_type":"월세","location":"강남구","price_number":500,"features":["1층","대로변","역세권"]},
    {"name":"신하영","request":"테헤란로 사무실 30평 보증금 5천 월세 300 이하 IT스타트업","category":"office","trade_type":"월세","location":"강남구","price_number":300,"features":["역세권","엘리베이터"]},
    {"name":"구본재","request":"노원구 전세 아파트 3억 이내 20평대 신혼부부","category":"apartment","trade_type":"전세","location":"노원구","price_number":30000,"features":["역세권"]},
    {"name":"문채원","request":"양천구 목동 매매 아파트 14억 이내 학군 중요 32평","category":"apartment","trade_type":"매매","location":"양천구","price_number":140000,"features":["학군우수"]},
    {"name":"장도윤","request":"건대입구 전세 투룸 2억 이내 역세권 올수리","category":"room","trade_type":"전세","location":"광진구","price_number":20000,"features":["역세권","올수리"]},
    {"name":"송예린","request":"홍대 1층 상가 보증금 5천 월세 200 이하 카페 창업","category":"commercial","trade_type":"월세","location":"마포구","price_number":200,"features":["1층","역세권"]},
    {"name":"황민석","request":"강남 매매 오피스텔 3억 이내 수익률 5% 이상 역세권","category":"officetel","trade_type":"매매","location":"강남구","price_number":30000,"features":["역세권","수익형"]},
    {"name":"권나은","request":"사당역 전세 아파트 4억 이내 역세권 직장인","category":"apartment","trade_type":"전세","location":"동작구","price_number":40000,"features":["역세권"]},
    {"name":"조현우","request":"마포 합정 사무실 10평 보증금 1천 월세 80 이하 디자인회사","category":"office","trade_type":"월세","location":"마포구","price_number":80,"features":["역세권"]},
    {"name":"유서진","request":"잠실 월세 아파트 보증금 5천 월세 150 이하 30평대","category":"apartment","trade_type":"월세","location":"송파구","price_number":150,"features":["역세권","아파트"]},
]

# 손님별 타임라인 메모 템플릿
def gen_client_notes(client_card_id, client_data, idx):
    """손님 1명에 대해 3~5개 메모 생성"""
    notes = []
    name = client_data["name"]
    trade = client_data["trade_type"]
    cat_kr = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}.get(client_data["category"],"매물")
    loc = client_data["location"]

    # 1) 첫 상담 메모 (10~20일 전)
    first_days = random.randint(10, 20)
    first_date = datetime.now() - timedelta(days=first_days)
    first_templates = [
        f"{name} 손님 첫 상담. {loc} {trade} {cat_kr} 찾고 계심. 예산 확인 완료.",
        f"{name} 손님 전화 상담. {loc} 근처 {trade} {cat_kr} 희망. 다음주 매물 보내드리기로.",
        f"{name} 손님 카톡 문의. {trade} {cat_kr} 조건 정리 완료. 매물 리스트 준비 중.",
        f"지인 소개로 {name} 손님 연결. {loc} {trade} {cat_kr} 조건. 급하진 않다고 하심.",
    ]
    notes.append({
        "client_card_id": client_card_id,
        "agent_id": MY_USER_ID,
        "type": "상담",
        "content": random.choice(first_templates),
        "created_at": first_date.isoformat(),
    })

    # 2) 매물 소개 메모 (5~10일 전)
    second_days = random.randint(5, 9)
    second_date = datetime.now() - timedelta(days=second_days)
    second_templates = [
        f"{name} 손님께 {loc} {cat_kr} 매물 3건 카톡으로 보내드림. 반응 좋음.",
        f"매물 리스트 5건 전송 완료. {name} 손님 2건 관심 표시.",
        f"{name} 손님 매물 확인 후 전화 옴. 가격 네고 가능한지 확인 요청.",
        f"카톡으로 매물 사진/정보 전달. {name} 손님 주말 방문 의사 있음.",
    ]
    notes.append({
        "client_card_id": client_card_id,
        "agent_id": MY_USER_ID,
        "type": "매물소개",
        "content": random.choice(second_templates),
        "created_at": second_date.isoformat(),
    })

    # 3) 방문/통화 메모 (2~5일 전)
    third_days = random.randint(2, 4)
    third_date = datetime.now() - timedelta(days=third_days)
    third_templates = [
        f"{name} 손님 {loc} 매물 현장 방문. 첫 번째 매물 마음에 들어하심.",
        f"{name} 손님과 통화. 가격 조건 재확인. 계약 의향 있으나 고민 중.",
        f"현장 방문 2건 완료. {name} 손님 두 번째 매물 관심. 집주인 연락 예정.",
        f"{name} 손님 방문 완료. 컨디션 좋다고 하심. 주말에 가족과 재방문 예정.",
    ]
    notes.append({
        "client_card_id": client_card_id,
        "agent_id": MY_USER_ID,
        "type": "방문",
        "content": random.choice(third_templates),
        "created_at": third_date.isoformat(),
    })

    # 4) 일부 손님: 알림 메모 (날짜 있는 메모)
    if idx % 3 == 0:
        alert_days = random.randint(1, 14)
        alert_date = (datetime.now() + timedelta(days=alert_days)).strftime("%Y-%m-%d")
        alert_templates = [
            f"{name} 손님 {alert_date} 방문 예정. 매물 2건 준비해두기.",
            f"계약 상담 예정 ({alert_date}). {name} 손님 서류 안내 필요.",
            f"{name} 손님 {alert_date} 재방문 약속. 집주인과 시간 조율.",
        ]
        notes.append({
            "client_card_id": client_card_id,
            "agent_id": MY_USER_ID,
            "type": "일정",
            "content": random.choice(alert_templates),
            "alert_date": alert_date,
            "alert_done": False,
            "created_at": (datetime.now() - timedelta(days=1)).isoformat(),
        })

    # 5) 일부 손님: 완료된 알림
    if idx % 5 == 0:
        past_alert = (datetime.now() - timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d")
        notes.append({
            "client_card_id": client_card_id,
            "agent_id": MY_USER_ID,
            "type": "일정",
            "content": f"{name} 손님 {past_alert} 방문 완료. 매물 2건 확인.",
            "alert_date": past_alert,
            "alert_done": True,
            "created_at": (datetime.now() - timedelta(days=random.randint(3, 7))).isoformat(),
        })

    # 6) 일부: 추가 메모
    if idx % 2 == 0:
        extra_date = datetime.now() - timedelta(days=random.randint(1, 3))
        extra_templates = [
            f"{name} 손님 추가 요청: 주차 2대 가능한 곳 선호.",
            f"가격 네고 진행 중. 집주인 500만원 조정 가능 회신.",
            f"{name} 손님 조건 변경: 평수 좀 더 넓은 곳도 괜찮다고 하심.",
            f"전세보험 가입 가능 여부 확인 요청. 내일 답변 드리기로.",
            f"{name} 손님 계약 서류 준비 안내 완료. 등기부등본 확인 필요.",
        ]
        notes.append({
            "client_card_id": client_card_id,
            "agent_id": MY_USER_ID,
            "type": "메모",
            "content": random.choice(extra_templates),
            "created_at": extra_date.isoformat(),
        })

    return notes


# ========== 메인 ==========

def main():
    print("=" * 60)
    print("REALISTIC SEED DATA GENERATOR")
    print("=" * 60)

    # ===== 1단계: 기존 데이터 삭제 =====
    print("\n[1단계] 기존 테스트 데이터 삭제")

    tables_to_clear = [
        ("client_notes", "agent_id=eq." + MY_USER_ID),
        ("card_shares", "shared_by=eq." + MY_USER_ID),
        ("share_room_members", "member_id=eq." + MY_USER_ID),
        ("share_rooms", "owner_id=eq." + MY_USER_ID),
        ("search_logs", "agent_id=eq." + MY_USER_ID),
        ("match_notifications", "agent_id=eq." + MY_USER_ID),
        ("cards", "agent_id=eq." + MY_USER_ID),
    ]

    for table, query in tables_to_clear:
        ok = batch_delete(table, query)
        status = "OK" if ok else "SKIP/FAIL"
        print(f"  {table}: {status}")

    # ===== 2단계: 5명 가상 중개사 × 30개 매물 = 150개 =====
    print("\n[2단계] 가상 중개사 5명 × 30개 매물 = 150개")

    agent_cards = {}  # agent_idx -> [card_ids]
    all_agent_cards = []

    for idx, agent in enumerate(AGENTS):
        cards = generate_agent_cards(agent)
        card_ids = [c["id"] for c in cards]
        agent_cards[idx] = card_ids
        all_agent_cards.extend(cards)
        print(f"  {agent['business_name']} ({agent['district']}): {len(cards)}개 생성")

    count = batch_insert("cards", all_agent_cards)
    print(f"  => DB 저장: {count}/{len(all_agent_cards)}")

    # ===== 3단계: 내 계정 매물 100개 =====
    print("\n[3단계] 내 계정(스마일부동산) 매물 100개")

    my_cards = generate_my_cards()
    my_card_ids = [c["id"] for c in my_cards]
    count = batch_insert("cards", my_cards)
    print(f"  => DB 저장: {count}/{len(my_cards)}")

    # ===== 4단계: 공유방 3개 + 매물 공유 =====
    print("\n[4단계] 공유방 3개 생성 + 매물 공유")

    share_rooms_data = [
        {"name": "마포 매물공유방", "agent_idx": 0},
        {"name": "강남 매물공유방", "agent_idx": 1},
        {"name": "송파 매물공유방", "agent_idx": 2},
    ]

    for sr in share_rooms_data:
        room_id = str(uuid.uuid4())
        agent_idx = sr["agent_idx"]

        # 공유방 생성
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/share_rooms", headers=HEADERS, json={
            "id": room_id, "name": sr["name"], "owner_id": MY_USER_ID
        })
        if resp.status_code not in (200, 201):
            print(f"  공유방 생성 실패 ({sr['name']}): {resp.status_code} {resp.text[:100]}")
            continue

        # 방장 등록
        requests.post(f"{SUPABASE_URL}/rest/v1/share_room_members", headers=HEADERS, json={
            "room_id": room_id, "member_id": MY_USER_ID, "invited_phone": "01047632531",
            "status": "accepted", "role": "owner", "accepted_at": datetime.now().isoformat()
        })

        # 해당 중개사 매물 공유
        shares = []
        for cid in agent_cards[agent_idx]:
            shares.append({"card_id": cid, "room_id": room_id, "shared_by": MY_USER_ID})

        # 내 매물 일부 공유 (10개)
        my_sample = random.sample(my_card_ids, min(10, len(my_card_ids)))
        for cid in my_sample:
            shares.append({"card_id": cid, "room_id": room_id, "shared_by": MY_USER_ID})

        share_count = batch_insert("card_shares", shares)
        print(f"  {sr['name']}: 방 생성 OK, 매물 {share_count}개 공유")

    # ===== 5단계: 손님 20명 + 타임라인 메모 =====
    print("\n[5단계] 손님 20명 + 타임라인 메모")

    client_cards = []
    all_notes = []

    for idx, cd in enumerate(CLIENT_DATA):
        card_id = gen_id()
        cat_kr = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸/빌라","commercial":"상가","office":"사무실"}.get(cd["category"],"매물")

        search_text = f"손님 {cd['trade_type']} {cd['location']} {cat_kr} {' '.join(cd['features'])} {cd['request'][:80]}"

        card = {
            "id": card_id,
            "agent_id": MY_USER_ID,
            "style": "memo",
            "color": "mint",
            "property": {
                "type": "손님",
                "price": f"{cd['trade_type']} 희망",
                "location": cd["location"],
                "complex": "",
                "area": "",
                "floor": "",
                "features": cd["features"],
                "category": cd["category"],
            },
            "agent": {"name": MY_AGENT["business_name"], "business_name": MY_AGENT["business_name"], "phone": MY_AGENT["phone"]},
            "private_note": {"memo": cd["request"]},
            "agent_comment": None,
            "search_text": search_text,
            "price_number": cd["price_number"],
            "photos": None,
            "embedding": None,
            "trade_status": "계약가능",
            "created_at": random_date(25),
        }
        client_cards.append(card)

        # 타임라인 메모 생성
        notes = gen_client_notes(card_id, cd, idx)
        all_notes.extend(notes)

    count = batch_insert("cards", client_cards)
    print(f"  손님 카드: {count}/{len(client_cards)}")

    note_count = batch_insert("client_notes", all_notes)
    print(f"  타임라인 메모: {note_count}/{len(all_notes)}")

    # ===== 완료 =====
    total_cards = len(all_agent_cards) + len(my_cards) + len(client_cards)
    print(f"\n{'=' * 60}")
    print(f"DONE!")
    print(f"  매물: 가상중개사 {len(all_agent_cards)} + 내 계정 {len(my_cards)} + 손님 {len(client_cards)} = {total_cards}개")
    print(f"  공유방: 3개")
    print(f"  타임라인 메모: {len(all_notes)}개")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
