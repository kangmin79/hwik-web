# -*- coding: utf-8 -*-
"""
match_apt_seq.py — apartments.apt_seq 연결
  1차: 도로명(road_nm + bonbun + bubun) + 단지명 유사도
  2차: 지번(umd_nm + jibun) 폴백
  단지별 직접 조회 방식 (페이지네이션 없음)

사용법:
  python match_apt_seq.py --sigungu 11260,11710
  python match_apt_seq.py --region seoul
  python match_apt_seq.py --dry
"""
import os, sys, re, json, argparse, time
import urllib.request, urllib.parse

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

SUPABASE_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_KEY: sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")


def supa_get(path, params):
    url = f"{SUPABASE_URL}/rest/v1/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def supa_patch(table, where_col, where_val, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{where_col}=eq.{urllib.parse.quote(str(where_val))}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PATCH", headers={
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(req) as r:
        return r.status


def normalize_name(name: str) -> str:
    return re.sub(r'[\s\-_·•()（）\[\]{}아파트APT]', '', name or "").lower()


def norm_jibun(j: str) -> str:
    if not j: return ""
    m = re.match(r"^0*(\d+)(?:-0*(\d+))?$", j.strip())
    if m:
        bun = m.group(1)
        ji = m.group(2)
        return f"{bun}-{ji}" if ji and ji not in ("0", "00") else bun
    return j.strip()


def parse_road(doro: str):
    """도로명주소 → (road_nm, bonbun, bubun)"""
    if not doro: return None, None, None
    parts = doro.strip().split()
    for i in range(len(parts)-1, 0, -1):
        m = re.match(r"^(\d+)(?:-(\d+))?$", parts[i])
        if m:
            return parts[i-1], int(m.group(1)), int(m.group(2)) if m.group(2) else 0
    return None, None, None


def vote_seq(rows, kapt_name):
    """rows(apt_seq, apt_nm 포함)에서 빈도 투표 → 최다 apt_seq 반환.
    동점이면 단지명 유사도로 타이브레이크."""
    if not rows: return None

    seq_count = {}  # apt_seq → 등장 횟수
    seq_names = {}  # apt_seq → 단지명 집합
    for r in rows:
        seq = r.get("apt_seq")
        nm  = r.get("apt_nm", "")
        if seq:
            seq_count[seq] = seq_count.get(seq, 0) + 1
            seq_names.setdefault(seq, set()).add(nm)

    if not seq_count: return None
    if len(seq_count) == 1:
        return list(seq_count.keys())[0]

    max_count = max(seq_count.values())
    top_seqs = [s for s, c in seq_count.items() if c == max_count]

    # 1개만 최다면 바로 반환
    if len(top_seqs) == 1:
        return top_seqs[0]

    # 동점이면 단지명 유사도로 타이브레이크 (포함관계 우선)
    norm_kapt = normalize_name(kapt_name)
    for seq in top_seqs:
        for nm in seq_names.get(seq, []):
            norm_trade = normalize_name(nm)
            if norm_kapt == norm_trade or norm_kapt in norm_trade or norm_trade in norm_kapt:
                return seq

    # 그래도 동점이면 첫 번째 (빈도가 같으므로 차이 없음)
    return top_seqs[0]


def lookup_by_road(lawd_cd, road_nm, bonbun, bubun, kapt_name):
    """도로명+번호로 trade_raw_v2 조회 → apt_seq (빈도 투표)"""
    rows = supa_get("trade_raw_v2", {
        "select": "apt_seq,apt_nm",
        "lawd_cd": f"eq.{lawd_cd}",
        "road_nm": f"eq.{road_nm}",
        "road_nm_bonbun": f"eq.{bonbun}",
        "road_nm_bubun": f"eq.{bubun}",
        "limit": "500"
    })
    return vote_seq(rows, kapt_name)


def lookup_by_jibun(lawd_cd, umd_nm, jibun, kapt_name):
    """지번으로 trade_raw_v2 조회 → apt_seq (빈도 투표)"""
    rows = supa_get("trade_raw_v2", {
        "select": "apt_seq,apt_nm",
        "lawd_cd": f"eq.{lawd_cd}",
        "umd_nm":  f"eq.{umd_nm}",
        "jibun":   f"eq.{jibun}",
        "limit": "500"
    })
    return vote_seq(rows, kapt_name)


def lookup_by_name(lawd_cd, kapt_name):
    """단지명 유사도로 trade_raw_v2 조회 → apt_seq.
    도로명/지번 모두 실패 시 3차 폴백 — 지역 내 단지명 집계 후 가장 유사한 apt_seq 반환.
    """
    norm_kapt = normalize_name(kapt_name)
    if not norm_kapt or len(norm_kapt) < 2:
        return None

    # 해당 구 전체 단지명+apt_seq 집계 (중복 제거)
    rows = supa_get("trade_raw_v2", {
        "select": "apt_seq,apt_nm",
        "lawd_cd": f"eq.{lawd_cd}",
        "apt_seq": "not.is.null",
        "limit": "2000"
    })
    if not rows:
        return None

    # apt_seq별 단지명 집계
    seq_names = {}
    for r in rows:
        seq = r.get("apt_seq")
        nm  = r.get("apt_nm", "")
        if seq:
            seq_names.setdefault(seq, set()).add(nm)

    # 완전일치 또는 포함관계 우선
    for seq, names in seq_names.items():
        for nm in names:
            norm_trade = normalize_name(nm)
            if norm_kapt == norm_trade or norm_kapt in norm_trade or norm_trade in norm_kapt:
                return seq

    # 공통 문자 3자 이상 + 최고 점수
    best_seq, best_score = None, 0
    for seq, names in seq_names.items():
        for nm in names:
            norm_trade = normalize_name(nm)
            common = sum(1 for c in norm_kapt if c in norm_trade)
            if common > best_score and common >= 3:
                best_score = common
                best_seq = seq
    return best_seq


def main():
    from regions import (
        SEOUL_GU, INCHEON_GU, GYEONGGI_SI,
        SEJONG_SI, CHUNGBUK_SI, CHUNGNAM_SI,
        JEONBUK_SI, JEONNAM_SI, GYEONGBUK_SI, GYEONGNAM_SI,
        GANGWON_SI, JEJU_SI,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--sigungu", type=str, default=None)
    parser.add_argument("--region",  type=str, default=None)
    parser.add_argument("--dry",     action="store_true")
    args = parser.parse_args()

    if not args.sigungu and not args.region:
        sys.exit("--sigungu 또는 --region 필요")

    if args.sigungu:
        codes = [c.strip() for c in args.sigungu.split(",")]
    elif args.region == "all":
        from regions import BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU
        codes = (list(SEOUL_GU) + list(INCHEON_GU) + list(GYEONGGI_SI)
                 + list(BUSAN_GU) + list(DAEGU_GU) + list(GWANGJU_GU)
                 + list(DAEJEON_GU) + list(ULSAN_GU)
                 + list(SEJONG_SI) + list(CHUNGBUK_SI) + list(CHUNGNAM_SI)
                 + list(JEONBUK_SI) + list(JEONNAM_SI) + list(GYEONGBUK_SI)
                 + list(GYEONGNAM_SI) + list(GANGWON_SI) + list(JEJU_SI))
    else:
        from regions import BUSAN_GU, DAEGU_GU, GWANGJU_GU, DAEJEON_GU, ULSAN_GU
        region_map = {
            "seoul": SEOUL_GU,   "incheon": INCHEON_GU,  "gyeonggi": GYEONGGI_SI,
            "busan": BUSAN_GU,   "daegu": DAEGU_GU,      "gwangju": GWANGJU_GU,
            "daejeon": DAEJEON_GU, "ulsan": ULSAN_GU,    "sejong": SEJONG_SI,
            "chungbuk": CHUNGBUK_SI, "chungnam": CHUNGNAM_SI,
            "jeonbuk": JEONBUK_SI,   "jeonnam": JEONNAM_SI,
            "gyeongbuk": GYEONGBUK_SI, "gyeongnam": GYEONGNAM_SI,
            "gangwon": GANGWON_SI,   "jeju": JEJU_SI,
        }
        codes = list(region_map[args.region])

    print(f"대상: {len(codes)}개 구, dry={args.dry}")

    total_ok1 = total_ok2 = total_ok3 = total_fail = 0

    for code in codes:
        apts = supa_get("apartments", {
            "select": "kapt_code,kapt_name,doro_juso,umd_nm,jibun,sgg",
            "lawd_cd": f"eq.{code}",
            "kapt_code": "like.A*",
            "limit": "2000"
        })
        if not apts: continue

        ok1 = ok2 = ok3 = fail = 0
        sgg_name = apts[0].get("sgg", code)

        for apt in apts:
            kapt_code = apt["kapt_code"]
            kapt_name = apt.get("kapt_name", "")
            doro_juso = apt.get("doro_juso", "")
            umd_nm    = (apt.get("umd_nm") or "").strip()
            jibun     = norm_jibun(apt.get("jibun") or "")

            matched_seq = None

            # ── 1차: 도로명 + 단지명 ──
            road_nm, bonbun, bubun = parse_road(doro_juso)
            if road_nm and bonbun is not None:
                matched_seq = lookup_by_road(code, road_nm, bonbun, bubun, kapt_name)
                if matched_seq:
                    ok1 += 1

            # ── 2차: 지번 폴백 ──
            if not matched_seq and jibun and umd_nm:
                matched_seq = lookup_by_jibun(code, umd_nm, jibun, kapt_name)
                if matched_seq:
                    ok2 += 1

            # ── 3차: 단지명 폴백 (도로명/지번 모두 없는 지역 대응) ──
            if not matched_seq:
                matched_seq = lookup_by_name(code, kapt_name)
                if matched_seq:
                    ok3 += 1

            if matched_seq:
                if not args.dry:
                    supa_patch("apartments", "kapt_code", kapt_code, {"apt_seq": matched_seq})
            else:
                fail += 1
                print(f"  ❌ {umd_nm} {kapt_name}")

            time.sleep(0.05)

        print(f"\n  [{sgg_name}] {len(apts)}개 → 1차(도로명) {ok1} / 2차(지번) {ok2} / 3차(단지명) {ok3} / 실패 {fail}")
        total_ok1 += ok1
        total_ok2 += ok2
        total_ok3 += ok3
        total_fail += fail

    print(f"\n{'='*50}")
    print(f"완료: 1차(도로명) {total_ok1} / 2차(지번) {total_ok2} / 3차(단지명) {total_ok3} / 실패 {total_fail}")
    print(f"총 매칭: {total_ok1 + total_ok2 + total_ok3} / {total_ok1 + total_ok2 + total_ok3 + total_fail}")


if __name__ == "__main__":
    main()
