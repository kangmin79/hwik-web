-- 보안 수정: 공유 매물 RLS 강화

-- 1. cards_select_shared: 초대 수락한 멤버만 공유 매물 열람 가능
DROP POLICY IF EXISTS "cards_select_shared" ON cards;
CREATE POLICY "cards_select_shared" ON cards FOR SELECT
  USING (
    property->>'type' != '손님'
    AND id IN (
      SELECT cs.card_id FROM card_shares cs
      JOIN share_room_members srm ON srm.room_id = cs.room_id
      WHERE srm.member_id = auth.uid()
        AND srm.status = 'accepted'
    )
  );

-- 2. card_shares DELETE: 본인 카드만 공유 해제 가능
DROP POLICY IF EXISTS "card_shares_delete_own" ON card_shares;
CREATE POLICY "card_shares_delete_own" ON card_shares FOR DELETE
  USING (card_id IN (SELECT id FROM cards WHERE agent_id = auth.uid()::text));

-- 3. card_shares SELECT도 accepted만
DROP POLICY IF EXISTS "card_shares_select_member" ON card_shares;
CREATE POLICY "card_shares_select_member" ON card_shares FOR SELECT
  USING (room_id IN (
    SELECT room_id FROM share_room_members
    WHERE member_id = auth.uid() AND status = 'accepted'
  ));
