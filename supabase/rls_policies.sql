-- ═══════════════════════════════════════════════════════════
-- RLS 정책 — 손님 데이터 보안
-- Supabase Dashboard > SQL Editor에서 실행
-- ═══════════════════════════════════════════════════════════

-- 1. cards 테이블 RLS 활성화
ALTER TABLE cards ENABLE ROW LEVEL SECURITY;

-- 본인 카드만 조회/수정/삭제
CREATE POLICY "cards_select_own" ON cards FOR SELECT
  USING (agent_id = auth.uid()::text);

CREATE POLICY "cards_insert_own" ON cards FOR INSERT
  WITH CHECK (agent_id = auth.uid()::text);

CREATE POLICY "cards_update_own" ON cards FOR UPDATE
  USING (agent_id = auth.uid()::text);

CREATE POLICY "cards_delete_own" ON cards FOR DELETE
  USING (agent_id = auth.uid()::text);

-- 공유된 카드 조회 (card_shares 통해 공유된 매물은 볼 수 있음, 손님 카드 제외)
CREATE POLICY "cards_select_shared" ON cards FOR SELECT
  USING (
    property->>'type' != '손님'
    AND id IN (
      SELECT cs.card_id FROM card_shares cs
      JOIN share_room_members srm ON srm.share_rooms_id = cs.room_id
      WHERE srm.user_id = auth.uid()::text
    )
  );

-- 2. client_notes 테이블 RLS 활성화
ALTER TABLE client_notes ENABLE ROW LEVEL SECURITY;

-- 본인 손님의 메모만 조회/수정/삭제
CREATE POLICY "client_notes_select_own" ON client_notes FOR SELECT
  USING (
    client_card_id IN (
      SELECT id FROM cards WHERE agent_id = auth.uid()::text
    )
  );

CREATE POLICY "client_notes_insert_own" ON client_notes FOR INSERT
  WITH CHECK (
    client_card_id IN (
      SELECT id FROM cards WHERE agent_id = auth.uid()::text
    )
  );

CREATE POLICY "client_notes_update_own" ON client_notes FOR UPDATE
  USING (
    client_card_id IN (
      SELECT id FROM cards WHERE agent_id = auth.uid()::text
    )
  );

CREATE POLICY "client_notes_delete_own" ON client_notes FOR DELETE
  USING (
    client_card_id IN (
      SELECT id FROM cards WHERE agent_id = auth.uid()::text
    )
  );

-- 3. match_notifications 테이블 RLS 활성화
ALTER TABLE match_notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "match_notif_select_own" ON match_notifications FOR SELECT
  USING (agent_id = auth.uid()::text);

CREATE POLICY "match_notif_insert_own" ON match_notifications FOR INSERT
  WITH CHECK (agent_id = auth.uid()::text);

CREATE POLICY "match_notif_update_own" ON match_notifications FOR UPDATE
  USING (agent_id = auth.uid()::text);

-- 4. profiles 테이블 RLS 활성화
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_select_own" ON profiles FOR SELECT
  USING (id = auth.uid());

CREATE POLICY "profiles_update_own" ON profiles FOR UPDATE
  USING (id = auth.uid());

-- 5. card_shares 테이블 RLS 활성화
ALTER TABLE card_shares ENABLE ROW LEVEL SECURITY;

-- 본인이 속한 공유방의 공유 내역만 조회
CREATE POLICY "card_shares_select_member" ON card_shares FOR SELECT
  USING (
    room_id IN (
      SELECT share_rooms_id FROM share_room_members WHERE user_id = auth.uid()::text
    )
  );

-- 본인 카드만 공유 가능
CREATE POLICY "card_shares_insert_own" ON card_shares FOR INSERT
  WITH CHECK (
    card_id IN (SELECT id FROM cards WHERE agent_id = auth.uid()::text)
  );

-- 6. share_room_members 테이블 RLS
ALTER TABLE share_room_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "srm_select_member" ON share_room_members FOR SELECT
  USING (
    share_rooms_id IN (
      SELECT share_rooms_id FROM share_room_members WHERE user_id = auth.uid()::text
    )
  );
