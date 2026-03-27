# -*- coding: utf-8 -*-
"""
공동주택 상세정보 수집 (주차대수, 승강기, 복리시설 등)
- 국토교통부 공동주택 상세 정보조회 API (getAphusDtlInfoV4)
- kapt_code 기반으로 apartments 테이블 업데이트

사용법:
  python sync_apt_detail.py           # 주차 데이터 없는 단지만
  python sync_apt_detail.py --all     # 전체 갱신
"""

import os
import sys
import json
import time
import argparse
import ssl
import urllib3
import requests
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

urllib3.disable_warnings()


def _load_env():
    for fname in (".env", "env"):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

GOV_SERVICE_KEY = os.environ.get("GOV_SERVICE_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

DETAIL_API_URL = "http://apis.data.go.kr/1611000/AptBasisInfoServiceV3/getAphusDtlInfoV4"

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

gov_session = requests.Session()
gov_session.mount("https://", TLSAdapter())
gov_session.verify = False

sb_session = requests.Session()


def fetch_detail(kapt_code: str) -> dict | None:
    """상세 API 호출"""
    try:
        resp = gov_session.get(DETAIL_API_URL, params={
            "serviceKey": GOV_SERVICE_KEY,
            "kaptCode": kapt_code,
        }, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        item = data.get("response", {}).get("body", {}).get("item", {})
        if not item:
            return None
        return item
    except Exception as e:
        return None


def load_apartments(only_empty_parking=True):
    """apartments 테이블 로드"""
    all_apts = []
    offset = 0
    limit = 1000
    while True:
        params = {
            "select": "kapt_code,kapt_name,parking,households",
            "limit": str(limit),
            "offset": str(offset),
        }
        if only_empty_parking:
            params["or"] = "(parking.is.null,parking.eq.)"
        resp = sb_session.get(
            f"{SUPABASE_URL}/rest/v1/apartments",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        all_apts.extend(data)
        offset += limit
        if len(data) < limit:
            break
    return all_apts


def update_apartment(kapt_code: str, update_data: dict):
    """apartments 테이블 업데이트"""
    resp = sb_session.patch(
        f"{SUPABASE_URL}/rest/v1/apartments?kapt_code=eq.{kapt_code}",
        headers=SB_HEADERS,
        json=update_data,
        timeout=15,
    )
    return resp.status_code in (200, 204)


def main():
    parser = argparse.ArgumentParser(description="공동주택 상세정보 수집")
    parser.add_argument("--all", action="store_true", help="전체 단지 갱신")
    args = parser.parse_args()

    apts = load_apartments(only_empty_parking=not args.all)
    print(f"📦 대상 단지: {len(apts)}개")

    success = 0
    fail = 0

    for i, apt in enumerate(apts):
        kapt_code = apt["kapt_code"]
        detail = fetch_detail(kapt_code)

        if detail:
            ground = detail.get("kaptdPcnt") or "0"
            underground = detail.get("kaptdPcntu") or "0"
            try:
                total_parking = int(ground) + int(underground)
            except:
                total_parking = 0

            elevator = detail.get("kaptdEcnt") or 0
            welfare = detail.get("welfareFacility") or ""

            parking_str = str(total_parking) if total_parking > 0 else ""

            ok = update_apartment(kapt_code, {"parking": parking_str})
            if ok:
                success += 1
            else:
                fail += 1

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(apts)}] 성공:{success} 실패:{fail}")
        else:
            fail += 1

        # API rate limit 방지
        time.sleep(0.15)

    print(f"\n✅ 완료: 성공 {success} / 실패 {fail} / 전체 {len(apts)}")


if __name__ == "__main__":
    main()
