# -*- coding: utf-8 -*-
"""25구 × 350개 = 8,750 매물 + 손님 200명 생성"""
import os, sys, json, random, string, requests
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# .env
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

DISTRICTS = [
    ("강남구", ["역삼동","삼성동","대치동","논현동","신사동","청담동","압구정동","도곡동","개포동","일원동"], 37.497, 127.028),
    ("서초구", ["서초동","반포동","방배동","잠원동","양재동","내곡동"], 37.483, 127.009),
    ("송파구", ["잠실동","문정동","가락동","석촌동","방이동","풍납동","거여동","마천동"], 37.514, 127.106),
    ("마포구", ["합정동","서교동","상수동","망원동","연남동","공덕동","도화동","상암동","대흥동","성산동"], 37.554, 126.910),
    ("용산구", ["이태원동","한남동","이촌동","용산동","후암동","원효로"], 37.532, 126.979),
    ("성동구", ["성수동","왕십리동","행당동","금호동","옥수동","응봉동"], 37.563, 127.037),
    ("광진구", ["구의동","자양동","화양동","중곡동","광장동","능동"], 37.538, 127.082),
    ("영등포구", ["여의도동","영등포동","당산동","문래동","양평동","신길동"], 37.526, 126.896),
    ("강동구", ["천호동","길동","둔촌동","강일동","암사동","고덕동","명일동"], 37.530, 127.124),
    ("동작구", ["사당동","노량진동","상도동","흑석동","대방동","동작동"], 37.497, 126.939),
    ("관악구", ["신림동","봉천동","남현동","조원동"], 37.478, 126.951),
    ("중구", ["명동","충무로","을지로","신당동","약수동","회현동"], 37.563, 126.997),
    ("종로구", ["종로동","삼청동","혜화동","평창동","부암동","명륜동"], 37.573, 126.979),
    ("강서구", ["마곡동","화곡동","등촌동","발산동","가양동","방화동"], 37.551, 126.849),
    ("양천구", ["목동","신월동","신정동"], 37.517, 126.867),
    ("구로구", ["구로동","신도림동","개봉동","고척동","오류동"], 37.495, 126.858),
    ("노원구", ["상계동","중계동","하계동","공릉동","월계동"], 37.654, 127.056),
    ("서대문구", ["신촌동","연희동","홍은동","홍제동","북가좌동","충정로"], 37.579, 126.937),
    ("은평구", ["응암동","불광동","녹번동","수색동","진관동","갈현동"], 37.603, 126.929),
    ("중랑구", ["면목동","상봉동","망우동","중화동","신내동","묵동"], 37.607, 127.093),
    ("도봉구", ["방학동","쌍문동","창동","도봉동"], 37.669, 127.032),
    ("동대문구", ["전농동","답십리동","장안동","회기동","청량리동","이문동"], 37.574, 127.040),
    ("성북구", ["길음동","돈암동","정릉동","성북동","장위동","석관동"], 37.589, 127.017),
    ("금천구", ["가산동","독산동","시흥동"], 37.457, 126.895),
    ("강북구", ["미아동","번동","수유동","우이동","삼양동"], 37.640, 127.011),
]

APT_BRANDS = ["래미안","자이","힐스테이트","푸르지오","더샵","롯데캐슬","e편한세상","아이파크","SK뷰","포레나","트리지움","리센츠","헬리오시티","파크리오","센트레빌","두산위브","한화포레나","금호어울림","디에이치","아크로","르엘"]
OFFICETEL_NAMES = ["SK오피스텔","트라팰리스","메트로","센트럴","프라임","캐슬","골든타워","리버파크","시티타워","비즈스퀘어"]
VILLA_NAMES = ["빌라","행복빌라","한빛빌라","그린빌라","신축빌라","해오름빌라","청구빌라","동아빌라","삼익빌라"]
COMMERCIAL_NAMES = ["1층 상가","상가","점포","매장","카페상가","편의점상가"]
OFFICE_NAMES = ["사무실","공유오피스","지식산업센터","업무오피스","코워킹스페이스"]
FEATURES = {
    "apartment": ["남향","역세권","올수리","주차가능","동향","학군우수","베란다확장","신축","풀옵션","한강뷰","공원뷰","고층","탑층","로열층","드레스룸","시스템에어컨","즉시입주","정남향","시티뷰","산뷰","주차2대","경비실","정원"],
    "officetel": ["역세권","풀옵션","신축","빌트인","고층","주차가능","즉시입주","시스템에어컨","초역세권"],
    "room": ["올수리","풀옵션","역세권","주차가능","애견가능","복층","루프탑","즉시입주","신축","베란다확장","CCTV","보안"],
    "commercial": ["1층","대로변","역세권","주차가능","코너","유동인구多","전면넓음","층고높음"],
    "office": ["역세권","엘리베이터","주차가능","신축","시티뷰","탕비실","회의실포함"],
}

def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def make_card(gu, dongs, lat, lng, category, trade_type):
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

    # 가격
    price_ranges = {
        ("apartment","매매"): [3,5,7,8,10,12,14,15,18,20,25,30,35,40,50],
        ("apartment","전세"): [2,3,4,5,6,7,8,9,10,12,15,18],
        ("officetel","매매"): [1.5,2,2.5,3,3.5,4,4.5,5],
        ("officetel","전세"): [0.8,1,1.2,1.5,1.8,2,2.5,3],
        ("room","매매"): [1,1.5,2,2.5,3,3.5,4,5],
        ("room","전세"): [0.5,0.8,1,1.2,1.5,2,2.5,3],
        ("commercial","매매"): [2,3,5,7,10,15,20],
        ("commercial","전세"): [1,1.5,2,3,5],
        ("office","매매"): [2,3,5,7,10],
        ("office","전세"): [0.5,0.8,1,1.5,2,3],
    }

    if trade_type == "월세":
        dep = random.choice([300,500,1000,1500,2000,3000,5000])
        mon = random.choice([30,40,50,60,70,80,90,100,120,150,200])
        price_str = f"보증금{dep:,}/월{mon}"
        price_number = dep
    else:
        eok = random.choice(price_ranges.get((category, trade_type), [3]))
        if eok >= 1:
            r = int((eok % 1) * 10000)
            b = int(eok)
            price_str = f"{b}억{f' {r:,}' if r else ''}"
        else:
            price_str = f"{int(eok*10000):,}만"
        price_number = int(eok * 10000)

    # 면적
    areas = {"apartment":[18,22,25,29,32,34,38,42,49,59,68,84],"officetel":[6,8,10,12,14,16,18],"room":[5,7,9,11,14,16,18,22],"commercial":[8,10,15,20,25,30,40],"office":[10,15,20,25,30,40,50]}
    pyeong = random.choice(areas.get(category,[20]))
    area = f"{pyeong}평"

    # 층
    if category == "apartment":
        floor = f"{random.choice([101,102,103,104,105])}동 {random.randint(2,30)}층"
    elif category == "commercial":
        floor = random.choice(["1층","지하1층","2층"])
    else:
        floor = f"{random.randint(2,20)}층"

    # 특징
    feats = random.sample(FEATURES.get(category,["역세권"]), min(random.randint(1,4), len(FEATURES.get(category,["역세권"]))))

    # 좌표 (구 중심에서 랜덤 offset)
    card_lat = lat + random.uniform(-0.012, 0.012)
    card_lng = lng + random.uniform(-0.012, 0.012)

    cat_ko = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}.get(category,"")
    search_text = f"{trade_type} {cat_ko} {price_str} {location} {complex_name} {area} {floor} {' '.join(feats)}"

    return {
        "id": gen_id(),
        "agent_id": MY_USER_ID,
        "style": "memo",
        "color": "mint" if trade_type=="전세" else "coral" if trade_type=="매매" else "blue",
        "property": {
            "type": trade_type, "price": price_str, "location": location,
            "complex": complex_name, "area": area, "floor": floor,
            "features": feats, "category": category,
            "moveIn": random.choice([None,"즉시입주","협의","2026년 5월","2026년 6월","2026년 7월"]),
        },
        "agent": {"name":"스마일부동산","business_name":"스마일부동산","phone":"010-4763-2531"},
        "agent_comment": f"{complex_name} {trade_type} {price_str}",
        "search_text": search_text,
        "price_number": price_number,
        "lat": round(card_lat, 6),
        "lng": round(card_lng, 6),
        "coord_type": "seed",
        "trade_status": random.choices(["계약가능","계약중"], weights=[85,15])[0],
        "created_at": (datetime.now() - timedelta(days=random.randint(0,30))).isoformat(),
    }

def make_client(gu, dongs, lat, lng):
    dong = random.choice(dongs)
    trade = random.choice(["매매","전세","월세"])
    cat = random.choice(["apartment","officetel","room","commercial","office"])
    cat_ko = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}.get(cat,"")

    if trade == "월세":
        price = f"보증금 {random.choice([500,1000,2000,3000])} 월세 {random.choice([30,50,80,100])} 이내"
    else:
        eok = random.choice([2,3,4,5,7,10,15])
        price = f"{eok}억 이내"

    memo = f"{gu} {dong} {cat_ko} {trade} {price} 원함. {random.choice(['급구','천천히','이번달','내년초','신혼부부','투자','실거주','직장근처'])}"

    return {
        "id": gen_id(),
        "agent_id": MY_USER_ID,
        "style": "a", "color": "#3b82f6",
        "property": {"type":"손님","price":price,"location":f"{gu} {dong}","complex":None,"area":None,"floor":None,"room":None,"features":[],"moveIn":None,"category":cat},
        "agent_comment": None,
        "search_text": f"손님 {trade} {cat_ko} {gu} {dong} {price} {memo}",
        "price_number": None,
        "lat": round(lat + random.uniform(-0.008,0.008), 6),
        "lng": round(lng + random.uniform(-0.008,0.008), 6),
        "trade_status": "계약가능",
        "private_note": {"memo": memo, "rawText": memo},
        "created_at": datetime.now().isoformat(),
    }

def insert_batch(cards, label=""):
    batch_size = 50
    total = len(cards)
    inserted = 0
    for i in range(0, total, batch_size):
        batch = cards[i:i+batch_size]
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/cards", headers=HEADERS, json=batch)
        if resp.status_code in (200, 201):
            inserted += len(batch)
        else:
            print(f"  ERROR: {resp.status_code} {resp.text[:200]}")
        if inserted % 500 == 0 or inserted == total:
            print(f"  {label} {inserted}/{total}")
    return inserted

if __name__ == "__main__":
    PER_DISTRICT = 350
    # 구별 배분: 아파트140 + 오피스텔70 + 원투룸70 + 상가35 + 사무실35 = 350
    cat_dist = [("apartment",140),("officetel",70),("room",70),("commercial",35),("office",35)]
    trade_types = ["매매","전세","월세"]

    print(f"=== 매물 생성: {len(DISTRICTS)}구 × {PER_DISTRICT}개 = {len(DISTRICTS)*PER_DISTRICT}개 ===")
    all_cards = []
    for gu, dongs, lat, lng in DISTRICTS:
        gu_cards = []
        for cat, count in cat_dist:
            for i in range(count):
                tt = trade_types[i % 3]
                gu_cards.append(make_card(gu, dongs, lat, lng, cat, tt))
        all_cards.extend(gu_cards)
        print(f"  {gu}: {len(gu_cards)}개 생성")

    random.shuffle(all_cards)
    print(f"\n총 {len(all_cards)}개 매물 생성 완료. DB 삽입 중...")
    inserted = insert_batch(all_cards, "매물")
    print(f"매물 {inserted}개 삽입 완료\n")

    # 손님 200명 (구별 8명씩)
    print("=== 손님 200명 생성 ===")
    clients = []
    for gu, dongs, lat, lng in DISTRICTS:
        for _ in range(8):
            clients.append(make_client(gu, dongs, lat, lng))
    random.shuffle(clients)
    c_inserted = insert_batch(clients, "손님")
    print(f"손님 {c_inserted}명 삽입 완료\n")

    print(f"=== 완료 ===")
    print(f"매물: {inserted}개 (25구 × {PER_DISTRICT})")
    print(f"손님: {c_inserted}명")
    print(f"총: {inserted + c_inserted}개")
