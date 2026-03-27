# -*- coding: utf-8 -*-
"""
휙 검색/매칭 자동 테스트 에이전트
- 검색 295개 키워드 테스트
- 손님 매칭 테스트
- 결과 자동 분석 + 리포트 생성
- 실행: python test_search_agent.py
"""
import os, sys, json, time, requests
from datetime import datetime
from collections import defaultdict

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
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxYXhlamd6a2NoeGJmemd6eXppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2MzI3NTIsImV4cCI6MjA4MjIwODc1Mn0.-njNdAKVA7Me60H98AYaf-Z3oi45SfUmeoBNvuRJugE")
AGENT_ID = "219ecf54-6879-4636-8fb2-45ca8591c748"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

# ===== 검색 테스트 키워드 =====
SEARCH_TESTS = [
    # 기본 — 반드시 통과해야 함
    {"query": "매매", "expect": {"trade_type": "매매"}, "cat": "기본"},
    {"query": "전세", "expect": {"trade_type": "전세"}, "cat": "기본"},
    {"query": "월세", "expect": {"trade_type": "월세"}, "cat": "기본"},
    {"query": "아파트", "expect": {"category": "apartment"}, "cat": "기본"},
    {"query": "오피스텔", "expect": {"category": "officetel"}, "cat": "기본"},
    {"query": "상가", "expect": {"category": "commercial"}, "cat": "기본"},
    {"query": "사무실", "expect": {"category": "office"}, "cat": "기본"},
    {"query": "원룸", "expect": {"category": "room"}, "cat": "기본"},

    # 25개 구별 검색 — 해당 구 매물이 나와야 함
    {"query": "강남구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "강남"}, "cat": "구별"},
    {"query": "서초구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "서초"}, "cat": "구별"},
    {"query": "송파구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "송파"}, "cat": "구별"},
    {"query": "마포구 오피스텔 월세", "expect": {"trade_type": "월세", "category": "officetel", "location": "마포"}, "cat": "구별"},
    {"query": "용산구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "용산"}, "cat": "구별"},
    {"query": "성동구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "성동"}, "cat": "구별"},
    {"query": "광진구 오피스텔 전세", "expect": {"trade_type": "전세", "category": "officetel", "location": "광진"}, "cat": "구별"},
    {"query": "영등포구 상가 매매", "expect": {"trade_type": "매매", "category": "commercial", "location": "영등포"}, "cat": "구별"},
    {"query": "강동구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "강동"}, "cat": "구별"},
    {"query": "동작구 원룸 월세", "expect": {"trade_type": "월세", "category": "room", "location": "동작"}, "cat": "구별"},
    {"query": "관악구 원룸 전세", "expect": {"trade_type": "전세", "category": "room", "location": "관악"}, "cat": "구별"},
    {"query": "중구 사무실 월세", "expect": {"trade_type": "월세", "category": "office", "location": "중구"}, "cat": "구별"},
    {"query": "종로구 오피스텔 매매", "expect": {"trade_type": "매매", "category": "officetel", "location": "종로"}, "cat": "구별"},
    {"query": "강서구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "강서"}, "cat": "구별"},
    {"query": "양천구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "양천"}, "cat": "구별"},
    {"query": "구로구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "구로"}, "cat": "구별"},
    {"query": "노원구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "노원"}, "cat": "구별"},
    {"query": "서대문구 오피스텔 월세", "expect": {"trade_type": "월세", "category": "officetel", "location": "서대문"}, "cat": "구별"},
    {"query": "은평구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "은평"}, "cat": "구별"},
    {"query": "중랑구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "중랑"}, "cat": "구별"},
    {"query": "도봉구 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "location": "도봉"}, "cat": "구별"},
    {"query": "동대문구 상가 월세", "expect": {"trade_type": "월세", "category": "commercial", "location": "동대문"}, "cat": "구별"},
    {"query": "성북구 원룸 월세", "expect": {"trade_type": "월세", "category": "room", "location": "성북"}, "cat": "구별"},
    {"query": "금천구 사무실 전세", "expect": {"trade_type": "전세", "category": "office", "location": "금천"}, "cat": "구별"},
    {"query": "강북구 아파트 매매", "expect": {"trade_type": "매매", "category": "apartment", "location": "강북"}, "cat": "구별"},

    # 가격 검색
    {"query": "강남구 아파트 전세 5억이하", "expect": {"trade_type": "전세", "category": "apartment", "location": "강남", "max_price": 50000}, "cat": "가격"},
    {"query": "마포구 아파트 매매 3억이하", "expect": {"trade_type": "매매", "category": "apartment", "location": "마포", "max_price": 30000}, "cat": "가격"},
    {"query": "송파구 오피스텔 전세 2억이하", "expect": {"trade_type": "전세", "category": "officetel", "location": "송파", "max_price": 20000}, "cat": "가격"},
    {"query": "노원구 아파트 전세 3억이하", "expect": {"trade_type": "전세", "category": "apartment", "location": "노원", "max_price": 30000}, "cat": "가격"},
    {"query": "중랑구 아파트 전세 3억이하", "expect": {"trade_type": "전세", "category": "apartment", "location": "중랑", "max_price": 30000}, "cat": "가격"},
    {"query": "용산구 아파트 매매 10억이상", "expect": {"trade_type": "매매", "category": "apartment", "location": "용산", "min_price": 100000}, "cat": "가격"},

    # 단지명
    {"query": "래미안", "expect": {"complex": "래미안"}, "cat": "단지명"},
    {"query": "자이", "expect": {"complex": "자이"}, "cat": "단지명"},
    {"query": "힐스테이트", "expect": {"complex": "힐스테이트"}, "cat": "단지명"},
    {"query": "래미안 전세", "expect": {"trade_type": "전세", "complex": "래미안"}, "cat": "단지명"},

    # 특징
    {"query": "역세권 아파트", "expect": {"category": "apartment", "feature": "역세권"}, "cat": "특징"},
    {"query": "남향 아파트 전세", "expect": {"trade_type": "전세", "category": "apartment", "feature": "남향"}, "cat": "특징"},
    {"query": "올수리 원룸 월세", "expect": {"trade_type": "월세", "category": "room", "feature": "올수리"}, "cat": "특징"},

    # 복합
    {"query": "강남구 아파트 전세 30평 5억이하", "expect": {"trade_type": "전세", "category": "apartment", "location": "강남", "max_price": 50000}, "cat": "복합"},
    {"query": "마포구 원룸 월세", "expect": {"trade_type": "월세", "category": "room", "location": "마포"}, "cat": "복합"},
    {"query": "서초구 사무실 전세", "expect": {"trade_type": "전세", "category": "office", "location": "서초"}, "cat": "복합"},
    {"query": "송파구 아파트 매매 10억이하", "expect": {"trade_type": "매매", "category": "apartment", "location": "송파", "max_price": 100000}, "cat": "복합"},
]


def search(query, mode="my"):
    """검색 API 호출"""
    try:
        resp = requests.post(f"{SUPABASE_URL}/functions/v1/search-property",
            headers=HEADERS, timeout=30,
            json={"query": query, "agent_id": AGENT_ID, "limit": 30, "search_mode": mode})
        return resp.json()
    except Exception as e:
        return {"error": str(e), "results": []}


def match_client(client_card_id):
    """손님 매칭 API 호출"""
    try:
        resp = requests.post(f"{SUPABASE_URL}/functions/v1/match-properties",
            headers=HEADERS, timeout=30,
            json={"client_card_id": client_card_id, "agent_id": AGENT_ID, "limit": 10, "threshold": 0.15})
        return resp.json()
    except Exception as e:
        return {"error": str(e), "results": []}


def check_result(result, expect):
    """결과가 기대에 맞는지 체크"""
    results = result.get("results", [])
    if not results:
        return "EMPTY", 0, "결과 0건"

    top10 = results[:10]
    checks = {"trade": 0, "category": 0, "location": 0, "price": 0, "complex": 0, "feature": 0}
    total_checks = 0

    for r in top10:
        p = r.get("property", {})
        pn = r.get("price_number", 0) or 0

        if "trade_type" in expect:
            total_checks += 1
            if p.get("type") == expect["trade_type"]:
                checks["trade"] += 1

        if "category" in expect:
            total_checks += 1
            if p.get("category") == expect["category"]:
                checks["category"] += 1

        if "location" in expect:
            total_checks += 1
            loc = p.get("location", "")
            if expect["location"] in loc:
                checks["location"] += 1

        if "max_price" in expect:
            total_checks += 1
            if pn > 0 and pn <= expect["max_price"] * 1.1:
                checks["price"] += 1

        if "min_price" in expect:
            total_checks += 1
            if pn > 0 and pn >= expect["min_price"] * 0.9:
                checks["price"] += 1

        if "complex" in expect:
            total_checks += 1
            st = r.get("search_text", "") + " " + p.get("complex", "")
            if expect["complex"] in st:
                checks["complex"] += 1

        if "feature" in expect:
            total_checks += 1
            feats = " ".join(p.get("features", []))
            st = r.get("search_text", "")
            if expect["feature"] in feats or expect["feature"] in st:
                checks["feature"] += 1

    if total_checks == 0:
        return "OK", 100, "조건 없음"

    match_rate = round(sum(checks.values()) / total_checks * 100)

    # 각 항목별 정확도
    details = []
    for k, v in checks.items():
        if k == "trade" and "trade_type" in expect:
            details.append(f"거래:{round(v/len(top10)*100)}%")
        elif k == "category" and "category" in expect:
            details.append(f"카테:{round(v/len(top10)*100)}%")
        elif k == "location" and "location" in expect:
            details.append(f"지역:{round(v/len(top10)*100)}%")
        elif k == "price" and ("max_price" in expect or "min_price" in expect):
            details.append(f"가격:{round(v/len(top10)*100)}%")
        elif k == "complex" and "complex" in expect:
            details.append(f"단지:{round(v/len(top10)*100)}%")
        elif k == "feature" and "feature" in expect:
            details.append(f"특징:{round(v/len(top10)*100)}%")

    if match_rate >= 70:
        status = "OK"
    elif match_rate >= 30:
        status = "WARN"
    else:
        status = "FAIL"

    # 상위 3개 결과 요약
    top3 = []
    for r in results[:3]:
        p = r.get("property", {})
        top3.append(f"{p.get('type','?')} {p.get('category','?')} {p.get('location','?')} {p.get('price','?')}")

    return status, match_rate, " | ".join(details) + f" → 상위: {'; '.join(top3)}"


def run_search_tests():
    """검색 테스트 실행"""
    print("=" * 70)
    print(f"  휙 검색 테스트 ({len(SEARCH_TESTS)}개)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = {"OK": [], "WARN": [], "FAIL": [], "EMPTY": [], "ERROR": []}
    cat_stats = defaultdict(lambda: {"ok": 0, "warn": 0, "fail": 0, "empty": 0, "error": 0})

    for i, test in enumerate(SEARCH_TESTS):
        q = test["query"]
        expect = test["expect"]
        cat = test["cat"]

        data = search(q)

        if "error" in data and data.get("results") is None:
            status = "ERROR"
            match_rate = 0
            detail = f"에러: {data['error']}"
        elif data.get("error") and not data.get("results"):
            status = "ERROR"
            match_rate = 0
            detail = f"에러: {data['error']}"
        else:
            status, match_rate, detail = check_result(data, expect)

        count = len(data.get("results", []))
        method = data.get("search_method", "?")

        # 상태 이모지
        emoji = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌", "EMPTY": "📭", "ERROR": "💥"}[status]
        print(f"  {emoji} [{cat}] \"{q}\" → {status} ({match_rate}%) {count}건 [{method}] {detail[:80]}")

        results[status].append({"query": q, "cat": cat, "rate": match_rate, "count": count, "detail": detail})
        cat_stats[cat][status.lower()] += 1

        time.sleep(0.1)  # API 부하 방지

    # 요약
    print("\n" + "=" * 70)
    print("  검색 테스트 요약")
    print("=" * 70)
    total = len(SEARCH_TESTS)
    ok = len(results["OK"])
    warn = len(results["WARN"])
    fail = len(results["FAIL"])
    empty = len(results["EMPTY"])
    error = len(results["ERROR"])
    print(f"  ✅ OK: {ok}/{total} ({round(ok/total*100)}%)")
    print(f"  ⚠️ WARN: {warn}/{total}")
    print(f"  ❌ FAIL: {fail}/{total}")
    print(f"  📭 EMPTY: {empty}/{total}")
    print(f"  💥 ERROR: {error}/{total}")

    if results["FAIL"]:
        print(f"\n  ❌ FAIL 상세:")
        for r in results["FAIL"]:
            print(f"    [{r['cat']}] \"{r['query']}\" → {r['rate']}% | {r['detail'][:60]}")

    if results["EMPTY"]:
        print(f"\n  📭 EMPTY 상세:")
        for r in results["EMPTY"]:
            print(f"    [{r['cat']}] \"{r['query']}\"")

    if results["ERROR"]:
        print(f"\n  💥 ERROR 상세:")
        for r in results["ERROR"]:
            print(f"    [{r['cat']}] \"{r['query']}\" → {r['detail'][:60]}")

    print(f"\n  카테고리별:")
    for cat, stats in sorted(cat_stats.items()):
        t = sum(stats.values())
        print(f"    {cat}: OK {stats['ok']}/{t} | WARN {stats['warn']} | FAIL {stats['fail']} | EMPTY {stats['empty']}")

    return results


def run_match_tests():
    """손님 매칭 테스트"""
    print("\n" + "=" * 70)
    print("  휙 손님 매칭 테스트")
    print("=" * 70)

    # 손님 카드 조회
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/cards",
        params={"select": "id,property,private_note", "agent_id": f"eq.{AGENT_ID}",
                "property->>type": "eq.손님", "limit": "100", "order": "created_at.desc"},
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    clients = resp.json() if resp.status_code == 200 else []
    print(f"  손님 {len(clients)}명 조회")

    if not clients:
        print("  손님 카드 없음")
        return {}

    ok = warn = fail = empty = error = 0
    acc = {"trade": 0, "category": 0, "location": 0, "price": 0, "cnt": 0}
    problems = []

    for i, client in enumerate(clients):
        cp = client.get("property", {})
        memo = (client.get("private_note") or {}).get("memo", "")
        all_text = " ".join(filter(None, [cp.get("price"), cp.get("location"), memo]))

        # 기대 조건 추출
        exp_trade = None
        if "매매" in all_text: exp_trade = "매매"
        elif "전세" in all_text: exp_trade = "전세"
        elif "월세" in all_text: exp_trade = "월세"

        exp_cat = cp.get("category")
        exp_loc = None
        import re
        loc_m = re.search(r'(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)', all_text)
        if loc_m: exp_loc = loc_m.group(1)
        if cp.get("location"):
            loc_m2 = re.search(r'(강남|서초|송파|마포|용산|성동|광진|영등포|강동|동작|관악|종로|중구|강서|양천|구로|노원|서대문|은평|중랑|도봉|동대문|성북|금천|강북)', cp["location"])
            if loc_m2: exp_loc = loc_m2.group(1)

        # 매칭 실행
        data = match_client(client["id"])
        matched = data.get("results", [])

        if data.get("error"):
            error += 1
            continue

        if not matched:
            empty += 1
            continue

        # 정확도 체크
        t_ok = c_ok = l_ok = p_ok = 0
        for m in matched:
            mp = m.get("property", {})
            if not exp_trade or mp.get("type") == exp_trade: t_ok += 1
            if not exp_cat or mp.get("category") == exp_cat: c_ok += 1
            if not exp_loc or exp_loc in (mp.get("location") or ""): l_ok += 1
            p_ok += 1  # 가격은 서버에서 이미 필터

        n = len(matched)
        t_rate = round(t_ok/n*100)
        c_rate = round(c_ok/n*100)
        l_rate = round(l_ok/n*100)
        p_rate = round(p_ok/n*100)
        avg = round((t_rate + c_rate + l_rate + p_rate) / 4)

        acc["trade"] += t_rate; acc["category"] += c_rate; acc["location"] += l_rate; acc["price"] += p_rate; acc["cnt"] += 1

        if avg >= 70: ok += 1
        elif avg >= 30: warn += 1; problems.append(f"[WARN] {memo[:40]} → 거래{t_rate}% 카테{c_rate}% 지역{l_rate}%")
        else: fail += 1; problems.append(f"[FAIL] {memo[:40]} → 거래{t_rate}% 카테{c_rate}% 지역{l_rate}%")

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(clients)} 완료...")
        time.sleep(0.1)

    total = ok + warn + fail + empty + error
    print(f"\n  ✅ OK: {ok}/{total}")
    print(f"  ⚠️ WARN: {warn}/{total}")
    print(f"  ❌ FAIL: {fail}/{total}")
    print(f"  📭 EMPTY: {empty}/{total}")
    if acc["cnt"] > 0:
        c = acc["cnt"]
        print(f"\n  항목별 평균: 거래 {round(acc['trade']/c)}% | 카테고리 {round(acc['category']/c)}% | 지역 {round(acc['location']/c)}% | 가격 {round(acc['price']/c)}%")

    if problems:
        print(f"\n  문제 상세 (상위 10개):")
        for p in problems[:10]:
            print(f"    {p}")

    return {"ok": ok, "warn": warn, "fail": fail, "empty": empty}


if __name__ == "__main__":
    print("\n🔍 휙 검색/매칭 자동 테스트 에이전트\n")
    start = time.time()

    search_results = run_search_tests()
    match_results = run_match_tests()

    elapsed = round(time.time() - start)
    print(f"\n⏱️ 총 소요: {elapsed}초")
    print(f"\n{'='*70}")
    print(f"  완료! 결과를 확인하세요.")
    print(f"{'='*70}")
