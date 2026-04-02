# -*- coding: utf-8 -*-
"""
휙 대규모 시드 데이터 생성 (v2)
- 기존 전부 삭제
- 내 매물 200건 (사진 5장씩)
- 중개사 25명 × 200건 = 5000건
- 공유방 25개 + 매물 공유
- 손님 30명 + 메모 180건 (3/15~4/15)
- 지저분한 데이터 ~20건
"""
import os, sys, json, uuid, random, string, requests, time, base64
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
HEADERS_REP = {**HEADERS, "Prefer": "return=representation"}

MY_USER_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"
MY_AGENT = {"business_name": "스마일부동산", "name": "스마일부동산", "phone": "010-4763-2531"}

# 이미지 경로
PHOTO_PATHS = [
    r"C:\Users\강동욱\Desktop\이미지\16.png",
    r"C:\Users\강동욱\Desktop\이미지\1 - 복사본 (2).png",
    r"C:\Users\강동욱\Desktop\이미지\6.png",
    r"C:\Users\강동욱\Desktop\이미지\10.png",
    r"C:\Users\강동욱\Desktop\이미지\11.png",
]

# ========== 데이터 풀 ==========
DISTRICTS = {
    "강남구": {"dongs":["역삼동","삼성동","대치동","논현동","신사동","청담동","압구정동","도곡동","개포동"],"lat":37.5172,"lng":127.0473},
    "서초구": {"dongs":["서초동","반포동","방배동","잠원동","양재동"],"lat":37.4836,"lng":127.0327},
    "송파구": {"dongs":["잠실동","문정동","가락동","석촌동","방이동","풍납동"],"lat":37.5145,"lng":127.1059},
    "마포구": {"dongs":["공덕동","합정동","서교동","상수동","망원동","연남동","성산동","상암동"],"lat":37.5633,"lng":126.9085},
    "용산구": {"dongs":["이태원동","한남동","이촌동","용산동","후암동"],"lat":37.5326,"lng":126.9906},
    "성동구": {"dongs":["성수동","왕십리","행당동","금호동","옥수동"],"lat":37.5633,"lng":127.0371},
    "광진구": {"dongs":["구의동","자양동","화양동","중곡동"],"lat":37.5384,"lng":127.0822},
    "영등포구": {"dongs":["여의도동","당산동","문래동","양평동","신길동"],"lat":37.5264,"lng":126.8963},
    "강동구": {"dongs":["천호동","둔촌동","강일동","암사동","고덕동"],"lat":37.5301,"lng":127.1238},
    "동작구": {"dongs":["사당동","노량진동","상도동","흑석동"],"lat":37.5124,"lng":126.9393},
    "관악구": {"dongs":["신림동","봉천동"],"lat":37.4784,"lng":126.9516},
    "종로구": {"dongs":["종로동","삼청동","혜화동","평창동"],"lat":37.5735,"lng":126.9790},
    "중구": {"dongs":["명동","충무로","을지로","신당동"],"lat":37.5641,"lng":126.9979},
    "강서구": {"dongs":["마곡동","화곡동","등촌동","발산동","가양동"],"lat":37.5510,"lng":126.8496},
    "양천구": {"dongs":["목동","신월동","신정동"],"lat":37.5170,"lng":126.8665},
    "구로구": {"dongs":["구로동","신도림동","개봉동"],"lat":37.4954,"lng":126.8874},
    "노원구": {"dongs":["상계동","중계동","하계동","공릉동"],"lat":37.6542,"lng":127.0568},
    "서대문구": {"dongs":["신촌동","연희동","홍은동"],"lat":37.5791,"lng":126.9368},
    "은평구": {"dongs":["응암동","불광동","녹번동","수색동","진관동"],"lat":37.6027,"lng":126.9291},
    "중랑구": {"dongs":["면목동","상봉동","망우동"],"lat":37.6063,"lng":127.0925},
    "도봉구": {"dongs":["방학동","쌍문동","창동"],"lat":37.6688,"lng":127.0471},
    "동대문구": {"dongs":["전농동","답십리동","장안동","회기동","청량리동"],"lat":37.5744,"lng":127.0400},
    "성북구": {"dongs":["길음동","돈암동","정릉동","장위동"],"lat":37.5894,"lng":127.0167},
    "금천구": {"dongs":["가산동","독산동","시흥동"],"lat":37.4519,"lng":126.9020},
    "강북구": {"dongs":["미아동","번동","수유동","우이동"],"lat":37.6397,"lng":127.0255},
}

AGENTS_25 = [
    {"gu":"강남구","biz":"미래공인중개사","name":"이지은","phone":"010-2501-0001"},
    {"gu":"서초구","biz":"반포부동산","name":"최민지","phone":"010-2501-0002"},
    {"gu":"송파구","biz":"잠실공인중개사","name":"박성호","phone":"010-2501-0003"},
    {"gu":"마포구","biz":"한강공인중개사","name":"김영수","phone":"010-2501-0004"},
    {"gu":"용산구","biz":"용산부동산","name":"정태우","phone":"010-2501-0005"},
    {"gu":"성동구","biz":"성수공인중개사","name":"강민호","phone":"010-2501-0006"},
    {"gu":"광진구","biz":"건대부동산","name":"윤서영","phone":"010-2501-0007"},
    {"gu":"영등포구","biz":"여의도공인중개사","name":"임재현","phone":"010-2501-0008"},
    {"gu":"강동구","biz":"강동부동산","name":"한수미","phone":"010-2501-0009"},
    {"gu":"동작구","biz":"사당공인중개사","name":"오진우","phone":"010-2501-0010"},
    {"gu":"관악구","biz":"신림부동산","name":"배지민","phone":"010-2501-0011"},
    {"gu":"종로구","biz":"광화문부동산","name":"구본재","phone":"010-2501-0012"},
    {"gu":"중구","biz":"명동공인중개사","name":"신하영","phone":"010-2501-0013"},
    {"gu":"강서구","biz":"마곡공인중개사","name":"문채원","phone":"010-2501-0014"},
    {"gu":"양천구","biz":"목동부동산","name":"장도윤","phone":"010-2501-0015"},
    {"gu":"구로구","biz":"구로공인중개사","name":"송예린","phone":"010-2501-0016"},
    {"gu":"노원구","biz":"노원부동산","name":"황민석","phone":"010-2501-0017"},
    {"gu":"서대문구","biz":"신촌공인중개사","name":"권나은","phone":"010-2501-0018"},
    {"gu":"은평구","biz":"은평부동산","name":"조현우","phone":"010-2501-0019"},
    {"gu":"중랑구","biz":"중랑공인중개사","name":"유서진","phone":"010-2501-0020"},
    {"gu":"도봉구","biz":"도봉부동산","name":"안예나","phone":"010-2501-0021"},
    {"gu":"동대문구","biz":"청량리공인중개사","name":"김태형","phone":"010-2501-0022"},
    {"gu":"성북구","biz":"길음부동산","name":"남지현","phone":"010-2501-0023"},
    {"gu":"금천구","biz":"가산공인중개사","name":"서동훈","phone":"010-2501-0024"},
    {"gu":"강북구","biz":"수유부동산","name":"차은서","phone":"010-2501-0025"},
]

APT_COMPLEXES = {
    "강남구":["아크로리버파크","대치 래미안","역삼 아이파크","타워팰리스","삼성 래미안","압구정 현대","도곡 렉슬","개포 자이"],
    "서초구":["반포 자이","래미안 퍼스티지","서초 힐스테이트","잠원 한신","방배 래미안","서초 자이"],
    "송파구":["잠실 엘스","잠실 리센츠","파크리오","헬리오시티","올림픽파크 포레온","잠실 레이크팰리스"],
    "마포구":["래미안 푸르지오","마포 자이","e편한세상 마포","DMC 래미안","마포 힐스테이트","공덕 자이"],
    "용산구":["용산 센트럴파크","한남 더힐","이촌 래미안","용산 파크타워","용산 푸르지오"],
    "성동구":["성수 자이","옥수 하이페리온","행당 한진","금호 두산위브","왕십리 텐즈힐"],
    "광진구":["건대 스타시티","광진 자이","자양 래미안","구의 현대"],
    "영등포구":["여의도 자이","여의도 시범","당산 래미안","영등포 푸르지오","당산 자이"],
    "강동구":["고덕 래미안","둔촌 자이","천호 래미안","암사 한강"],
    "동작구":["래미안 에버리치","이수 힐스테이트","상도 자이","사당 래미안"],
    "관악구":["관악 드림타운","봉천 래미안","신림 푸르지오"],
    "종로구":["경희궁자이","종로 래미안","혜화 래미안"],
    "중구":["신당 래미안","약수 하이페리온","충무로 자이"],
    "강서구":["마곡 힐스테이트","발산 래미안","화곡 푸르지오","마곡 자이"],
    "양천구":["목동 신시가지","목동 래미안","신정 래미안","목동 자이"],
    "구로구":["구로 파크푸르지오","신도림 래미안","개봉 롯데캐슬"],
    "노원구":["중계 래미안","상계 주공","노원 롯데캐슬","하계 래미안"],
    "서대문구":["서대문 래미안","연희 자이","신촌 힐스테이트"],
    "은평구":["은평 뉴타운 힐스테이트","응암 래미안","불광 롯데캐슬"],
    "중랑구":["중랑 포레나","면목 래미안","상봉 자이"],
    "도봉구":["창동 래미안","방학 자이","쌍문 래미안"],
    "동대문구":["한화꿈에그린","전농 래미안","답십리 래미안","청량리 자이"],
    "성북구":["길음 래미안","돈암 자이","정릉 래미안"],
    "금천구":["가산 래미안","독산 자이","시흥 래미안"],
    "강북구":["미아 래미안","수유 자이","번동 래미안"],
}
OFFICETEL_NAMES = ["SK오피스텔","트라팰리스","메트로오피스텔","센트럴오피스텔","프라임오피스텔","나루오피스텔","골든타워","블루타워"]
VILLA_NAMES = ["빌라","투룸빌라","신축빌라","원룸","투룸","쓰리룸"]
COMMERCIAL_NAMES = ["1층 상가","코너상가","메인상가","점포","카페상가","음식점상가"]
OFFICE_NAMES = ["사무실","지식산업센터","업무용오피스","코워킹스페이스"]

FEATURES_POOL = {
    "apartment": [
        ["남향","역세권","올수리","주차가능"],["동향","학군좋음","베란다확장","주차가능"],
        ["남동향","신축","풀옵션","시스템에어컨"],["정남향","한강뷰","고층","주차가능"],
        ["남향","공원뷰","올수리","엘리베이터"],["초역세권","올수리","즉시입주"],
        ["더블역세권","학원가","주차가능","베란다확장"],["남향","초품아","학군좋음"],
        ["HUG가능","무융자","남향","역세권"],["신축","풀옵션","주차가능","보안"],
    ],
    "officetel": [
        ["역세권","풀옵션","신축"],["빌트인","고층","주차가능"],
        ["초역세권","풀옵션","시스템에어컨"],["역세권","올수리","즉시입주"],
        ["신축","풀옵션","빌트인"],["더블역세권","주차가능","고층"],
        ["HUG가능","역세권","풀옵션"],["무인택배","보안","엘리베이터"],
    ],
    "room": [
        ["풀옵션","역세권"],["올수리","주차가능"],
        ["올수리","베란다확장"],["신축","풀옵션"],
        ["역세권","애견가능"],["복층","루프탑","올수리"],
        ["풀옵션","즉시입주"],["역세권","즉시입주"],
        ["분리형","풀옵션"],["HUG가능","올수리"],
    ],
    "commercial": [
        ["1층","대로변","역세권"],["1층","주차가능","대로변"],
        ["역세권","1층"],["대로변","코너자리","주차가능"],
        ["유동인구많음","전면넓음"],["1층상가","업종제한없음"],
    ],
    "office": [
        ["역세권","엘리베이터","주차가능"],["역세권","엘리베이터"],
        ["신축","주차가능","엘리베이터"],["역세권","엘리베이터","시티뷰"],
        ["대출가능","역세권"],["주차가능","보안","엘리베이터"],
    ],
}

# ========== 헬퍼 ==========
def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def random_date_range(start, end):
    delta = end - start
    rand_days = random.randint(0, max(delta.days, 1))
    return start + timedelta(days=rand_days, hours=random.randint(6,22), minutes=random.randint(0,59))

def gen_price(category, trade_type):
    if trade_type == "매매":
        prices = {"apartment":[3,4,5,6,7,8,9,10,12,14,15,18,20,25,30,35,40,50],"officetel":[1.5,2,2.5,3,3.5,4,5],"room":[1.5,2,2.5,3,4,5],"commercial":[3,5,7,10,12,15,20],"office":[3,5,7,8,10,12]}
    elif trade_type == "전세":
        prices = {"apartment":[2,3,4,5,6,7,8,9,10,12,15,18],"officetel":[1,1.5,2,2.5,3,3.5],"room":[0.5,0.8,1,1.2,1.5,2,2.5,3],"commercial":[1,2,3,5],"office":[0.5,1,1.5,2,2.5,3]}
    else:
        return None
    return random.choice(prices.get(category, [3]))

def format_price(eok, trade_type, category):
    if trade_type == "월세":
        dep_ranges = {"apartment":([3000,5000,7000,10000],[100,130,150,200,250]),"officetel":([300,500,1000,1500,2000],[40,50,60,70,80,100,120]),"room":([200,300,500,700,1000],[30,35,40,45,50,60,70,80]),"commercial":([2000,3000,5000,7000,10000],[100,150,200,300,400,500]),"office":([1000,2000,3000,5000],[80,100,150,200,300])}
        deps, mons = dep_ranges.get(category, ([1000],[50]))
        dep = random.choice(deps); mon = random.choice(mons)
        return f"보증금{dep:,}/월{mon}", dep, mon
    if eok >= 1:
        base = int(eok); rem = int(round((eok - base) * 10000))
        if rem > 0: return f"{base}억 {rem:,}", int(eok * 10000), None
        return f"{base}억", int(eok * 10000), None
    return f"{int(eok * 10000):,}만", int(eok * 10000), None

def gen_area(cat):
    areas = {"apartment":[18,22,25,29,32,34,38,42,50,59],"officetel":[6,8,10,12,14,16,18],"room":[4,6,8,10,12,15,18,20],"commercial":[8,10,15,20,25,30,40],"office":[8,10,15,20,25,30,40,50]}
    return f"{random.choice(areas.get(cat,[20]))}평"

def gen_floor(cat):
    if cat == "apartment":
        return f"{random.choice([101,102,103,104,105])}동 {random.randint(2,25)}층"
    if cat == "commercial":
        return random.choice(["1층","지하1층","2층"])
    return f"{random.randint(2,18)}층"

def gen_complex(cat, gu, dong):
    ds = dong.replace("동","").replace("리","")
    if cat == "apartment":
        return random.choice(APT_COMPLEXES.get(gu, [f"{ds} 래미안"]))
    elif cat == "officetel": return f"{ds} {random.choice(OFFICETEL_NAMES)}"
    elif cat == "room": return f"{ds} {random.choice(VILLA_NAMES)}"
    elif cat == "commercial": return f"{ds} {random.choice(COMMERCIAL_NAMES)}"
    else: return f"{ds} {random.choice(OFFICE_NAMES)}"

def gen_tags(cat, trade_type, gu, dong, features, area_str, floor_str, complex_name):
    """간단 태그 생성 (Edge Function의 generateTags와 유사)"""
    tags = ["서울", gu, dong]
    if trade_type in ["매매","전세","월세"]: tags.append(trade_type)
    cat_map = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}
    if cat in cat_map: tags.append(cat_map[cat])
    tags.extend(features)
    # 단지명
    cn = complex_name.replace("아파트","").replace("오피스텔","").strip()
    if cn and len(cn) >= 2: tags.append(cn)
    # 면적 구간
    am = area_str.replace("평","")
    try:
        p = int(am)
        if p <= 10: tags.append("5~10평")
        elif p <= 15: tags.append("10~15평")
        elif p <= 20: tags.append("15~20평")
        elif p <= 25: tags.append("20~25평")
        elif p <= 30: tags.append("25~30평")
        elif p <= 40: tags.append("30~40평")
        else: tags.append("40평이상")
    except: pass
    return list(set(tags))

def batch_insert(table, data, batch_size=50, delay=0.1):
    success = 0
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=batch)
        if resp.status_code in (200, 201):
            success += len(batch)
        else:
            print(f"  FAIL {table} batch {i}: {resp.status_code} {resp.text[:200]}")
        if delay: time.sleep(delay)
    return success

def batch_delete(table, query):
    resp = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?{query}", headers=HEADERS)
    return resp.status_code in (200, 204)

# ========== 매물 카드 생성 ==========
def make_card(category, trade_type, gu, agent_id, agent_info, dirty=False):
    info = DISTRICTS[gu]
    dong = random.choice(info["dongs"])
    location = f"{gu} {dong}"
    complex_name = gen_complex(category, gu, dong)
    features = random.choice(FEATURES_POOL.get(category, [["역세권"]]))
    area = gen_area(category)
    floor = gen_floor(category)
    move_in = random.choice([None, "즉시입주", "입주협의", "2026년 5월", "2026년 6월"])
    lat = info["lat"] + random.uniform(-0.012, 0.012)
    lng = info["lng"] + random.uniform(-0.012, 0.012)

    if trade_type == "월세":
        price_str, deposit, monthly = format_price(None, "월세", category)
        price_number = deposit
    else:
        eok = gen_price(category, trade_type)
        price_str, price_number, _ = format_price(eok, trade_type, category)
        deposit = None; monthly = None

    # 지저분한 데이터
    if dirty:
        dirty_mods = [
            lambda: (price_str.replace("억","억 ").replace("보증금","보증금 "), features),
            lambda: (price_str.replace("천","쳔"), features + ["풀업션"]),
            lambda: (price_str, [f.replace("역세권","역새권") for f in features]),
            lambda: (price_str + "  ", features),
        ]
        mod = random.choice(dirty_mods)
        price_str_d, features_d = mod()
        price_str = price_str_d; features = features_d

    search_text = f"{trade_type} {price_str} {location} {complex_name} {area} {floor} {' '.join(features)}"
    tags = gen_tags(category, trade_type, gu, dong, features, area, floor, complex_name)

    return {
        "id": gen_id(),
        "agent_id": agent_id,
        "style": "memo",
        "color": "mint" if trade_type == "전세" else "coral" if trade_type == "매매" else "blue",
        "property": {
            "type": trade_type, "price": price_str, "location": location,
            "complex": complex_name, "area": area, "floor": floor,
            "features": features, "category": category, "moveIn": move_in,
            "rawText": f"{location} {complex_name} {trade_type} {price_str} {area} {floor} {' '.join(features)}"
        },
        "private_note": {"memo": random.choice([
            "집주인 협조적, 네고 가능","즉시입주 가능","관리비 별도 15만원",
            "융자 없음, 깨끗한 매물","올수리 2024년 완료","주차 1대 포함",
            "장기 계약 선호","보증보험 가입 가능","세입자 깨끗하게 사용",
        ])},
        "agent_comment": f"💬 {gu} {dong} {category} {trade_type} 추천 매물",
        "search_text": search_text,
        "price_number": price_number,
        "deposit": deposit,
        "monthly_rent": monthly,
        "lat": round(lat, 6), "lng": round(lng, 6),
        "photos": None,
        "tags": tags,
        "trade_status": random.choices(["계약가능","계약중"], weights=[85,15])[0],
        "created_at": random_date_range(datetime(2026,3,10), datetime(2026,4,1)).isoformat(),
    }

def generate_cards(agent_id, agent_info, gu, count=200, dirty_count=0):
    cards = []
    # 비율: 아파트70, 오피스텔40, 원투룸40, 상가25, 사무실25
    dist = [("apartment",70),("officetel",40),("room",40),("commercial",25),("office",25)]
    for cat, n in dist:
        actual = int(n * count / 200)
        for i in range(actual):
            tt = random.choice(["매매","전세","월세"]) if cat in ["apartment","officetel"] else random.choice(["매매","전세","월세","월세"])
            dirty = dirty_count > 0 and len(cards) < dirty_count
            cards.append(make_card(cat, tt, gu, agent_id, agent_info, dirty=dirty))
    return cards[:count]

# ========== 사진 업로드 ==========
def upload_photos(card_ids, batch_label=""):
    """카드에 사진 5장씩 업로드"""
    photo_data = []
    for p in PHOTO_PATHS:
        with open(p, "rb") as f:
            photo_data.append(f.read())

    uploaded = 0
    for idx, cid in enumerate(card_ids):
        urls = []
        for pi, pdata in enumerate(photo_data):
            fname = f"{pi}_{int(time.time()*1000)}.png"
            path = f"photos/cards/{cid}/{fname}"
            resp = requests.post(
                f"{SUPABASE_URL}/storage/v1/object/{path}",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "image/png"},
                data=pdata
            )
            if resp.status_code in (200, 201):
                urls.append(f"{SUPABASE_URL}/storage/v1/object/public/{path}")
            time.sleep(0.05)
        # 카드 업데이트
        if urls:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/cards?id=eq.{cid}",
                headers=HEADERS,
                json={"photos": urls}
            )
            uploaded += 1
        if (idx+1) % 20 == 0:
            print(f"  {batch_label} 사진 업로드: {idx+1}/{len(card_ids)}")
    return uploaded

# ========== 메인 ==========
def main():
    print("=" * 60)
    print("휙 대규모 시드 데이터 생성 (v2)")
    print("=" * 60)

    # ===== 0. 기존 데이터 삭제 =====
    print("\n[0] 기존 데이터 삭제")
    for table, q in [
        ("client_notes", f"agent_id=eq.{MY_USER_ID}"),
        ("match_notifications", f"agent_id=eq.{MY_USER_ID}"),
        ("memos", f"agent_id=eq.{MY_USER_ID}"),
        ("search_logs", f"agent_id=eq.{MY_USER_ID}"),
    ]:
        batch_delete(table, q)
        print(f"  {table}: OK")

    # 공유 관련 삭제 (카드 전에)
    batch_delete("card_shares", f"shared_by=eq.{MY_USER_ID}")
    print("  card_shares: OK")

    # 공유방 멤버/방 삭제
    # 내가 멤버인 방 조회
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/share_room_members?member_id=eq.{MY_USER_ID}&select=room_id", headers=HEADERS_REP)
    if resp.status_code == 200:
        rooms = [r["room_id"] for r in resp.json()]
        for rid in rooms:
            batch_delete("card_shares", f"room_id=eq.{rid}")
            batch_delete("share_room_members", f"room_id=eq.{rid}")
            batch_delete("share_rooms", f"id=eq.{rid}")
    print("  share_rooms/members: OK")

    # 모든 카드 삭제 (내 것)
    batch_delete("cards", f"agent_id=eq.{MY_USER_ID}")
    print("  my cards: OK")

    # 기존 테스트 중개사 카드/프로필 삭제
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/profiles?phone=like.010-2501-*&select=id", headers=HEADERS_REP)
    if resp.status_code == 200:
        test_ids = [p["id"] for p in resp.json()]
        for tid in test_ids:
            batch_delete("cards", f"agent_id=eq.{tid}")
            batch_delete("profiles", f"id=eq.{tid}")
        print(f"  기존 테스트 중개사 {len(test_ids)}명 삭제")

    # ===== 1. 테스트 중개사 25명 =====
    print("\n[1] 테스트 중개사 25명 생성")
    agent_map = {}  # gu -> {"id": uuid, "biz": ..., "cards": [...]}

    for idx, ag in enumerate(AGENTS_25):
        email = f"test-agent-{idx+1}@hwik-test.com"
        admin_headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}

        # auth user 생성 시도
        user_resp = requests.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin_headers,
            json={"email": email, "password": "test1234!@", "email_confirm": True})
        if user_resp.status_code in (200, 201):
            user_id = user_resp.json().get("id")
        else:
            # 이미 존재 → admin API로 이메일 기반 조회 (여러 페이지)
            user_id = None
            for page in range(1, 10):
                list_resp = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users?page={page}&per_page=100", headers=admin_headers)
                if list_resp.status_code != 200: break
                users = list_resp.json().get("users", [])
                if not users: break
                for u in users:
                    if u.get("email") == email:
                        user_id = u["id"]
                        break
                if user_id: break
            if not user_id:
                print(f"  {ag['gu']} 중개사 조회 실패")
                continue

        # 프로필 upsert (있으면 업데이트, 없으면 생성)
        requests.post(f"{SUPABASE_URL}/rest/v1/profiles",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json={"id": user_id, "business_name": ag["biz"], "agent_name": ag["name"],
                  "phone": ag["phone"], "address": f"서울시 {ag['gu']}"})

        agent_map[ag["gu"]] = {"id": str(user_id), "biz": ag["biz"], "name": ag["name"], "phone": ag["phone"]}
        print(f"  {ag['gu']} {ag['biz']} ({ag['name']}): {user_id}")
        time.sleep(0.1)

    # ===== 2. 내 매물 200건 =====
    print("\n[2] 내 매물 200건 생성")
    all_gus = list(DISTRICTS.keys())
    my_cards = []
    for i in range(200):
        gu = random.choice(all_gus)
        cat = random.choices(["apartment","officetel","room","commercial","office"], weights=[35,20,20,13,12])[0]
        tt = random.choice(["매매","전세","월세"])
        dirty = i < 20  # 처음 20건 지저분
        my_cards.append(make_card(cat, tt, gu, MY_USER_ID, MY_AGENT, dirty=dirty))

    count = batch_insert("cards", my_cards, delay=0.15)
    print(f"  저장: {count}/200")
    my_card_ids = [c["id"] for c in my_cards]

    # 사진 업로드
    print("\n  사진 업로드 (200건 × 5장 = 1000장)")
    photo_count = upload_photos(my_card_ids, "내 매물")
    print(f"  사진 완료: {photo_count}/200")

    # ===== 3. 중개사별 매물 200건 =====
    print("\n[3] 중개사 25명 × 200건 = 5000건")
    for gu, ag_info in agent_map.items():
        cards = generate_cards(ag_info["id"], ag_info, gu, count=200)
        cnt = batch_insert("cards", cards, delay=0.1)
        ag_info["card_ids"] = [c["id"] for c in cards]
        print(f"  {gu} {ag_info['biz']}: {cnt}/200")

    # ===== 4. 공유방 25개 =====
    print("\n[4] 공유방 25개 + 매물 공유")
    for gu, ag_info in agent_map.items():
        room_id = str(uuid.uuid4())
        # 방 생성
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/share_rooms", headers=HEADERS, json={
            "id": room_id, "name": f"{gu} 매물공유방", "owner_id": ag_info["id"]
        })
        if resp.status_code not in (200, 201):
            print(f"  {gu} 방 생성 실패: {resp.text[:100]}")
            continue

        # 멤버 등록
        members = [
            {"room_id": room_id, "member_id": ag_info["id"], "invited_phone": ag_info["phone"], "status": "accepted", "role": "owner", "accepted_at": datetime.now().isoformat()},
            {"room_id": room_id, "member_id": MY_USER_ID, "invited_phone": "01047632531", "status": "accepted", "role": "member", "accepted_at": datetime.now().isoformat()},
        ]
        batch_insert("share_room_members", members, delay=0)

        # 매물 공유
        shares = [{"card_id": cid, "room_id": room_id, "shared_by": ag_info["id"]} for cid in ag_info.get("card_ids", [])]
        sc = batch_insert("card_shares", shares, delay=0.05)
        print(f"  {gu}: 방 OK, 매물 {sc}건 공유")

    # ===== 5. 손님 30명 =====
    print("\n[5] 손님 30명 등록")
    CLIENT_DATA = [
        {"name":"김서연","req":"마포구 전세 아파트 30평대 역세권 5억 이내","cat":"apartment","tt":"전세","loc":"마포구","dep":None,"mon":None,"pn":50000,"feats":["역세권"]},
        {"name":"박준혁","req":"강남 매매 아파트 40평대 한강뷰 20~30억","cat":"apartment","tt":"매매","loc":"강남구","dep":None,"mon":None,"pn":250000,"feats":["한강뷰"]},
        {"name":"이하은","req":"송파구 잠실 전세 아파트 25평 이상 8억 이내","cat":"apartment","tt":"전세","loc":"송파구","dep":None,"mon":None,"pn":80000,"feats":["역세권"]},
        {"name":"정우진","req":"강남역 월세 오피스텔 보증금 1천 월세 80 이하 풀옵션","cat":"officetel","tt":"월세","loc":"강남구","dep":1000,"mon":80,"pn":1000,"feats":["풀옵션","역세권"]},
        {"name":"최수아","req":"홍대 전세 투룸 2억5천 이내 올수리","cat":"room","tt":"전세","loc":"마포구","dep":None,"mon":None,"pn":25000,"feats":["올수리"]},
        {"name":"강민준","req":"서초 반포 매매 50평대 한강뷰 35억","cat":"apartment","tt":"매매","loc":"서초구","dep":None,"mon":None,"pn":350000,"feats":["한강뷰"]},
        {"name":"윤지아","req":"합정역 월세 원룸 보증금 500 월세 45 이하 풀옵션","cat":"room","tt":"월세","loc":"마포구","dep":500,"mon":45,"pn":500,"feats":["풀옵션"]},
        {"name":"임태현","req":"여의도 전세 오피스텔 3억 이내 15평 이상","cat":"officetel","tt":"전세","loc":"영등포구","dep":None,"mon":None,"pn":30000,"feats":["역세권"]},
        {"name":"한소희","req":"용산 이촌동 전세 한강뷰 30평대 10억","cat":"apartment","tt":"전세","loc":"용산구","dep":None,"mon":None,"pn":100000,"feats":["한강뷰"]},
        {"name":"오준서","req":"성수동 월세 오피스텔 보증금 1천 월세 75 이하 신축","cat":"officetel","tt":"월세","loc":"성동구","dep":1000,"mon":75,"pn":1000,"feats":["신축"]},
        {"name":"배지민","req":"강남 대로변 1층 상가 보증금 1억 월세 500 이하","cat":"commercial","tt":"월세","loc":"강남구","dep":10000,"mon":500,"pn":10000,"feats":["1층","대로변"]},
        {"name":"신하영","req":"테헤란로 사무실 30평 보증금 5천 월세 300","cat":"office","tt":"월세","loc":"강남구","dep":5000,"mon":300,"pn":5000,"feats":["역세권"]},
        {"name":"구본재","req":"노원구 전세 아파트 3억 이내 20평대 신혼","cat":"apartment","tt":"전세","loc":"노원구","dep":None,"mon":None,"pn":30000,"feats":["역세권"]},
        {"name":"문채원","req":"양천구 목동 매매 아파트 14억 이내 학군 32평","cat":"apartment","tt":"매매","loc":"양천구","dep":None,"mon":None,"pn":140000,"feats":["학군좋음"]},
        {"name":"장도윤","req":"건대입구 전세 투룸 2억 이내 역세권","cat":"room","tt":"전세","loc":"광진구","dep":None,"mon":None,"pn":20000,"feats":["역세권","올수리"]},
        {"name":"송예린","req":"홍대 1층 상가 보증금 5천 월세 200 카페 창업","cat":"commercial","tt":"월세","loc":"마포구","dep":5000,"mon":200,"pn":5000,"feats":["1층"]},
        {"name":"황민석","req":"강남 매매 오피스텔 3억 이내 역세권","cat":"officetel","tt":"매매","loc":"강남구","dep":None,"mon":None,"pn":30000,"feats":["역세권"]},
        {"name":"권나은","req":"사당역 전세 아파트 4억 이내 역세권","cat":"apartment","tt":"전세","loc":"동작구","dep":None,"mon":None,"pn":40000,"feats":["역세권"]},
        {"name":"조현우","req":"마포 합정 사무실 10평 보증금 1천 월세 80","cat":"office","tt":"월세","loc":"마포구","dep":1000,"mon":80,"pn":1000,"feats":["역세권"]},
        {"name":"유서진","req":"잠실 월세 아파트 보증금 5천 월세 150 30평대","cat":"apartment","tt":"월세","loc":"송파구","dep":5000,"mon":150,"pn":5000,"feats":["역세권"]},
        {"name":"안예나","req":"성수동 매매 아파트 30평대 12억 이내","cat":"apartment","tt":"매매","loc":"성동구","dep":None,"mon":None,"pn":120000,"feats":["역세권"]},
        # 지저분한 손님 데이터
        {"name":"김태형","req":"관악 봉천 원름 월세 300/40 풀업션 역새권","cat":"room","tt":"월세","loc":"관악구","dep":300,"mon":40,"pn":300,"feats":["풀옵션"]},
        {"name":"남지현","req":"서대문 신촌 전셰 4억이하 20평대","cat":"apartment","tt":"전세","loc":"서대문구","dep":None,"mon":None,"pn":40000,"feats":[]},
        {"name":"서동훈","req":"종로 1층 상가 대로변 매매 10억 코너","cat":"commercial","tt":"매매","loc":"종로구","dep":None,"mon":None,"pn":100000,"feats":["1층","대로변","코너자리"]},
        {"name":"차은서","req":"강동 오피스텔 전세 2억이내 역세권","cat":"officetel","tt":"전세","loc":"강동구","dep":None,"mon":None,"pn":20000,"feats":["역세권"]},
        {"name":"이정민","req":"마포구 아파트나 오피스텔 전세 5억 이내 역세권","cat":"apartment","tt":"전세","loc":"마포구","dep":None,"mon":None,"pn":50000,"feats":["역세권"],"multi_cat":["apartment","officetel"]},
        {"name":"박수현","req":"강북 수유 투룸 전세 1억5천 이내 수유역근처","cat":"room","tt":"전세","loc":"강북구","dep":None,"mon":None,"pn":15000,"feats":["역세권"]},
        {"name":"홍길동","req":"강서 마곡동 아파트 매매 7억 이내 30평","cat":"apartment","tt":"매매","loc":"강서구","dep":None,"mon":None,"pn":70000,"feats":[]},
        {"name":"김미영","req":"금천 가산동 지식산업센터 전세 2억","cat":"office","tt":"전세","loc":"금천구","dep":None,"mon":None,"pn":20000,"feats":["역세권"]},
        {"name":"전재우","req":"도봉구 역세권 아파트 전세 2억5천 이내 20평대","cat":"apartment","tt":"전세","loc":"도봉구","dep":None,"mon":None,"pn":25000,"feats":["역세권"]},
    ]

    client_cards = []
    for cd in CLIENT_DATA:
        cid = gen_id()
        gu = cd["loc"]
        dong = random.choice(DISTRICTS.get(gu, {"dongs":[""]})["dongs"])
        cat_map = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}
        tags = ["서울", gu, dong, cd["tt"]]
        if cd["cat"] in cat_map: tags.append(cat_map[cd["cat"]])
        tags.extend(cd["feats"])
        multi = cd.get("multi_cat")
        wc = [cd["cat"]]
        if multi: wc = multi

        client_cards.append({
            "id": cid, "agent_id": MY_USER_ID, "style": "memo", "color": "mint",
            "property": {"type":"손님","price":cd["req"].split("이내")[0] if "이내" in cd["req"] else cd["req"][:30],"location":f"{gu} {dong}","complex":"","area":"","floor":"","features":cd["feats"],"category":cd["cat"],"rawText":cd["req"]},
            "contact_name": cd["name"], "contact_phone": f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
            "search_text": cd["req"],
            "price_number": cd["pn"], "deposit": cd["dep"], "monthly_rent": cd["mon"],
            "wanted_trade_type": cd["tt"],
            "wanted_categories": wc,
            "tags": list(set(tags)),
            "lat": DISTRICTS.get(gu,{"lat":37.5,"lng":127})["lat"] + random.uniform(-0.005,0.005),
            "lng": DISTRICTS.get(gu,{"lat":37.5,"lng":127})["lng"] + random.uniform(-0.005,0.005),
            "trade_status": "계약가능",
            "created_at": random_date_range(datetime(2026,3,15), datetime(2026,3,25)).isoformat(),
        })

    cnt = batch_insert("cards", client_cards, delay=0)
    print(f"  손님 저장: {cnt}/30")

    # ===== 6. 손님 메모 (3/15~4/15) =====
    print("\n[6] 손님 메모 생성 (3/15~4/15)")
    all_notes = []
    memo_stages = [
        {"offset":(0,3),"type":"상담","tpl":["{name} 손님 첫 상담. {loc} {tt} {cat} 찾으심.","{name} 손님 전화 상담. 조건 정리 완료."]},
        {"offset":(3,6),"type":"매물소개","tpl":["{name} 손님께 매물 5건 카톡 전송. 2건 관심.","{name} 손님 매물 확인 후 주말 방문 의사."]},
        {"offset":(6,10),"type":"방문","tpl":["{name} 손님 현장 방문 2건 완료. 첫 번째 마음에 듦.","{name} 손님 가족과 방문. 긍정적 반응."]},
        {"offset":(10,15),"type":"메모","tpl":["{name} 손님 가격 네고 진행 중. 500만원 조정 가능.","{name} 손님 조건 변경: 평수 좀 넓어도 된다고."]},
        {"offset":(15,20),"type":"방문","tpl":["{name} 손님 재방문 완료. 계약 의향 있음.","{name} 손님 남편과 재방문. 긍정적."]},
        {"offset":(20,25),"type":"서류","tpl":["{name} 손님 등기부등본 확인 완료.","{name} 손님 HUG 보증보험 가입 문의."]},
        {"offset":(25,28),"type":"대출","tpl":["{name} 손님 은행 대출 상담 완료. 디딤돌 가능.","{name} 손님 대출 사전승인 완료."]},
        {"offset":(28,32),"type":"계약","tpl":["{name} 손님 계약 예정. 특약 조율 중.","{name} 손님 가계약금 입금 예정."]},
    ]

    base_date = datetime(2026, 3, 15)
    for ci, cd in enumerate(CLIENT_DATA):
        cid = client_cards[ci]["id"]
        name = cd["name"]
        loc = cd["loc"]
        tt = cd["tt"]
        cat_kr = {"apartment":"아파트","officetel":"오피스텔","room":"원투룸","commercial":"상가","office":"사무실"}.get(cd["cat"],"매물")

        # 각 손님마다 5~8 메모
        num_stages = random.randint(5, min(8, len(memo_stages)))
        for si in range(num_stages):
            stage = memo_stages[si]
            day_offset = random.randint(*stage["offset"])
            note_date = base_date + timedelta(days=day_offset, hours=random.randint(9,18))
            content = random.choice(stage["tpl"]).format(name=name, loc=loc, tt=tt, cat=cat_kr)

            alert_date_val = None
            if si >= 4 and random.random() < 0.6:
                alert_day = base_date + timedelta(days=day_offset + random.randint(1, 5))
                alert_date_val = alert_day.strftime("%Y-%m-%dT%H:%M:%S")

            all_notes.append({
                "client_card_id": cid,
                "agent_id": MY_USER_ID,
                "type": stage["type"],
                "content": content,
                "alert_date": alert_date_val,
                "alert_done": False,
                "created_at": note_date.isoformat(),
            })

    nc = batch_insert("client_notes", all_notes, delay=0)
    print(f"  메모 저장: {nc}/{len(all_notes)}")

    # ===== 완료 =====
    total = len(my_cards) + sum(len(ag.get("card_ids",[])) for ag in agent_map.values()) + len(client_cards)
    print(f"\n{'='*60}")
    print(f"완료!")
    print(f"  내 매물: {len(my_cards)}건 (사진 포함)")
    print(f"  중개사: {len(agent_map)}명 × 200건 = {sum(len(ag.get('card_ids',[])) for ag in agent_map.values())}건")
    print(f"  공유방: {len(agent_map)}개")
    print(f"  손님: {len(client_cards)}명")
    print(f"  메모: {len(all_notes)}건")
    print(f"  총 카드: {total}건")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
