# -*- coding: utf-8 -*-
"""
휙 대량 테스트 데이터 생성
- 매물 1,000개 (이미지 없음, 빠른 생성)
- 검색 로그 10,000건 (학습용)
"""
import os, sys, json, random, requests, string
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

MY_USER_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"

# ========== 매물 생성 데이터 ==========
DISTRICTS = [
    ("강남구", ["역삼동","삼성동","대치동","논현동","신사동","청담동","압구정동","도곡동","개포동","일원동"]),
    ("서초구", ["서초동","반포동","방배동","잠원동","양재동","내곡동"]),
    ("송파구", ["잠실동","문정동","가락동","석촌동","방이동","풍납동","거여동","마천동"]),
    ("마포구", ["합정동","서교동","상수동","망원동","연남동","공덕동","도화동","상암동","대흥동","성산동"]),
    ("용산구", ["이태원동","한남동","이촌동","용산동","후암동","원효로"]),
    ("성동구", ["성수동","왕십리","행당동","금호동","옥수동","응봉동"]),
    ("광진구", ["건대입구","구의동","자양동","화양동","광장동"]),
    ("영등포구", ["여의도동","영등포동","당산동","문래동","양평동","신길동"]),
    ("강동구", ["천호동","길동","둔촌동","강일동","암사동","고덕동"]),
    ("동작구", ["사당동","노량진동","상도동","흑석동","대방동"]),
    ("관악구", ["신림동","봉천동","남현동"]),
    ("중구", ["명동","충무로","을지로","신당동","약수동"]),
    ("종로구", ["종로","광화문","삼청동","북촌","서촌","혜화동"]),
    ("강서구", ["마곡동","화곡동","등촌동","발산동","가양동"]),
    ("양천구", ["목동","신월동","신정동"]),
    ("구로구", ["구로동","신도림동","개봉동","고척동"]),
    ("노원구", ["상계동","중계동","하계동","공릉동","월계동"]),
    ("서대문구", ["신촌동","연희동","홍은동","북가좌동","충정로"]),
    ("은평구", ["응암동","불광동","녹번동","수색동","진관동"]),
    ("중랑구", ["면목동","상봉동","망우동","중화동"]),
    ("도봉구", ["방학동","쌍문동","창동","도봉동"]),
    ("동대문구", ["전농동","답십리","장안동","회기동","청량리"]),
    ("성북구", ["길음동","돈암동","정릉동","성북동","장위동"]),
    ("금천구", ["가산동","독산동","시흥동"]),
    ("강북구", ["미아동","번동","수유동","우이동"]),
]

APT_BRANDS = [
    "래미안","자이","힐스테이트","푸르지오","더샵","롯데캐슬","e편한세상","아이파크",
    "SK뷰","엘스","리센츠","트리지움","포레나","우미린","한화포레나","두산위브",
    "대림아파트","현대아파트","삼성아파트","한신아파트","쌍용아파트","동아아파트",
    "파크리오","센트레빌","베라체","헬리오시티","올림픽파크","아크로","타워팰리스",
    "갤러리아","레이크팰리스","하이페리온","디에이치","르엘","시그니엘",
]

OFFICETEL_NAMES = [
    "SK오피스텔","트라팰리스","메트로오피스텔","리버오피스텔","센트럴오피스텔",
    "스타오피스텔","프라임오피스텔","캐슬오피스텔","나루오피스텔","그린오피스텔",
    "더힐오피스텔","센트럴타워","골든타워","실버타워","블루타워",
]

VILLA_NAMES = ["빌라","투룸빌라","원룸","투룸","쓰리룸","다세대","연립주택","주택","하우스"]
COMMERCIAL_NAMES = ["1층 상가","상가","점포","매장","카페상가","음식점상가","편의점상가"]
OFFICE_NAMES = ["사무실","공유오피스","지식산업센터","업무용오피스","코워킹스페이스"]

FEATURES_POOL = {
    "apartment": [["남향","역세권","올수리","주차가능"],["동향","학군우수","베란다확장","주차2대"],["남동향","신축","풀옵션","시스템에어컨"],["서향","리모델링","드레스룸","즉시입주"],["정남향","한강뷰","고층","주차가능"],["남향","공원뷰","올수리","엘리베이터"],["탁트인전망","시티뷰","풀옵션","주차2대"],["남향","초역세권","올수리","즉시입주"],["더블역세권","학원가","주차가능","베란다확장"],["산뷰","정원","경비실","주차가능"]],
    "officetel": [["역세권","풀옵션","신축"],["빌트인","고층","주차가능"],["초역세권","풀옵션","시스템에어컨"],["역세권","올수리","즉시입주"],["신축","풀옵션","빌트인"],["더블역세권","주차가능","고층"]],
    "room": [["원룸","풀옵션","역세권"],["투룸","올수리","주차가능"],["쓰리룸","올수리","베란다확장"],["원룸","신축","풀옵션"],["투룸","역세권","애견가능"],["복층","루프탑","올수리"],["투룸","풀옵션","즉시입주"],["원룸","역세권","즉시입주"]],
    "commercial": [["1층","대로변","역세권"],["1층","주차가능","대로변"],["역세권","1층"],["대로변","코너","주차가능"]],
    "office": [["역세권","엘리베이터","주차가능"],["역세권","엘리베이터"],["신축","주차가능","엘리베이터"],["역세권","엘리베이터","시티뷰"]],
}

SUBWAY_STATIONS = [
    "강남역","역삼역","삼성역","선릉역","교대역","서초역","잠실역","종합운동장역",
    "합정역","홍대입구역","상수역","망원역","공덕역","마포역","여의도역","당산역",
    "건대입구역","왕십리역","성수역","뚝섬역","이태원역","녹사평역","한남역",
    "신림역","사당역","노량진역","대방역","천호역","강동역","잠실나루역",
    "신도림역","구로디지털단지역","가산디지털단지역","목동역","발산역","마곡역",
    "상봉역","망우역","중화역","면목역","회기역","청량리역","답십리역",
]

def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def gen_price(category, trade_type):
    if trade_type == "매매":
        if category == "apartment": return random.choice([3,5,7,8,9,10,11,12,13,14,15,16,18,20,22,25,28,30,35,38,40,45,50,55])
        if category == "officetel": return random.choice([1.5,1.8,2,2.2,2.5,2.8,3,3.2,3.5,4,4.2,4.5,5])
        if category == "room": return random.choice([1.5,2,2.5,3,3.5,3.8,4,4.5,5,5.5])
        if category == "commercial": return random.choice([3,4,5,6,7,8,9,10,12,15,20])
        if category == "office": return random.choice([3,4,5,6,7,8,10])
    elif trade_type == "전세":
        if category == "apartment": return random.choice([2,3,4,5,6,7,8,9,10,11,12,14,15,18])
        if category == "officetel": return random.choice([1,1.2,1.5,1.8,2,2.2,2.5,2.8,3,3.2,3.5])
        if category == "room": return random.choice([0.5,0.8,1,1.2,1.5,1.8,2,2.2,2.5,2.8,3])
        if category == "commercial": return random.choice([1,1.5,2,2.5,3,4,5])
        if category == "office": return random.choice([0.5,0.8,1,1.2,1.5,2,2.5,3])
    return 1

def format_price(eok, trade_type):
    if trade_type == "월세":
        deposits = [300,500,1000,1500,2000,3000,4000,5000]
        monthlys = [30,35,40,45,50,55,60,65,70,75,80,90,100,110,120,130,150,180,200,250,300]
        dep = random.choice(deposits)
        mon = random.choice(monthlys)
        return f"보증금{dep:,}/월{mon}", mon
    if eok >= 1:
        remainder = int((eok % 1) * 10000)
        base = int(eok)
        if remainder > 0:
            return f"{base}억 {remainder:,}", int(eok * 10000)
        return f"{base}억", int(eok * 10000)
    return f"{int(eok * 10000):,}만", int(eok * 10000)

def gen_area(category):
    if category == "apartment": return f"{random.choice([18,20,22,24,25,27,28,29,30,32,33,34,35,38,40,42,45,50,59,63,68,84])}평"
    if category == "officetel": return f"{random.choice([6,7,8,9,10,11,12,13,14,15,16,18])}평"
    if category == "room": return f"{random.choice([4,5,6,7,8,9,10,11,12,13,14,15,16,18,20,22])}평"
    if category == "commercial": return f"{random.choice([8,10,12,15,18,20,25,30,35,40])}평"
    if category == "office": return f"{random.choice([8,10,12,15,18,20,25,30,35,40,50])}평"
    return "20평"

def gen_floor(category):
    if category == "apartment":
        dong = random.choice([101,102,103,104,105,106,107,108,109,110,111,112])
        floor = random.randint(2, 30)
        return f"{dong}동 {floor}층"
    if category == "commercial": return random.choice(["1층","지하1층","2층"])
    return f"{random.randint(2, 20)}층"

def gen_comment(category, trade_type, district, dong, station):
    templates = {
        "apartment": [
            f"{station} 도보 {random.randint(2,10)}분, 실거주 추천 매물이에요.",
            f"{dong} 생활권, 학군 좋고 교통 편리해요.",
            f"{district} 인기 단지, {trade_type} 매물 드물어요.",
            f"올수리 완료, 바로 입주 가능합니다.",
            f"한강뷰/공원뷰 가능한 로얄층이에요.",
        ],
        "officetel": [
            f"{station} 초역세권, 직장인 최적 매물.",
            f"{dong} 1인 가구 인기 오피스텔이에요.",
            f"풀옵션이라 짐만 들어오면 돼요.",
        ],
        "room": [
            f"{station} 인근 가성비 좋은 매물이에요.",
            f"{dong} 조용한 주택가, 깨끗해요.",
            f"대학생/사회초년생 추천합니다.",
        ],
        "commercial": [
            f"{station} 유동인구 많은 입지예요.",
            f"{dong} 상권, 모든 업종 가능합니다.",
            f"현재 임차인 있어 수익 안정적이에요.",
        ],
        "office": [
            f"{station} 인근, 교통 편리한 사무실이에요.",
            f"{dong} 업무지구, 기업 밀집 지역.",
            f"소규모 스타트업에 적합한 사무실이에요.",
        ],
    }
    return random.choice(templates.get(category, [f"{district} {dong} 매물입니다."]))

def gen_memo():
    memos = [
        "집주인 010-XXXX-XXXX, 네고 가능",
        "즉시입주, 임대인 협조적",
        "전세보험 가입 가능",
        "반려동물 소형 가능",
        "장기 계약 시 할인",
        "관리비 별도 15만원",
        "주차 1대 포함",
        "",""  # 빈 메모도 가능
    ]
    return random.choice(memos)

def generate_cards(count=1000):
    cards = []
    categories = ["apartment"] * 35 + ["officetel"] * 20 + ["room"] * 25 + ["commercial"] * 10 + ["office"] * 10
    trade_types = ["매매","전세","월세"]

    for i in range(count):
        category = random.choice(categories)
        trade_type = random.choice(trade_types)
        gu, dongs = random.choice(DISTRICTS)
        dong = random.choice(dongs)
        location = f"{gu} {dong}"

        # 단지명
        if category == "apartment":
            complex_name = f"{dong.replace('동','')} {random.choice(APT_BRANDS)}"
        elif category == "officetel":
            complex_name = f"{dong.replace('동','')} {random.choice(OFFICETEL_NAMES)}"
        elif category == "room":
            complex_name = f"{dong.replace('동','')} {random.choice(VILLA_NAMES)}"
        elif category == "commercial":
            complex_name = f"{dong.replace('동','')} {random.choice(COMMERCIAL_NAMES)}"
        else:
            complex_name = f"{dong.replace('동','')} {random.choice(OFFICE_NAMES)}"

        # 근처 역
        station = random.choice(SUBWAY_STATIONS)

        # 가격
        eok = gen_price(category, trade_type)
        price_str, price_number = format_price(eok, trade_type)

        # 특징
        features = random.choice(FEATURES_POOL.get(category, [["역세권"]]))

        # 면적/층
        area = gen_area(category)
        floor = gen_floor(category)

        # 코멘트/메모
        comment = gen_comment(category, trade_type, gu, dong, station)
        memo = gen_memo()

        # 입주일
        move_in = random.choice([None, None, "즉시입주", "입주협의", "2026년 4월", "2026년 5월", "2026년 6월"])

        # search_text
        search_text = f"{trade_type} {price_str} {location} {complex_name} {area} {floor} {' '.join(features)}"

        card = {
            "id": gen_id(),
            "agent_id": MY_USER_ID,
            "style": "memo",
            "color": "mint" if trade_type == "전세" else "coral" if trade_type == "매매" else "blue",
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
            "agent": {"name": "스마일부동산", "business_name": "스마일부동산", "phone": "010-4763-2531"},
            "private_note": {"memo": memo} if memo else None,
            "agent_comment": comment,
            "search_text": search_text,
            "price_number": price_number,
            "photos": None,
            "trade_status": random.choices(["계약가능","계약중","완료"], weights=[80,15,5])[0],
            "created_at": (datetime.now() - timedelta(days=random.randint(0, 60))).isoformat(),
        }
        cards.append(card)
    return cards

# ========== 검색 로그 생성 ==========
SEARCH_QUERIES = [
    # 기본 거래유형
    ("매매", 80), ("전세", 80), ("월세", 80),
    # 지역
    ("강남", 60), ("마포", 60), ("송파", 50), ("잠실", 50), ("합정", 40),
    ("역삼", 30), ("반포", 30), ("서초", 30), ("여의도", 30), ("성수", 30),
    ("용산", 25), ("이태원", 20), ("홍대", 20), ("건대", 20), ("목동", 20),
    ("노원", 15), ("구로", 15), ("강서", 15), ("영등포", 15),
    # 카테고리
    ("아파트", 50), ("오피스텔", 40), ("원룸", 30), ("투룸", 25), ("상가", 20), ("사무실", 20),
    # 복합 검색
    ("강남 매매", 40), ("마포 전세", 40), ("송파 아파트", 30), ("잠실 전세", 30),
    ("강남 아파트 매매", 25), ("마포 월세 원룸", 25), ("역세권 풀옵션", 30),
    ("강남 전세 아파트", 25), ("합정 월세", 20), ("잠실 매매 아파트", 20),
    ("남향 올수리", 15), ("한강뷰", 20), ("신축 오피스텔", 20),
    ("즉시입주", 15), ("애견가능", 10), ("복층", 10), ("루프탑", 8),
    ("주차가능 투룸", 15), ("학군 잠실", 15), ("사무실 강남", 15),
    # 가격 조건
    ("3억 이하 전세", 25), ("5억 이상 매매", 20), ("10억 이상 아파트", 15),
    ("2억 미만", 15), ("1억 이하 월세", 15), ("20억 이상", 10),
    # 가혹한 검색
    ("마포 전세 풀옵 역세", 10), ("강남 아파트 남향 올수리", 10),
    ("상가 1층 역세권", 10), ("카페", 8), ("코엑스", 8),
    ("스타트업 사무실", 8), ("법조", 8), ("초역세권", 10),
    # 단지명
    ("래미안", 15), ("자이", 15), ("푸르지오", 10), ("아크로", 10), ("힐스테이트", 10),
    # 손님
    ("손님", 5), ("손님 강남", 5), ("손님 마포", 5),
]

def generate_search_logs(cards, count=10000):
    logs = []
    card_index = {}
    for c in cards:
        p = c["property"]
        key_text = f"{p['type']} {p.get('location','')} {p.get('complex','')} {p.get('category','')} {' '.join(p.get('features',[]))} {p.get('area','')}".lower()
        card_index[c["id"]] = key_text

    generated = 0
    while generated < count:
        query, weight = random.choice(SEARCH_QUERIES)
        q_lower = query.lower()
        q_words = q_lower.split()

        # 이 쿼리에 매칭되는 카드 찾기
        matching_ids = []
        for cid, ctext in card_index.items():
            if all(w in ctext for w in q_words):
                matching_ids.append(cid)

        if not matching_ids:
            # 부분 매칭
            for cid, ctext in card_index.items():
                if any(w in ctext for w in q_words):
                    matching_ids.append(cid)

        result_count = len(matching_ids)

        # 검색만 하고 클릭 안 한 경우 (30%)
        if random.random() < 0.3 or not matching_ids:
            logs.append({
                "agent_id": MY_USER_ID,
                "query": query,
                "result_count": result_count,
                "clicked_card_id": None,
                "search_mode": "local",
                "created_at": (datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0,23))).isoformat(),
            })
            generated += 1
            continue

        # 클릭한 경우 — 상위 매물 클릭 확률 높게
        click_count = random.choices([1,2,3], weights=[60,30,10])[0]
        clicked = random.sample(matching_ids[:min(20, len(matching_ids))], min(click_count, len(matching_ids)))

        for cid in clicked:
            logs.append({
                "agent_id": MY_USER_ID,
                "query": query,
                "result_count": result_count,
                "clicked_card_id": cid,
                "search_mode": "local",
                "created_at": (datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0,23))).isoformat(),
            })
            generated += 1
            if generated >= count:
                break

    return logs[:count]

# ========== 메인 ==========
def main():
    print("=" * 60)
    print("MASS DATA GENERATOR")
    print("=" * 60)

    # 1. 매물 5000개 생성
    print(f"\n--- Generating 5000 cards (no images) ---")
    cards = generate_cards(5000)

    # 배치 삽입 (50개씩)
    batch_size = 50
    success = 0
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i+batch_size]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/cards",
            headers=HEADERS,
            json=batch
        )
        if resp.status_code in (200, 201):
            success += len(batch)
            print(f"  Cards: {success}/{len(cards)}")
        else:
            print(f"  FAIL batch {i}: {resp.status_code} {resp.text[:100]}")

    print(f"\n  Total cards created: {success}")

    # 2. 검색 로그 30000건 생성
    print(f"\n--- Generating 30000 search logs ---")
    logs = generate_search_logs(cards, 30000)

    log_success = 0
    for i in range(0, len(logs), 100):
        batch = logs[i:i+100]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/search_logs",
            headers=HEADERS,
            json=batch
        )
        if resp.status_code in (200, 201):
            log_success += len(batch)
            if log_success % 1000 == 0:
                print(f"  Logs: {log_success}/{len(logs)}")
        else:
            print(f"  FAIL log batch {i}: {resp.status_code} {resp.text[:100]}")

    print(f"\n  Total logs created: {log_success}")

    print(f"\n{'=' * 60}")
    print(f"DONE! {success} cards + {log_success} search logs")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
