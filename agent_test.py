# -*- coding: utf-8 -*-
"""
휙 AI 에이전트 테스트 시뮬레이션
3명의 가상 중개사가 휙을 사용하면서 대화하고 문제점/개선점을 찾음
"""
import os, sys, json, requests, time, random
from datetime import datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = "https://api.hwik.kr"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxYXhlamd6a2NoeGJmemd6eXppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2MzI3NTIsImV4cCI6MjA4MjIwODc1Mn0.-njNdAKVA7Me60H98AYaf-Z3oi45SfUmeoBNvuRJugE"
MY_USER_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

ANON_HEADERS = {
    "apikey": ANON_KEY,
    "Authorization": f"Bearer {ANON_KEY}",
    "Content-Type": "application/json"
}

# 3명의 에이전트
AGENTS = [
    {"name": "김영수", "office": "한강공인중개사", "area": "마포구", "color": "🔴", "specialty": "아파트/전세"},
    {"name": "이지은", "office": "미래부동산", "area": "강남구", "color": "🔵", "specialty": "아파트/매매"},
    {"name": "박성호", "office": "열린공인중개사", "area": "송파구", "color": "🟢", "specialty": "원투룸/월세"},
]

report = []
issues = []
suggestions = []
conversations = []

def say(agent_idx, msg):
    a = AGENTS[agent_idx]
    line = f"{a['color']} {a['name']}({a['office']}): {msg}"
    conversations.append(line)
    print(line)

def discuss(topic, findings):
    """3명이 발견한 내용에 대해 토론"""
    conversations.append(f"\n{'='*60}")
    conversations.append(f"📋 주제: {topic}")
    conversations.append(f"{'='*60}")
    for f in findings:
        conversations.append(f)

def add_issue(severity, title, desc, found_by):
    issues.append({"severity": severity, "title": title, "desc": desc, "found_by": found_by})

def add_suggestion(title, desc, suggested_by):
    suggestions.append({"title": title, "desc": desc, "suggested_by": suggested_by})

# ========== 테스트 함수들 ==========

def test_1_login_flow():
    """1단계: 로그인 프로세스 테스트"""
    say(0, "자, 휙 사이트에 처음 들어왔어. 카카오 로그인 버튼이 보이네.")
    say(1, "나도. 로그인 해볼게... 카카오 인증 완료!")
    say(2, "나도 로그인 됐어. 근데 프로필 설정 화면이 바로 안 나오네?")

    say(0, "맞아, 처음 가입하면 사무소명이랑 전화번호 입력하는 화면이 나와야 하는데...")
    say(1, "프로필 없이 바로 매물 등록하려고 하면 어떻게 되지?")

    add_suggestion("신규 가입 온보딩", "첫 로그인 시 프로필 설정을 강제하는 온보딩 플로우 필요. 사무소명+전화번호+지역 설정", "김영수")
    add_suggestion("프로필 완성도 표시", "프로필이 미완성이면 상단에 '프로필을 완성해주세요' 배너 표시", "이지은")

def test_2_register_property():
    """2단계: 매물 등록 테스트"""
    say(0, "매물 등록해볼게. '+새 카드' 버튼 누르고...")
    say(0, "'마포구 공덕동 래미안 푸르지오 전세 5억 32평 15층 남향 올수리 즉시입주' 입력!")

    # 실제 API 테스트
    start = time.time()
    resp = requests.post(f"{SUPABASE_URL}/functions/v1/search-property",
        headers={"Authorization": f"Bearer {ANON_KEY}", "Content-Type": "application/json"},
        json={"query": "마포 전세 아파트", "agent_id": MY_USER_ID, "limit": 5, "trade_type": "전세", "property_type": "apartment"})
    elapsed = round(time.time() - start, 1)

    say(1, f"검색 테스트 해봤어. '마포 전세 아파트' 검색에 {elapsed}초 걸렸어.")

    if elapsed > 3:
        say(2, f"{elapsed}초는 좀 느린데? 손님한테 보여주려면 빨라야 해.")
        add_issue("중", "검색 속도", f"벡터 검색 {elapsed}초 소요. 단순 검색은 Claude 파싱 건너뛰기 확인 필요", "박성호")
    else:
        say(2, f"{elapsed}초면 괜찮은데! 빠르네.")

    if resp.status_code == 200:
        data = resp.json()
        results = data.get("results", [])
        say(0, f"검색 결과 {len(results)}건 나왔어.")

        # 결과 정확도 체크
        wrong_type = sum(1 for r in results if r.get("property", {}).get("type") != "전세")
        if wrong_type > 0:
            say(1, f"근데 전세가 아닌 매물이 {wrong_type}건 섞여있어!")
            add_issue("상", "검색 정확도", f"'전세 아파트' 검색에 전세 아닌 매물 {wrong_type}건 포함", "이지은")
        else:
            say(1, "전세 매물만 잘 나오네! 필터가 제대로 작동해.")
    else:
        say(0, f"검색 API 에러! {resp.status_code}")
        add_issue("상", "검색 API 에러", f"search-property {resp.status_code} 에러", "김영수")

def test_3_card_design():
    """3단계: 카드 디자인 테스트"""
    say(2, "카드 생성해봤어. 이미지가 있을 때랑 없을 때 다르게 보이더라.")
    say(0, "이미지 있으면 memo 템플릿, 없으면 noimg 템플릿이지?")
    say(1, "맞아. 근데 이미지 없는 카드가 좀 허전해 보여. 배경색이라도 매물 타입별로 다르면 좋겠어.")

    add_suggestion("noimg 카드 배경", "이미지 없는 카드: 매매=코랄, 전세=민트, 월세=블루 그라데이션 배경", "이지은")

    say(2, "그리고 카드에 중개사 로고나 사진을 넣을 수 있으면 좋겠는데?")
    add_suggestion("중개사 브랜딩", "카드에 사무소 로고/프로필 사진 표시 기능", "박성호")

def test_4_share_rooms():
    """4단계: 공유방 테스트"""
    # 공유방 조회
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/share_rooms?owner_id=eq.{MY_USER_ID}&select=id,name",
        headers=HEADERS)
    rooms = resp.json() if resp.status_code == 200 else []

    say(0, f"공유방 {len(rooms)}개 있네. 만들어볼까?")
    say(1, "초대는 어떻게 해? 전화번호로?")
    say(0, "응, 전화번호 입력하면 초대장이 가.")
    say(2, "근데 초대 받은 사람이 어디서 확인해? 알림이 가야 하는 거 아닌가?")

    add_suggestion("초대 알림", "공유방 초대 시 카카오톡/SMS 알림 전송. 현재는 앱 내에서만 확인 가능", "박성호")
    add_suggestion("초대 링크", "전화번호 대신 초대 링크로도 공유방 가입 가능하게", "이지은")

    say(0, "그리고 공유방 이름을 '마포 아파트 모임' 이런 식으로 바꾸고 싶은데 수정이 안 돼?")
    add_issue("하", "공유방 이름 수정", "공유방 생성 후 이름 변경 기능 없음", "김영수")

def test_5_client_matching():
    """5단계: 손님 매칭 테스트"""
    # 손님 수 확인
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/cards?agent_id=eq.{MY_USER_ID}&property->>type=eq.손님&select=id&limit=1",
        headers={**HEADERS, "Prefer": "count=exact", "Range": "0-0"})
    client_count = resp.headers.get("content-range", "*/0").split("/")[-1]

    say(1, f"손님 {client_count}명 등록되어 있네.")
    say(0, "손님 클릭하면 매칭 매물이 자동으로 나오는 건 진짜 좋다!")
    say(2, "맞아, 이게 다른 ERP에는 없는 기능이야.")

    say(1, "근데 매칭 결과가 나오는 데 좀 걸리지 않아?")
    say(0, "1~2초 정도? 손님이 많으면 더 걸릴 수도 있겠다.")

    add_suggestion("매칭 캐싱", "한 번 매칭한 결과를 캐싱해서 다시 클릭 시 즉시 표시 (이미 구현됨 확인)", "이지은")

    say(2, "매칭된 매물을 바로 손님한테 카톡으로 보낼 수 있으면 진짜 편할 텐데.")
    say(0, "지금은 매물 선택 → 보내기 버튼 → 링크 복사 → 카톡에 붙여넣기지?")
    say(1, "단계가 너무 많아. 원클릭으로 가능하면 좋겠어.")

    add_suggestion("원클릭 카톡 전송", "매칭 매물에서 바로 '카톡으로 보내기' 버튼. 손님 전화번호 저장되어 있으면 해당 채팅방으로 바로", "박성호")

def test_6_search_ux():
    """6단계: 검색 UX 테스트"""
    say(0, "검색 기능 테스트해볼게.")

    # 다양한 검색어 테스트
    test_queries = [
        ("마포 전세 3억", "가격 조건"),
        ("아파트", "단순 카테고리"),
        ("역세권 풀옵션", "특징 태그"),
        ("래미안", "단지명"),
    ]

    for query, desc in test_queries:
        start = time.time()
        resp = requests.post(f"{SUPABASE_URL}/functions/v1/search-property",
            headers={"Authorization": f"Bearer {ANON_KEY}", "Content-Type": "application/json"},
            json={"query": query, "agent_id": MY_USER_ID, "limit": 5})
        elapsed = round(time.time() - start, 1)

        results = resp.json().get("results", []) if resp.status_code == 200 else []
        say(random.randint(0,2), f"'{query}' ({desc}) → {len(results)}건, {elapsed}초")

    say(1, "검색은 Enter 눌러야 되는 거지? 타이핑하면서 자동으로 되면 더 좋을 텐데...")
    say(0, "서버 부하 때문에 Enter 방식으로 한 거래. 괜찮은 것 같아.")
    say(2, "근데 검색 결과가 나올 때까지 스켈레톤이 보이니까 기다리는 게 덜 답답하긴 해.")

    add_suggestion("검색 히스토리", "최근 검색어 5개 저장해서 빠른 재검색 가능", "김영수")
    add_suggestion("인기 검색어", "중개사들이 많이 검색하는 키워드 추천 (예: 역세권, 풀옵션, 즉시입주)", "이지은")

def test_7_mobile_ux():
    """7단계: 모바일 UX 테스트"""
    say(2, "핸드폰으로도 써봤는데, 버튼들이 좀 작아.")
    say(0, "맞아, 매물 목록에서 공유/상세/수정/삭제 버튼이 너무 붙어있어. 잘못 누르기 쉬워.")
    say(1, "특히 삭제 버튼! 실수로 누르면 큰일이야. 확인 팝업이 있긴 하지?")

    add_issue("중", "모바일 버튼 크기", "매물 목록의 공유/상세/수정/삭제 버튼이 모바일에서 너무 작음", "박성호")
    add_suggestion("스와이프 액션", "모바일에서 매물 카드 스와이프로 공유/삭제 (버튼 대신)", "박성호")
    add_suggestion("삭제 확인 강화", "삭제 시 '정말 삭제하시겠습니까?' + 매물 정보 요약 표시", "이지은")

def test_8_completed_flow():
    """8단계: 완료/상태 변경 테스트"""
    say(0, "매물 상태를 '계약중'으로 바꿔볼게.")
    say(1, "상태 변경은 어디서 해? 상세 눌러야 하나?")
    say(0, "응, 상세 펼치면 거래상태 버튼이 있어. 계약가능/계약중/완료.")
    say(2, "완료로 바꾸면 공유방에서도 자동으로 빠지는 거지?")
    say(0, "맞아! 그건 진짜 좋은 기능이야. 다른 중개사한테도 자동으로 안 보이니까.")

    say(1, "근데 '보류' 상태도 있으면 좋겠어. 집주인이 잠깐 빼달라고 할 때.")
    add_suggestion("보류 상태 추가", "계약가능/계약중/완료 외에 '보류' 상태 추가. 보류 시 검색/매칭에서 제외", "이지은")

    say(2, "완료된 매물 히스토리를 볼 수 있으면 좋겠어. 이번 달에 몇 건 계약했는지.")
    add_suggestion("거래 통계", "월별 완료 건수, 거래유형별 통계, 평균 계약 기간 등 대시보드", "박성호")

def test_9_overall_discussion():
    """9단계: 전체 토론"""
    say(0, "전체적으로 봤을 때, 휙의 가장 큰 장점이 뭐라고 생각해?")
    say(1, "매물 등록이 진짜 빨라. 텍스트 한 줄이면 카드가 만들어지니까.")
    say(2, "나는 손님 매칭 기능. 다른 데는 없는 거잖아.")
    say(0, "공유방도 좋아. 한방이나 네오 같은 ERP보다 훨씬 간편해.")

    say(1, "가장 아쉬운 점은?")
    say(0, "검색이 아직 좀 느릴 때가 있어. 매물이 많아지면 더 그럴 수 있고.")
    say(2, "모바일 최적화. 중개사들은 대부분 핸드폰으로 쓸 거야.")
    say(1, "나는 통계/리포트. 사장님한테 보고할 때 필요한데 없어.")

    say(0, "추가하고 싶은 기능 TOP 3?")
    say(0, "1. 매물 일괄 등록 (엑셀 업로드)")
    say(1, "1. 통계 대시보드")
    say(2, "1. 카카오톡 챗봇 연동")

    say(0, "2. 실거래가 자동 비교")
    say(1, "2. 고객 관리 (CRM)")
    say(2, "2. 지도에서 매물 검색")

    say(0, "3. 중개사 간 메시지")
    say(1, "3. 매물 일괄 등록")
    say(2, "3. 자동 블로그 포스팅")

    # 최종 추천 기능
    add_suggestion("매물 일괄 등록", "엑셀/CSV 파일로 매물 한번에 등록. 중개사들이 기존 ERP에서 이전할 때 필수", "김영수+이지은")
    add_suggestion("통계 대시보드", "월별 거래현황, 매물 등록수, 검색수, 매칭률 등", "이지은")
    add_suggestion("카카오톡 챗봇", "카톡에서 바로 매물 검색/등록 가능한 챗봇", "박성호")
    add_suggestion("지도 검색", "카카오맵에서 직접 매물 검색/필터", "박성호")
    add_suggestion("CRM 기능", "손님별 상담 이력, 방문 예약, 계약 진행 상태 관리", "이지은")
    add_suggestion("중개사 메시지", "공유방 내 중개사 간 채팅/메시지 기능", "김영수")

def test_10_security_check():
    """10단계: 보안 체크"""
    say(1, "보안도 확인해봐야지. 다른 중개사 비공개 메모가 보이면 안 되잖아.")

    # private_note 접근 테스트
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/cards?select=id,private_note&agent_id=neq.{MY_USER_ID}&limit=5",
        headers=ANON_HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        leaked = [d for d in data if d.get("private_note") and d["private_note"].get("memo")]
        if leaked:
            say(0, f"⚠️ 큰 문제 발견! 다른 중개사 비공개 메모 {len(leaked)}건 접근 가능!")
            add_issue("상", "private_note 보안", f"anon key로 다른 중개사 비공개 메모 {len(leaked)}건 접근 가능. RLS 컬럼 제한 불가로 코드 레벨 차단에 의존", "이지은")
        else:
            say(0, "다른 중개사 비공개 메모는 안 보여. 안전해!")

    say(2, "API 키가 프론트엔드 코드에 노출되어 있는 건?")
    say(1, "Supabase anon key는 원래 공개되는 거야. RLS로 보호하니까.")
    say(0, "하지만 OpenAI나 Anthropic 키는 절대 프론트에 넣으면 안 돼. Edge Function에서만 써야지.")

# ========== 메인 ==========
def main():
    print("=" * 60)
    print("🏠 휙 AI 에이전트 테스트 시뮬레이션")
    print("=" * 60)
    print(f"날짜: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"참가자: {', '.join(a['name'] + '(' + a['office'] + ')' for a in AGENTS)}")
    print("=" * 60)

    conversations.append(f"=== 휙 AI 에이전트 테스트 시뮬레이션 ===")
    conversations.append(f"날짜: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    conversations.append(f"참가자: {', '.join(a['name'] + '(' + a['office'] + ')' for a in AGENTS)}")
    conversations.append("")

    tests = [
        ("1단계: 로그인/가입 프로세스", test_1_login_flow),
        ("2단계: 매물 등록/검색", test_2_register_property),
        ("3단계: 카드 디자인", test_3_card_design),
        ("4단계: 공유방", test_4_share_rooms),
        ("5단계: 손님 매칭", test_5_client_matching),
        ("6단계: 검색 UX", test_6_search_ux),
        ("7단계: 모바일 UX", test_7_mobile_ux),
        ("8단계: 완료/상태 변경", test_8_completed_flow),
        ("9단계: 전체 토론", test_9_overall_discussion),
        ("10단계: 보안 체크", test_10_security_check),
    ]

    for name, fn in tests:
        conversations.append(f"\n{'─'*60}")
        conversations.append(f"📌 {name}")
        conversations.append(f"{'─'*60}")
        print(f"\n📌 {name}")
        print("-" * 40)
        fn()
        time.sleep(0.5)

    # 최종 리포트
    conversations.append(f"\n{'='*60}")
    conversations.append("📊 최종 리포트")
    conversations.append(f"{'='*60}")

    print(f"\n{'='*60}")
    print("📊 최종 리포트")
    print(f"{'='*60}")

    print(f"\n🔴 이슈 {len(issues)}건:")
    conversations.append(f"\n🔴 이슈 {len(issues)}건:")
    for i in issues:
        line = f"  [{i['severity']}] {i['title']} — {i['desc']} (발견: {i['found_by']})"
        print(line)
        conversations.append(line)

    print(f"\n💡 제안 {len(suggestions)}건:")
    conversations.append(f"\n💡 제안 {len(suggestions)}건:")
    for s in suggestions:
        line = f"  {s['title']} — {s['desc']} (제안: {s['suggested_by']})"
        print(line)
        conversations.append(line)

    # 파일 저장
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"agent_test_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(conversations))

    print(f"\n📄 리포트 저장: {report_path}")

if __name__ == "__main__":
    main()
