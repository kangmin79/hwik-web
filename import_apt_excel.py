# -*- coding: utf-8 -*-
"""
공동주택 엑셀 임포트 (기본정보 + 관리비)
- K-apt에서 매주 배포하는 엑셀 파일 → apartments 테이블 업데이트
- 3~6개월마다 새 엑셀 넣고 실행하면 됨

사용법:
  python import_apt_excel.py --basic "D:/다운로드/20260324_단지_기본정보.xlsx"
  python import_apt_excel.py --fee "D:/다운로드/20260327_단지_관리비정보.xlsx"
  python import_apt_excel.py --basic "기본.xlsx" --fee "관리비.xlsx"   # 둘 다
"""

import os
import sys
import json
import argparse
import warnings

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

import pandas as pd
import requests


# ── 환경변수 ──
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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

sb = requests.Session()


# ========================================================
# 1. 기본정보 엑셀 임포트
# ========================================================
def import_basic(filepath: str):
    """기본정보 엑셀 → apartments 테이블 업데이트"""
    print(f"\n📂 기본정보: {filepath}")
    df = pd.read_excel(filepath, header=1)
    print(f"   {len(df)}행 로드")

    # 서울만 필터
    df = df[df["시도"] == "서울특별시"].copy()
    print(f"   서울: {len(df)}개 단지")

    updates = []
    for _, row in df.iterrows():
        kapt_code = str(row.get("단지코드") or "").strip()
        if not kapt_code:
            continue

        parking_total = _int(row.get("총주차대수"))
        top_floor = _int(row.get("최고층수"))
        heating = str(row.get("난방방식") or "").strip()
        builder = str(row.get("시공사") or "").strip()
        elevator = _int(row.get("승강기(승객+화물)")) + _int(row.get("승강기(승객용)"))
        cctv = _int(row.get("CCTV대수"))
        corridor = str(row.get("복도유형") or "").strip()
        mgmt_office_tel = str(row.get("관리사무소 연락처") or "").strip()

        update = {"kapt_code": kapt_code}
        if parking_total > 0:
            update["parking"] = str(parking_total)
        if top_floor > 0:
            update["top_floor"] = str(top_floor)
        if heating:
            update["heating"] = heating
        if builder:
            update["builder"] = builder

        # extra_info에 나머지 저장
        extra = {}
        if elevator > 0:
            extra["elevator"] = elevator
        if cctv > 0:
            extra["cctv"] = cctv
        if corridor:
            extra["corridor"] = corridor
        if mgmt_office_tel:
            extra["mgmt_tel"] = mgmt_office_tel
        if extra:
            update["extra_info"] = extra

        updates.append(update)

    print(f"   업데이트 대상: {len(updates)}개")
    _batch_upsert_apartments(updates)


# ========================================================
# 2. 관리비 엑셀 임포트
# ========================================================
def import_fee(filepath: str):
    """관리비 엑셀 → apartments.mgmt_fee 업데이트 (최근 3개월 세대당 평균)"""
    print(f"\n📂 관리비: {filepath}")
    df = pd.read_excel(filepath, header=1)
    print(f"   {len(df)}행 로드")

    df = df[df["시도"] == "서울특별시"].copy()
    print(f"   서울: {len(df)}행")

    # 단지별 최근 3개월 평균 계산
    # 세대수는 apartments 테이블에서 가져와야 하지만,
    # 여기서는 공용관리비 + 개별사용료 합계를 단지코드별로 집계
    df["총관리비"] = pd.to_numeric(df["공용관리비계"], errors="coerce").fillna(0) + \
                     pd.to_numeric(df["개별사용료계"], errors="coerce").fillna(0)
    df["년월"] = df["발생년월(YYYYMM)"].astype(str)

    # 단지별 최근 3개월
    grouped = df.sort_values("년월", ascending=False).groupby("단지코드")

    # apartments에서 세대수 로드
    households_map = _load_households()

    updates = []
    for kapt_code, group in grouped:
        kapt_code = str(kapt_code).strip()
        recent = group.head(3)
        avg_total = recent["총관리비"].mean()

        if avg_total <= 0:
            continue

        hh = households_map.get(kapt_code, 0)
        if hh <= 0:
            continue

        # 세대당 월 관리비 (원 단위 → 만원 반올림)
        per_household = round(avg_total / hh)

        updates.append({
            "kapt_code": kapt_code,
            "mgmt_fee": per_household,
        })

    print(f"   관리비 계산: {len(updates)}개 단지")
    _batch_upsert_apartments(updates)


# ========================================================
# 유틸
# ========================================================
def _int(val):
    try:
        return int(float(val or 0))
    except:
        return 0


def _load_households() -> dict:
    """apartments 테이블에서 세대수 로드"""
    result = {}
    offset = 0
    while True:
        resp = sb.get(
            f"{SUPABASE_URL}/rest/v1/apartments",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "kapt_code,households", "limit": "1000", "offset": str(offset)},
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        for row in data:
            try:
                hh = int(row.get("households") or 0)
                if hh > 0:
                    result[row["kapt_code"]] = hh
            except:
                pass
        offset += 1000
        if len(data) < 1000:
            break
    print(f"   세대수 로드: {len(result)}개 단지")
    return result


def _batch_upsert_apartments(updates: list):
    """apartments 테이블 배치 업데이트"""
    if not updates:
        return

    success = 0
    fail = 0
    batch_size = 100

    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]

        # PATCH는 배치 불가 → 개별 처리
        for item in batch:
            kapt_code = item.pop("kapt_code")
            resp = sb.patch(
                f"{SUPABASE_URL}/rest/v1/apartments?kapt_code=eq.{kapt_code}",
                headers=SB_HEADERS,
                json=item,
                timeout=15,
            )
            if resp.status_code in (200, 204):
                success += 1
            else:
                fail += 1

        if (i + batch_size) % 500 == 0:
            print(f"   [{i + batch_size}/{len(updates)}] 성공:{success}")

    print(f"   ✅ 완료: 성공 {success} / 실패 {fail}")


# ========================================================
# 메인
# ========================================================
def main():
    parser = argparse.ArgumentParser(description="공동주택 엑셀 임포트")
    parser.add_argument("--basic", default=None, help="기본정보 엑셀 경로")
    parser.add_argument("--fee", default=None, help="관리비 엑셀 경로")
    args = parser.parse_args()

    if not args.basic and not args.fee:
        print("❌ --basic 또는 --fee 중 하나 이상 지정")
        print("   python import_apt_excel.py --basic '기본정보.xlsx' --fee '관리비.xlsx'")
        sys.exit(1)

    print("=" * 50)
    print("📊 공동주택 엑셀 임포트")
    print("=" * 50)

    if args.basic:
        import_basic(args.basic)

    if args.fee:
        import_fee(args.fee)

    print(f"\n{'=' * 50}")
    print("🏁 임포트 완료")
    print("=" * 50)


if __name__ == "__main__":
    main()
