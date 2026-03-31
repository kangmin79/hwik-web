import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { generateTags } from '../_shared/tags.ts'
import { getAuthUserId } from '../_shared/auth.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 기존 매물에 태그 일괄 생성
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const agent_id = getAuthUserId(req);
    if (!agent_id) throw new Error('인증이 필요합니다');

    // 태그가 없는 카드만 조회
    const { data: cards, error } = await supabase
      .from('cards')
      .select('id, property, price_number, deposit, monthly_rent, move_in_date, wanted_trade_type, wanted_categories, wanted_conditions, tags')
      .eq('agent_id', agent_id)
      .or('tags.is.null,tags.eq.[]')
      .limit(500);

    if (error) throw error;
    if (!cards || !cards.length) {
      return new Response(JSON.stringify({ success: true, updated: 0, message: '태그 생성할 카드 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    let updated = 0;
    for (const card of cards) {
      const tags = generateTags(card);
      if (tags.length) {
        const { error: updateErr } = await supabase
          .from('cards')
          .update({ tags })
          .eq('id', card.id);
        if (!updateErr) updated++;
      }
    }

    return new Response(JSON.stringify({
      success: true,
      total: cards.length,
      updated,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (e) {
    return new Response(JSON.stringify({ error: (e as Error).message }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
