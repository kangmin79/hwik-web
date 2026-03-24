# -*- coding: utf-8 -*-
"""
휙 테스트 데이터 생성 스크립트 v2
- 가상 중개사 3명의 매물 24개 (본인 계정으로 생성)
- 각 매물에 사진 3장
- 공유방 3개 생성 + 매물 공유
"""

import os, sys, json, uuid, random, requests
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

SUPABASE_URL = "https://api.hwik.kr"

# .env 로드
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_SERVICE_KEY:
    print("SUPABASE_SERVICE_ROLE_KEY missing"); sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

MY_USER_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"
MY_PHONE = "01047632531"

PHOTO_PATHS = [
    r"C:\Users\강동욱\Desktop\7.png",
    r"C:\Users\강동욱\Desktop\1 - 복사본 (13).png",
    r"C:\Users\강동욱\Desktop\3.png",
]

# 가상 중개사 정보 (profiles 생성 안 함, 카드 안에만 넣음)
AGENTS = [
    {"name": "한강공인중개사", "agent_name": "김영수", "phone": "010-1111-2222"},
    {"name": "미래부동산", "agent_name": "이지은", "phone": "010-3333-4444"},
    {"name": "열린공인중개사", "agent_name": "박성호", "phone": "010-5555-6666"},
]

# 매물 템플릿 (3명 x 8종 = 24개)
CARDS_DATA = [
    # ── 한강공인중개사 (마포구) ──
    {"agent_idx":0, "type":"매매","complex":"래미안 푸르지오","location":"마포구 공덕동","area":"32평","floor":"105동 15층","price":"12억 5,000","price_number":125000,"features":["남향","역세권","올수리","즉시입주"],"category":"apartment","comment":"공덕역 도보 3분, 한강뷰 일부 보이는 로얄층이에요. 올수리라 바로 입주 가능합니다.","memo":"1508호, 집주인 010-9876-5432, 융자 없음, 급매"},
    {"agent_idx":0, "type":"전세","complex":"마포 래미안","location":"마포구 도화동","area":"24평","floor":"103동 8층","price":"5억 5,000","price_number":55000,"features":["역세권","올수리","즉시입주","베란다확장"],"category":"apartment","comment":"도화역 5분 거리, 깨끗하게 수리되어 있어요. 신혼부부한테 딱이에요.","memo":"803호, 임대인 010-2222-3333, 2년 계약 선호"},
    {"agent_idx":0, "type":"월세","complex":"합정 메세나폴리스","location":"마포구 합정동","area":"18평","floor":"12층","price":"보증금3,000/월120","price_number":120,"features":["역세권","풀옵션","고층"],"category":"apartment","comment":"합정역 바로 앞이에요. 젊은 직장인들한테 인기 많은 단지예요.","memo":"1203호, 임대인 010-7777-8888, 1년 계약도 가능"},
    {"agent_idx":0, "type":"매매","complex":"마포 오벨리스크","location":"마포구 상암동","area":"12평","floor":"10층","price":"2억 8,000","price_number":28000,"features":["역세권","풀옵션","수익률5%"],"category":"officetel","comment":"월세 수익률 5% 이상 나오는 투자용 매물이에요.","memo":"1003호, 현재 임차인 있음 (월세 90만원)"},
    {"agent_idx":0, "type":"전세","complex":"합정 메트로오피스텔","location":"마포구 합정동","area":"10평","floor":"4층","price":"1억 8,000","price_number":18000,"features":["역세권","풀옵션","즉시입주"],"category":"officetel","comment":"합정역 2분, 혼자 살기 딱 좋은 크기예요. 풀옵션이라 짐만 들어오면 돼요.","memo":"401호, 임대인 010-4444-5555, 반려동물 소형 가능"},
    {"agent_idx":0, "type":"월세","complex":"공덕 리버오피스텔","location":"마포구 공덕동","area":"8평","floor":"3층","price":"보증금500/월55","price_number":55,"features":["역세권","풀옵션"],"category":"officetel","comment":"공덕역 초역세권, 직장인 출퇴근용으로 딱이에요.","memo":"302호, 임대인 직접 관리, 연락 잘 됨"},
    {"agent_idx":0, "type":"전세","complex":"합정 투룸빌라","location":"마포구 합정동","area":"15평","floor":"3층","price":"2억 2,000","price_number":22000,"features":["투룸","올수리","역세권"],"category":"room","comment":"합정역 도보 8분, 조용한 주택가에 있어요. 투룸이라 넉넉해요.","memo":"3층, 집주인 010-8888-9999, 여성 선호"},
    {"agent_idx":0, "type":"월세","complex":"합정 원룸","location":"마포구 합정동","area":"7평","floor":"2층","price":"보증금300/월40","price_number":40,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"합정역 가까운 가성비 원룸이에요. 대학생/사회초년생 추천!","memo":"2층, 집주인 직접 관리, 월세 연체 시 즉시 퇴거 조건"},

    # ── 미래부동산 (강남구) ──
    {"agent_idx":1, "type":"매매","complex":"아크로리버파크","location":"강남구 반포동","area":"45평","floor":"112동 22층","price":"38억","price_number":380000,"features":["남향","한강뷰","신축","풀옵션"],"category":"apartment","comment":"한강뷰가 정말 시원하게 들어오는 매물이에요. 이 단지에서 이 가격은 드문 기회예요.","memo":"2205호, 집주인 부부 해외 이주, 네고 가능 5천만원"},
    {"agent_idx":1, "type":"전세","complex":"대치 삼성래미안","location":"강남구 대치동","area":"33평","floor":"105동 12층","price":"12억","price_number":120000,"features":["학군우수","남향","주차가능"],"category":"apartment","comment":"대치동 학원가 도보권이에요. 전세 매물이 많이 없어서 서두르세요.","memo":"1203호, 전세보험 가입 가능, 임대인 협조적"},
    {"agent_idx":1, "type":"월세","complex":"역삼 아이파크","location":"강남구 역삼동","area":"22평","floor":"7층","price":"보증금5,000/월150","price_number":150,"features":["역세권","신축","주차가능"],"category":"apartment","comment":"역삼역 3분거리, 회사 다니기 너무 좋아요. 신축이라 깨끗해요.","memo":"703호, 반려동물 불가, 임대인 까다로움"},
    {"agent_idx":1, "type":"매매","complex":"강남 오피스텔타워","location":"강남구 논현동","area":"15평","floor":"8층","price":"4억 2,000","price_number":42000,"features":["역세권","신축","빌트인"],"category":"officetel","comment":"논현역 초역세권, 1인 가구한테 완벽한 매물이에요.","memo":"805호, 공실, 매도인 급매 원함, 네고 2천 가능"},
    {"agent_idx":1, "type":"전세","complex":"선릉 SK오피스텔","location":"강남구 역삼동","area":"14평","floor":"11층","price":"2억 5,000","price_number":25000,"features":["역세권","빌트인","고층"],"category":"officetel","comment":"선릉역 도보 5분, IT 회사 다니는 분들 많이 찾아요.","memo":"1102호, 전세보험 필수, 임대인 요청"},
    {"agent_idx":1, "type":"월세","complex":"강남 스타오피스텔","location":"강남구 신논현동","area":"11평","floor":"9층","price":"보증금1,000/월80","price_number":80,"features":["역세권","빌트인","신축"],"category":"officetel","comment":"신논현역 3분, 강남 직장인 최적의 위치예요.","memo":"901호, 여성 전용 층, 보안 철저"},
    {"agent_idx":1, "type":"전세","complex":"역삼 신축원룸","location":"강남구 역삼동","area":"8평","floor":"4층","price":"1억 5,000","price_number":15000,"features":["원룸","신축","풀옵션"],"category":"room","comment":"역삼역 5분, 올해 신축이라 모든 게 새거예요.","memo":"4층, 신축이라 하자보수 가능, 집주인 협조적"},
    {"agent_idx":1, "type":"월세","complex":"강남 쓰리룸","location":"강남구 논현동","area":"20평","floor":"3층","price":"보증금2,000/월100","price_number":100,"features":["쓰리룸","주차가능","올수리"],"category":"room","comment":"논현동 쓰리룸, 가족이나 룸메이트와 함께 살기 좋아요.","memo":"3층, 집주인 010-6666-7777, 장기 계약 시 월세 할인 가능"},

    # ── 열린공인중개사 (송파구) ──
    {"agent_idx":2, "type":"매매","complex":"잠실 엘스","location":"송파구 잠실동","area":"33평","floor":"108동 18층","price":"22억 8,000","price_number":228000,"features":["남동향","학군우수","역세권","주차2대"],"category":"apartment","comment":"학군이랑 교통 다 잡은 매물이에요. 아이 있는 가정에 딱이에요.","memo":"1802호, 집주인 010-1234-0000, 이번 달 계약 원함"},
    {"agent_idx":2, "type":"전세","complex":"잠실 리센츠","location":"송파구 잠실동","area":"28평","floor":"106동 10층","price":"8억 5,000","price_number":85000,"features":["역세권","올수리","베란다확장"],"category":"apartment","comment":"잠실역 도보 7분, 석촌호수 산책 가능한 최고의 입지예요.","memo":"1008호, 임대인 직장인, 주말 방문만 가능"},
    {"agent_idx":2, "type":"월세","complex":"잠실 트리지움","location":"송파구 잠실동","area":"20평","floor":"9층","price":"보증금4,000/월130","price_number":130,"features":["남향","올수리","역세권"],"category":"apartment","comment":"잠실 생활권의 합리적인 월세 매물이에요. 바로 입주 가능합니다.","memo":"905호, 즉시입주, 임대인 해외 거주 (관리인 통해 연락)"},
    {"agent_idx":2, "type":"매매","complex":"송파 오피스텔프라자","location":"송파구 문정동","area":"13평","floor":"6층","price":"3억 1,000","price_number":31000,"features":["역세권","풀옵션","테라스"],"category":"officetel","comment":"문정법조단지 인근, 직장인 임차 수요가 꾸준해요.","memo":"603호, 세입자 계약 6개월 남음, 승계 가능"},
    {"agent_idx":2, "type":"전세","complex":"잠실 나루오피스텔","location":"송파구 잠실동","area":"11평","floor":"7층","price":"2억","price_number":20000,"features":["역세권","풀옵션","신축"],"category":"officetel","comment":"잠실나루역 바로 앞, 교통 최고예요.","memo":"702호, 즉시입주, 이전 세입자 깨끗하게 사용"},
    {"agent_idx":2, "type":"월세","complex":"송파 그린오피스텔","location":"송파구 가락동","area":"9평","floor":"5층","price":"보증금500/월60","price_number":60,"features":["역세권","풀옵션","주차가능"],"category":"officetel","comment":"가락시장역 도보 5분, 생활 인프라 좋아요.","memo":"503호, 주차 1대 포함, 추가 주차 불가"},
    {"agent_idx":2, "type":"전세","complex":"잠실 투룸빌라","location":"송파구 잠실동","area":"13평","floor":"2층","price":"2억","price_number":20000,"features":["투룸","베란다확장","주차가능"],"category":"room","comment":"잠실 생활권 투룸, 가성비 최고예요.","memo":"2층, 반려동물 소형 가능, 주차 1대"},
    {"agent_idx":2, "type":"월세","complex":"송파 투룸","location":"송파구 문정동","area":"12평","floor":"4층","price":"보증금1,000/월65","price_number":65,"features":["투룸","풀옵션","역세권"],"category":"room","comment":"문정역 도보 3분, 교통 편하고 주변에 먹거리 많아요.","memo":"4층, 여성 전용, 1층에 CCTV 설치됨"},

    # ── 추가 매물: 다양한 지역/타입/특징 ──
    # 서초구
    {"agent_idx":1, "type":"전세","complex":"우남푸루미아","location":"서초구 반포동","area":"50평","floor":"117동 18층","price":"3억","price_number":30000,"features":["서향","베란다확장","동향","즉시입주"],"category":"apartment","comment":"반포 생활권, 넓은 50평 대형 아파트예요.","memo":"1802호"},
    {"agent_idx":1, "type":"매매","complex":"한화꿈에그린","location":"동대문구 전농동","area":"29평","floor":"104동","price":"16억","price_number":160000,"features":["학군좋음"],"category":"apartment","comment":"전농동 학원가 인접, 실거주 추천이에요.","memo":""},
    {"agent_idx":0, "type":"매매","complex":"e편한세상","location":"마포구 연남동","area":"63평","floor":"105동 12층","price":"21억","price_number":210000,"features":["역세권","공원뷰","풀옵션","즉시입주"],"category":"apartment","comment":"연남동 인기 단지, 공원뷰 대형평수예요.","memo":""},
    # 상가
    {"agent_idx":0, "type":"매매","complex":"마포 1층 상가","location":"마포구 서교동","area":"25평","floor":"1층","price":"8억","price_number":80000,"features":["대로변","주차가능","1층"],"category":"commercial","comment":"홍대입구역 유동인구 많은 1층 상가예요.","memo":"현재 카페 임차, 월세 250만원 수익"},
    {"agent_idx":2, "type":"월세","complex":"잠실 상가","location":"송파구 잠실동","area":"15평","floor":"1층","price":"보증금5,000/월200","price_number":200,"features":["역세권","1층","대로변"],"category":"commercial","comment":"잠실역 대로변 1층, 모든 업종 가능해요.","memo":"권리금 3000만원 별도"},
    # 사무실
    {"agent_idx":1, "type":"월세","complex":"강남 사무실","location":"강남구 역삼동","area":"30평","floor":"5층","price":"보증금3,000/월180","price_number":180,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"역삼역 도보 3분, IT기업 밀집지역 사무실이에요.","memo":"관리비 별도 30만원"},
    {"agent_idx":0, "type":"전세","complex":"마포 사무실","location":"마포구 공덕동","area":"20평","floor":"3층","price":"1억 5,000","price_number":15000,"features":["역세권","엘리베이터"],"category":"office","comment":"공덕역 인근, 소규모 사무실로 딱이에요.","memo":"2인~5인 사무실 적합"},
    # 애견가능 / 특수 태그
    {"agent_idx":2, "type":"월세","complex":"송파 펫빌라","location":"송파구 가락동","area":"18평","floor":"2층","price":"보증금1,500/월70","price_number":70,"features":["애견가능","투룸","올수리","정원"],"category":"room","comment":"반려동물 OK! 1층에 작은 정원이 있어요.","memo":"대형견도 가능, 집주인 반려인"},
    # 복층/루프탑
    {"agent_idx":0, "type":"월세","complex":"연남 복층빌라","location":"마포구 연남동","area":"22평","floor":"3~4층","price":"보증금2,000/월90","price_number":90,"features":["복층","루프탑","올수리","즉시입주"],"category":"room","comment":"연남동 핫플 골목, 복층+루프탑 구조 매력적이에요.","memo":"루프탑에서 한강뷰 살짝 보임"},

    # ══════ 손님 요청 (type: 손님) ══════
    {"agent_idx":0, "type":"손님","complex":"","location":"마포구","area":"20~30평","floor":"","price":"전세 5억 이내","price_number":50000,"features":["역세권","올수리","아파트"],"category":"apartment","comment":"","memo":"김OO 손님, 010-1234-5678, 4월 입주 희망, 초등학교 근처 원함"},
    {"agent_idx":0, "type":"손님","complex":"","location":"마포구 합정동","area":"10평 이내","floor":"","price":"월세 보증금 1000 이하/월50 이하","price_number":50,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"","memo":"이OO 손님(대학생), 010-2345-6789, 3월 말 입주, 여성전용 선호"},
    {"agent_idx":1, "type":"손님","complex":"","location":"강남구","area":"30평 이상","floor":"","price":"매매 15억~25억","price_number":200000,"features":["아파트","학군우수","주차가능"],"category":"apartment","comment":"","memo":"박OO 손님, 010-3456-7890, 대치동 학원가 선호, 초5+중2 자녀"},
    {"agent_idx":1, "type":"손님","complex":"","location":"강남구 역삼동","area":"15평 이내","floor":"","price":"전세 2억 이내","price_number":20000,"features":["오피스텔","역세권","신축"],"category":"officetel","comment":"","memo":"최OO 손님(직장인), 010-4567-8901, 5월 입주, 회사 역삼역 근처"},
    {"agent_idx":2, "type":"손님","complex":"","location":"송파구","area":"25~35평","floor":"","price":"전세 8억~12억","price_number":100000,"features":["아파트","역세권","학군우수"],"category":"apartment","comment":"","memo":"정OO 손님, 010-5678-9012, 잠실/방이 선호, 7월 입주 예정, 초3 자녀"},
    {"agent_idx":2, "type":"손님","complex":"","location":"송파구 문정동","area":"20평 이내","floor":"","price":"월세 보증금 2000/월80 이하","price_number":80,"features":["투룸","역세권","주차가능"],"category":"room","comment":"","memo":"한OO 손님(신혼부부), 010-6789-0123, 6월 입주, 주차 필수"},
]


def upload_photos(card_id):
    urls = []
    for i, path in enumerate(PHOTO_PATHS):
        if not os.path.exists(path):
            print(f"  사진 없음: {path}")
            continue
        with open(path, "rb") as f:
            data = f.read()
        storage_path = f"cards/{card_id}/{i}_{int(datetime.now().timestamp()*1000)}.png"
        resp = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/photos/{storage_path}",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "image/png"},
            data=data
        )
        if resp.status_code in (200, 201):
            urls.append(f"{SUPABASE_URL}/storage/v1/object/public/photos/{storage_path}")
            print(f"  photo {i+1} OK")
        else:
            print(f"  photo {i+1} FAIL: {resp.status_code}")
    return urls


def main():
    print("="*60)
    print("TEST DATA GENERATOR v2")
    print("="*60)

    # 1. 카드 생성
    print(f"\n--- Creating {len(CARDS_DATA)} cards ---")
    card_ids_by_agent = {0:[], 1:[], 2:[]}

    for i, cd in enumerate(CARDS_DATA):
        agent = AGENTS[cd["agent_idx"]]
        card_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=12))

        print(f"\n[{i+1}/{len(CARDS_DATA)}] {agent['name']} | {cd['type']} {cd['complex']} {cd['price']}")

        # 사진 업로드
        photos = upload_photos(card_id)

        card = {
            "id": card_id,
            "agent_id": MY_USER_ID,  # 본인 계정으로 생성 (FK 제약 회피)
            "style": "a",
            "color": "mint",
            "property": {
                "type": cd["type"],
                "price": cd["price"],
                "location": cd["location"],
                "complex": cd["complex"],
                "area": cd["area"],
                "floor": cd["floor"],
                "features": cd["features"],
                "category": cd["category"],
            },
            "agent": {
                "name": agent["name"],
                "business_name": agent["name"],
                "phone": agent["phone"],
            },
            "private_note": {"memo": cd["memo"]},
            "agent_comment": cd["comment"],
            "search_text": f"{cd['type']} {cd['price']} {cd['location']} {cd['complex']} {cd['area']} {cd['floor']} {' '.join(cd['features'])}",
            "price_number": cd["price_number"],
            "photos": photos if photos else None,
            "trade_status": random.choice(["계약가능", "계약가능", "계약가능", "계약중"]),
            "created_at": (datetime.now() - timedelta(days=random.randint(0, 14))).isoformat()
        }

        resp = requests.post(f"{SUPABASE_URL}/rest/v1/cards", headers=HEADERS, json=card)
        if resp.status_code in (200, 201):
            print(f"  CARD OK: {card_id}")
            card_ids_by_agent[cd["agent_idx"]].append(card_id)
        else:
            print(f"  CARD FAIL: {resp.status_code} {resp.text[:100]}")

    # 2. 공유방 생성 + 매물 공유
    print(f"\n--- Creating share rooms ---")
    for idx, agent in enumerate(AGENTS):
        room_id = str(uuid.uuid4())
        room_name = f"{agent['name']} 매물공유"

        # 공유방 생성
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/share_rooms", headers=HEADERS, json={
            "id": room_id, "name": room_name, "owner_id": MY_USER_ID
        })
        if resp.status_code in (200, 201):
            print(f"  ROOM OK: {room_name}")
        else:
            print(f"  ROOM FAIL: {resp.status_code} {resp.text[:100]}")
            continue

        # 방장 등록
        requests.post(f"{SUPABASE_URL}/rest/v1/share_room_members", headers=HEADERS, json={
            "room_id": room_id, "member_id": MY_USER_ID, "invited_phone": MY_PHONE,
            "status": "accepted", "role": "owner", "accepted_at": datetime.now().isoformat()
        })

        # 매물 공유
        for cid in card_ids_by_agent[idx]:
            requests.post(f"{SUPABASE_URL}/rest/v1/card_shares", headers=HEADERS, json={
                "card_id": cid, "room_id": room_id, "shared_by": MY_USER_ID
            })
        print(f"  SHARED {len(card_ids_by_agent[idx])} cards")

    print(f"\n{'='*60}")
    print(f"DONE! {len(CARDS_DATA)} cards + 3 rooms")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
