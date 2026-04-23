"""오피스텔 재수집 파이프라인.

2026-04-23 DB 손실 사고 재발 방지를 위한 설계 원칙:
  1. Supabase REST limit 1000 상수화 + 페이지네이션 Content-Range 검증
  2. 대량 집계는 DB RPC (앱 레벨 페이지네이션 버그 회피)
  3. 아파트 테이블 접근 전면 차단 (safety_guards.assert_not_apartment_table)
  4. officetel_pyeongs 는 FK 제거 후 보존 (공급면적 v6 데이터 19,807 row)
"""
