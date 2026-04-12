# -*- coding: utf-8 -*-
"""
match_apt_seq.py — trade_raw_v2.apt_seq → apartments.apt_seq 연결

K-apt aptSeq 형식: "11260-83" (lawd_cd앞5자리-순번)
국토부 실거래 aptSeq 형식: "11260-83" (동일)

동작:
  1. trade_raw_v2의 고유 apt_seq 목록 추출
  2. apartments에서 apt_seq가 없는 단지 조회
  3. K-apt BassInfo 재조회로 aptSeq 확보 → apartments.apt_seq 업데이트
  4. 매칭률 보고

사용법:
  python match_apt_seq.py               # apartments 전체
  python match_apt_seq.py --sigungu 11260,11710  # 특정 구만
  python match_apt_seq.py --dry         # DB 저장 안 하고 확인만
"""
import os, sys, ssl, time, argparse, json
import urllib.request, urllib.parse
import urllib3, requests
from requests.adapters import HTTPAdapter

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()

if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

GOV_KEY      = os.environ.get("GOV_SERVICE_KEY", "")
SUPABASE_URL = "https://jqaxejgzkchxbfzgzyzi.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BASS_URL     = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"

if not GOV_KEY:   sys.exit("❌ GOV_SERVICE_KEY 없음")
if not SUPABASE_KEY: sys.exit("❌ SUPABASE_SERVICE_ROLE_KEY 없음")


class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://", TLSAdapter())
session.verify = False


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


def fetch_bass_apt_seq(kapt_code: str) -> str | None:
    """K-apt BassInfo에서 aptSeq 조회"""
    try:
        r = session.get(BASS_URL, params={
            "serviceKey": GOV_KEY, "kaptCode": kapt_code, "_type": "json"
        }, timeout=15)
        body = r.json().get("response", {}).get("body", {})
        item = body.get("item")
        if isinstance(item, list):
            item = item[0] if item else {}
        return (item or {}).get("aptSeq") or None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sigungu", type=str, default=None, help="쉼표 구분 구 코드")
    parser.add_argument("--dry", action="store_true", help="DB 저장 안 하고 확인만")
    args = parser.parse_args()

    # 1. apt_seq 없는 apartments 조회
    params = {"select": "kapt_code,kapt_name,sgg,lawd_cd", "apt_seq": "is.null", "limit": "5000"}
    if args.sigungu:
        codes = [c.strip() for c in args.sigungu.split(",")]
        if len(codes) == 1:
            params["lawd_cd"] = f"eq.{codes[0]}"
        # 복수 구는 반복 조회
    apts = []
    if args.sigungu and len(codes) > 1:
        for code in codes:
            rows = supa_get("apartments", {"select": "kapt_code,kapt_name,sgg,lawd_cd",
                                           "apt_seq": "is.null", "lawd_cd": f"eq.{code}", "limit": "5000"})
            apts.extend(rows)
    else:
        apts = supa_get("apartments", params)

    print(f"apt_seq 없는 단지: {len(apts)}개")
    if args.dry:
        print("(dry 모드)")

    ok = fail = skip = 0
    for i, apt in enumerate(apts, 1):
        kc   = apt["kapt_code"]
        name = apt.get("kapt_name", "")
        sgg  = apt.get("sgg", "")

        # K-apt API 형식 kapt_code만 처리 (A로 시작)
        if not kc.startswith("A"):
            skip += 1
            print(f"  [{i}/{len(apts)}] SKIP {sgg} {name} ({kc}) — 구버전 ID")
            continue

        apt_seq = fetch_bass_apt_seq(kc)
        if not apt_seq:
            fail += 1
            print(f"  [{i}/{len(apts)}] ❌ {sgg} {name}: aptSeq 없음")
        else:
            if not args.dry:
                supa_patch("apartments", "kapt_code", kc, {"apt_seq": apt_seq})
            ok += 1
            print(f"  [{i}/{len(apts)}] ✅ {sgg} {name}: {apt_seq}")

        time.sleep(0.05)

    print(f"\n{'='*50}")
    print(f"완료: 성공 {ok} / 실패 {fail} / 스킵(구버전) {skip}")

    # 2. 매칭률 확인
    total_apts = supa_get("apartments", {"select": "kapt_code", "limit": "1"})
    print(f"\n매칭률 확인은 DB에서 직접: SELECT COUNT(*) FROM apartments WHERE apt_seq IS NOT NULL;")


if __name__ == "__main__":
    main()
