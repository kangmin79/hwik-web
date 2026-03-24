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

    # ══════════════════════════════════════════════
    # 카테고리별 추가 매물 (15개씩)
    # ══════════════════════════════════════════════

    # ── 아파트 추가 15개 ──
    {"agent_idx":0,"type":"매매","complex":"목동 신시가지","location":"양천구 목동","area":"34평","floor":"707동 15층","price":"14억","price_number":140000,"features":["남향","학군우수","주차2대"],"category":"apartment","comment":"목동 학원가 도보권, 학부모님께 인기 많아요.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"도곡 렉슬","location":"강남구 도곡동","area":"40평","floor":"103동 20층","price":"14억 5,000","price_number":145000,"features":["남향","고층","주차가능","학군우수"],"category":"apartment","comment":"도곡역 초역세권, 대치 학원가 인접해요.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"헬리오시티","location":"송파구 가락동","area":"25평","floor":"201동 8층","price":"보증금5,000/월130","price_number":130,"features":["역세권","신축","주차가능"],"category":"apartment","comment":"9,510세대 메가단지, 편의시설 완벽해요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"마포 자이","location":"마포구 대흥동","area":"28평","floor":"102동 11층","price":"11억 8,000","price_number":118000,"features":["역세권","올수리","남향"],"category":"apartment","comment":"대흥역 도보 2분, 마포 대장 아파트예요.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"반포 자이","location":"서초구 반포동","area":"42평","floor":"110동 25층","price":"18억","price_number":180000,"features":["한강뷰","남향","고층","주차2대"],"category":"apartment","comment":"한강뷰 끝판왕, 반포 생활권 최고 단지.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"파크리오","location":"송파구 잠실동","area":"35평","floor":"115동 17층","price":"25억","price_number":250000,"features":["남향","역세권","학군우수","올수리"],"category":"apartment","comment":"잠실 학군+교통+생활 3박자 갖춘 단지예요.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"DMC 래미안","location":"마포구 상암동","area":"20평","floor":"104동 6층","price":"보증금3,000/월100","price_number":100,"features":["역세권","올수리","주차가능"],"category":"apartment","comment":"디지털미디어시티역 5분, 방송국 근무자 추천.","memo":""},
    {"agent_idx":1,"type":"매매","complex":"타워팰리스","location":"강남구 도곡동","area":"68평","floor":"G동 52층","price":"55억","price_number":550000,"features":["시티뷰","고층","풀옵션","주차2대"],"category":"apartment","comment":"강남 랜드마크, 시티뷰가 압도적이에요.","memo":""},
    {"agent_idx":2,"type":"전세","complex":"올림픽파크 포레온","location":"송파구 둔촌동","area":"30평","floor":"208동 15층","price":"11억","price_number":110000,"features":["신축","역세권","남향","주차가능"],"category":"apartment","comment":"둔촌주공 재건축, 12,032세대 신축 대단지예요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"성수 자이","location":"성동구 성수동","area":"27평","floor":"103동 9층","price":"13억 5,000","price_number":135000,"features":["역세권","올수리","남동향"],"category":"apartment","comment":"성수역 도보 5분, 핫플 성수동 아파트예요.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"압구정 현대","location":"강남구 압구정동","area":"50평","floor":"11동 8층","price":"15억","price_number":150000,"features":["남향","주차가능","베란다확장"],"category":"apartment","comment":"압구정 로데오 생활권, 명품 학군이에요.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"잠실 레이크팰리스","location":"송파구 잠실동","area":"32평","floor":"106동 12층","price":"보증금8,000/월180","price_number":180,"features":["역세권","남향","올수리"],"category":"apartment","comment":"석촌호수 바로 앞, 호수뷰 가능한 매물이에요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"용산 파크타워","location":"용산구 한남동","area":"45평","floor":"B동 30층","price":"32억","price_number":320000,"features":["한강뷰","고층","풀옵션","시스템에어컨"],"category":"apartment","comment":"한남동 한강뷰 프리미엄, 외국인도 많이 찾아요.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"래미안 목동 아이파크","location":"양천구 목동","area":"38평","floor":"103동 16층","price":"9억","price_number":90000,"features":["학군우수","남향","주차2대","올수리"],"category":"apartment","comment":"목동 학군 최강, 아이 키우기 좋은 환경이에요.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"잠실 주공5단지","location":"송파구 잠실동","area":"25평","floor":"501동 5층","price":"19억","price_number":190000,"features":["역세권","재건축","학군우수"],"category":"apartment","comment":"재건축 추진 중, 투자가치 높은 매물이에요.","memo":""},

    # ── 오피스텔 추가 15개 ──
    {"agent_idx":0,"type":"매매","complex":"마포 트라팰리스","location":"마포구 상암동","area":"16평","floor":"15층","price":"3억 5,000","price_number":35000,"features":["역세권","풀옵션","시스템에어컨"],"category":"officetel","comment":"상암 DMC역 3분, 1인 가구 투자용 최적.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"강남 더힐 오피스텔","location":"강남구 삼성동","area":"18평","floor":"12층","price":"3억 2,000","price_number":32000,"features":["역세권","신축","풀옵션","고층"],"category":"officetel","comment":"삼성역 코엑스 인접, 직장인 최적 입지.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"잠실 캐슬오피스텔","location":"송파구 잠실동","area":"10평","floor":"8층","price":"보증금1,000/월70","price_number":70,"features":["역세권","풀옵션"],"category":"officetel","comment":"잠실역 5분, 가성비 좋은 오피스텔이에요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"공덕 SK리더스뷰","location":"마포구 공덕동","area":"14평","floor":"18층","price":"4억","price_number":40000,"features":["역세권","고층","빌트인"],"category":"officetel","comment":"공덕역 초역세권, 4개 노선 환승 가능.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"역삼 센트럴 오피스텔","location":"강남구 역삼동","area":"12평","floor":"9층","price":"2억 8,000","price_number":28000,"features":["역세권","풀옵션","빌트인"],"category":"officetel","comment":"역삼역 코앞, IT기업 밀집지역이에요.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"문정 법조오피스텔","location":"송파구 문정동","area":"11평","floor":"6층","price":"보증금500/월55","price_number":55,"features":["역세권","풀옵션","신축"],"category":"officetel","comment":"문정법조단지 인접, 법조인 수요 많아요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"홍대 오피스텔","location":"마포구 서교동","area":"9평","floor":"5층","price":"2억 2,000","price_number":22000,"features":["역세권","풀옵션"],"category":"officetel","comment":"홍대입구역 3분, 대학생 임대 수요 풍부.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"논현 프라임오피스텔","location":"강남구 논현동","area":"15평","floor":"10층","price":"2억 5,000","price_number":25000,"features":["역세권","빌트인","주차가능"],"category":"officetel","comment":"논현역 도보 3분, 신논현 더블역세권.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"방이 오피스텔","location":"송파구 방이동","area":"13평","floor":"7층","price":"보증금1,500/월75","price_number":75,"features":["올림픽공원","풀옵션","주차가능"],"category":"officetel","comment":"올림픽공원 도보 5분, 운동하기 좋아요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"연남 오피스텔","location":"마포구 연남동","area":"11평","floor":"4층","price":"2억 5,000","price_number":25000,"features":["풀옵션","올수리"],"category":"officetel","comment":"연남동 카페거리 인접, 분위기 좋은 동네.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"서초 오피스텔","location":"서초구 서초동","area":"14평","floor":"11층","price":"3억","price_number":30000,"features":["역세권","풀옵션","고층"],"category":"officetel","comment":"서초역 법원 인접, 전문직 수요 많아요.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"천호 오피스텔","location":"강동구 천호동","area":"10평","floor":"6층","price":"보증금500/월50","price_number":50,"features":["역세권","풀옵션","신축"],"category":"officetel","comment":"천호역 초역세권, 가성비 최고예요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"이대 오피스텔","location":"서대문구 대현동","area":"8평","floor":"3층","price":"1억 8,000","price_number":18000,"features":["역세권","풀옵션"],"category":"officetel","comment":"이대역 앞, 대학가 임대 수요 안정적.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"잠실새내 오피스텔","location":"송파구 신천동","area":"16평","floor":"14층","price":"3억 5,000","price_number":35000,"features":["역세권","풀옵션","고층","신축"],"category":"officetel","comment":"잠실새내역 2분, 롯데타워 생활권.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"가산 오피스텔","location":"금천구 가산동","area":"9평","floor":"8층","price":"보증금300/월45","price_number":45,"features":["역세권","풀옵션","신축"],"category":"officetel","comment":"가산디지털단지역 3분, IT기업 출퇴근 최적.","memo":""},

    # ── 원투룸/빌라 추가 15개 ──
    {"agent_idx":0,"type":"전세","complex":"연남 빌라","location":"마포구 연남동","area":"12평","floor":"3층","price":"1억 5,000","price_number":15000,"features":["투룸","올수리","역세권"],"category":"room","comment":"연남동 핫플 골목, 깨끗한 투룸이에요.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"신림 원룸","location":"관악구 신림동","area":"6평","floor":"2층","price":"보증금300/월35","price_number":35,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"신림역 3분, 서울대/관악구청 인접.","memo":""},
    {"agent_idx":2,"type":"전세","complex":"천호 투룸","location":"강동구 천호동","area":"14평","floor":"3층","price":"1억 8,000","price_number":18000,"features":["투룸","올수리","주차가능"],"category":"room","comment":"천호역 생활권, 넉넉한 투룸이에요.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"홍대 원룸","location":"마포구 서교동","area":"5평","floor":"4층","price":"보증금500/월45","price_number":45,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"홍대입구역 5분, 대학생 최적 원룸.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"역삼 빌라","location":"강남구 역삼동","area":"16평","floor":"2층","price":"2억 3,000","price_number":23000,"features":["투룸","올수리","주차가능","애견가능"],"category":"room","comment":"역삼역 도보 7분, 반려동물 OK.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"잠실 원룸","location":"송파구 잠실동","area":"7평","floor":"5층","price":"보증금500/월50","price_number":50,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"잠실나루역 인접, 교통 편리해요.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"마포 다세대","location":"마포구 망원동","area":"18평","floor":"2층","price":"3억 8,000","price_number":38000,"features":["투룸","올수리","테라스"],"category":"room","comment":"망원시장 인접, 테라스 있는 투룸.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"서초 빌라","location":"서초구 방배동","area":"20평","floor":"3층","price":"3억","price_number":30000,"features":["쓰리룸","올수리","주차가능"],"category":"room","comment":"방배동 조용한 주택가, 넓은 쓰리룸.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"성수 원룸","location":"성동구 성수동","area":"6평","floor":"3층","price":"보증금500/월55","price_number":55,"features":["원룸","풀옵션","역세권"],"category":"room","comment":"성수역 3분, 성수동 핫플 인접.","memo":""},
    {"agent_idx":0,"type":"전세","complex":"망원 투룸","location":"마포구 망원동","area":"15평","floor":"4층","price":"2억 5,000","price_number":25000,"features":["투룸","베란다확장","올수리"],"category":"room","comment":"망원역 도보 5분, 망리단길 생활권.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"강남 원룸","location":"강남구 역삼동","area":"7평","floor":"6층","price":"보증금1,000/월65","price_number":65,"features":["원룸","풀옵션","역세권","신축"],"category":"room","comment":"강남역 10분, 신축 원룸이에요.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"송파 다세대","location":"송파구 석촌동","area":"22평","floor":"3층","price":"4억 5,000","price_number":45000,"features":["쓰리룸","올수리","주차가능"],"category":"room","comment":"석촌역 인접, 가족 거주용 추천.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"상수 원룸","location":"마포구 상수동","area":"5평","floor":"2층","price":"보증금300/월40","price_number":40,"features":["원룸","풀옵션"],"category":"room","comment":"상수역 1분, 초역세권 원룸.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"논현 빌라","location":"강남구 논현동","area":"18평","floor":"3층","price":"2억 8,000","price_number":28000,"features":["투룸","올수리","주차가능"],"category":"room","comment":"논현역 도보 5분, 강남 생활권 투룸.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"방이 투룸","location":"송파구 방이동","area":"14평","floor":"4층","price":"보증금1,000/월60","price_number":60,"features":["투룸","풀옵션","올림픽공원"],"category":"room","comment":"올림픽공원 도보권, 조용한 동네예요.","memo":""},

    # ── 상가 추가 15개 ──
    {"agent_idx":0,"type":"매매","complex":"홍대 상가","location":"마포구 서교동","area":"20평","floor":"1층","price":"12억","price_number":120000,"features":["1층","대로변","역세권"],"category":"commercial","comment":"홍대 메인거리, 유동인구 최대.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"강남역 상가","location":"강남구 역삼동","area":"15평","floor":"1층","price":"보증금5,000/월300","price_number":300,"features":["1층","대로변","역세권"],"category":"commercial","comment":"강남역 초역세권 1층, 모든 업종 가능.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"잠실역 상가","location":"송파구 잠실동","area":"30평","floor":"1층","price":"15억","price_number":150000,"features":["1층","대로변","역세권","주차가능"],"category":"commercial","comment":"잠실역 대로변, 대형 매장 가능.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"망원 카페상가","location":"마포구 망원동","area":"12평","floor":"1층","price":"보증금2,000/월120","price_number":120,"features":["1층","카페거리"],"category":"commercial","comment":"망리단길 카페거리, 분위기 좋은 상가.","memo":""},
    {"agent_idx":1,"type":"매매","complex":"논현 상가","location":"강남구 논현동","area":"18평","floor":"지하1층","price":"5억","price_number":50000,"features":["역세권"],"category":"commercial","comment":"논현역 인근 지하상가, 가격 대비 넓어요.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"문정 상가","location":"송파구 문정동","area":"25평","floor":"1층","price":"보증금3,000/월180","price_number":180,"features":["1층","역세권","주차가능"],"category":"commercial","comment":"문정법조단지 인접, 음식점 추천.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"연남 상가","location":"마포구 연남동","area":"10평","floor":"1층","price":"6억","price_number":60000,"features":["1층","카페거리"],"category":"commercial","comment":"연남동 경의선숲길 인접, 소형 카페 최적.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"서초 상가","location":"서초구 서초동","area":"20평","floor":"1층","price":"보증금5,000/월250","price_number":250,"features":["1층","대로변","역세권"],"category":"commercial","comment":"서초역 법원 앞, 법률사무소/식당 적합.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"석촌 상가","location":"송파구 석촌동","area":"22평","floor":"1층","price":"9억","price_number":90000,"features":["1층","석촌호수","역세권"],"category":"commercial","comment":"석촌호수 앞, 관광 유동인구 많아요.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"합정 상가","location":"마포구 합정동","area":"15평","floor":"2층","price":"보증금2,000/월100","price_number":100,"features":["역세권"],"category":"commercial","comment":"합정역 상권, 2층이지만 계단 노출 좋아요.","memo":""},
    {"agent_idx":1,"type":"매매","complex":"역삼 상가","location":"강남구 역삼동","area":"35평","floor":"1층","price":"20억","price_number":200000,"features":["1층","대로변","역세권","주차가능"],"category":"commercial","comment":"테헤란로 대로변, 프랜차이즈 입점 적합.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"가락 상가","location":"송파구 가락동","area":"18평","floor":"1층","price":"보증금3,000/월150","price_number":150,"features":["1층","역세권"],"category":"commercial","comment":"가락시장역 인접, 식품/음식 관련 업종 추천.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"상수 상가","location":"마포구 상수동","area":"8평","floor":"1층","price":"4억","price_number":40000,"features":["1층","역세권"],"category":"commercial","comment":"상수역 골목상권, 소형 매장 최적.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"삼성 상가","location":"강남구 삼성동","area":"40평","floor":"1층","price":"보증금1억/월500","price_number":500,"features":["1층","대로변","코엑스"],"category":"commercial","comment":"코엑스 인접, 대형 상가 프리미엄.","memo":""},
    {"agent_idx":2,"type":"매매","complex":"방이 상가","location":"송파구 방이동","area":"14평","floor":"1층","price":"7억","price_number":70000,"features":["1층","먹자골목"],"category":"commercial","comment":"방이먹자골목, 음식점 수요 안정적.","memo":""},

    # ── 사무실 추가 15개 ──
    {"agent_idx":0,"type":"월세","complex":"마포 공유오피스","location":"마포구 서교동","area":"10평","floor":"3층","price":"보증금500/월80","price_number":80,"features":["역세권","엘리베이터"],"category":"office","comment":"홍대입구역 5분, 소규모 스타트업 적합.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"강남 테헤란로 사무실","location":"강남구 역삼동","area":"40평","floor":"8층","price":"보증금5,000/월300","price_number":300,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"테헤란로 IT기업 밀집지역, 10인 사무실.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"잠실 사무실","location":"송파구 잠실동","area":"25평","floor":"6층","price":"보증금3,000/월200","price_number":200,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"잠실역 인근, 교통 편리한 사무실.","memo":""},
    {"agent_idx":0,"type":"전세","complex":"공덕 사무실","location":"마포구 공덕동","area":"15평","floor":"4층","price":"1억","price_number":10000,"features":["역세권","엘리베이터"],"category":"office","comment":"공덕역 4개 노선 환승, 접근성 최고.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"서초 법조사무실","location":"서초구 서초동","area":"30평","floor":"5층","price":"보증금3,000/월250","price_number":250,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"서초 법원단지 인접, 법률사무소 최적.","memo":""},
    {"agent_idx":2,"type":"전세","complex":"문정 사무실","location":"송파구 문정동","area":"20평","floor":"7층","price":"1억 5,000","price_number":15000,"features":["역세권","엘리베이터","신축"],"category":"office","comment":"문정법조단지 신축 사무실, 깨끗해요.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"상암 DMC 사무실","location":"마포구 상암동","area":"50평","floor":"10층","price":"보증금5,000/월400","price_number":400,"features":["역세권","엘리베이터","주차가능","시티뷰"],"category":"office","comment":"DMC 방송국 인접, 미디어 기업 추천.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"삼성 사무실","location":"강남구 삼성동","area":"35평","floor":"9층","price":"3억","price_number":30000,"features":["역세권","엘리베이터","코엑스"],"category":"office","comment":"코엑스 도보 5분, 무역/컨벤션 업종 적합.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"가산 지식산업센터","location":"금천구 가산동","area":"30평","floor":"5층","price":"보증금2,000/월150","price_number":150,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"가산디지털단지 IT기업 밀집, 가성비 최고.","memo":""},
    {"agent_idx":0,"type":"월세","complex":"합정 사무실","location":"마포구 합정동","area":"12평","floor":"3층","price":"보증금1,000/월90","price_number":90,"features":["역세권","엘리베이터"],"category":"office","comment":"합정역 인근, 소규모 디자인/개발 사무실.","memo":""},
    {"agent_idx":1,"type":"전세","complex":"논현 사무실","location":"강남구 논현동","area":"25평","floor":"6층","price":"2억","price_number":20000,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"논현역 더블역세권, 중소기업 사무실.","memo":""},
    {"agent_idx":2,"type":"월세","complex":"송파 사무실","location":"송파구 가락동","area":"18평","floor":"4층","price":"보증금1,500/월120","price_number":120,"features":["역세권","엘리베이터"],"category":"office","comment":"가락시장역 인근, 소규모 사무실.","memo":""},
    {"agent_idx":0,"type":"매매","complex":"마포 지식산업센터","location":"마포구 성산동","area":"35평","floor":"7층","price":"5억","price_number":50000,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"월드컵경기장역 인근, 사무실+작업실 겸용.","memo":""},
    {"agent_idx":1,"type":"월세","complex":"강남 공유오피스","location":"강남구 신사동","area":"8평","floor":"5층","price":"보증금없음/월60","price_number":60,"features":["역세권","엘리베이터"],"category":"office","comment":"신사역 가로수길, 1~2인 프리랜서 적합.","memo":""},
    {"agent_idx":2,"type":"전세","complex":"천호 사무실","location":"강동구 천호동","area":"22평","floor":"5층","price":"1억 2,000","price_number":12000,"features":["역세권","엘리베이터","주차가능"],"category":"office","comment":"천호역 초역세권, 강동구 사무실 가성비.","memo":""},

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
