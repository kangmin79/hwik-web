# 다음 세션 할 일 (2026-04-16 오후)

## 오늘 완료한 것 (agent.html 완성)
- KakaoTalk 인앱브라우저 RLS 버그 수정 (profiles anon 정책 추가)
- 배경색 크림/아이보리 (#f5f0e8) 변경
- 사진없는 카드 바텀시트 빈공간 200px→72px 축소
- 카카오 1:1 오픈채팅 URL 저장 + 카카오톡 문의 버튼 동작
- 매물정보 클립보드 복사 + 토스트 알림
- hub-new 프로필 설정에 카카오 오픈채팅 URL 입력 필드 추가
- 공유 링크 → agent.html?id=xxx&cards=id1,id2 방식으로 전환
- ?cards= 모드 + 카카오 인앱 → "대화로 돌아가기" 버튼
- 가격/평형 범위 태그 (5천-1억, 15-20평) 손님 화면에서 필터링
- 인앱브라우저 하단바 가림 현상 수정 (safe-area-inset-bottom)

## 현재 흐름 (완성된 것)
- 구글 → danji → agent.html?id=xxx&kapt_code=xxx&type=매매 → 1:1 오픈채팅
- 중개사 직접 전송 → agent.html?id=xxx&cards=id1,id2 → 대화로 돌아가기

## 다음에 할 것

### 1. agent.html 태그 짤림 최종 확인
- 인앱브라우저 하단 패딩 fix 적용됨 → 실제 테스트 필요

### 2. hub-new 내 정보 카카오 오픈채팅 URL 입력 확인
- 새로 가입하는 중개사가 설정할 수 있는지 테스트

### 3. danji → agent.html 연결 (SEO 안정화 후)
- danji 페이지 중개사 링크에 ?kapt_code=&type= 파라미터 추가
- 구독 중인 중개사 매물만 노출 (추후 is_subscribed 컬럼)

### 4. 기존 카드 kapt_code 배치 매칭
- batch_match_kapt.py 실행 (5076개 카드)

## 비즈니스 방향 정리
- 수익: 구독료만 (광고비 제로)
- 구글 유입 시 같은 단지 여러 중개사 → 구독 중인 전체 매물 통합 표시
- SEO 안정화 → 트래픽 → danji → agent.html 순서 유지
