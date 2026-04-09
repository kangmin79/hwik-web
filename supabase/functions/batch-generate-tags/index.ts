import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { generateTags, extractExcludedTags, extractRequiredTags, extractUnmatchedKeywords } from '../_shared/tags.ts'
import { getAuthUserId } from '../_shared/auth.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 규칙으로 못 잡은 카드 → AI로 태그 추출
async function generateTagsWithAI(card: any): Promise<string[]> {
  const CLAUDE_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
  if (!CLAUDE_API_KEY) return [];

  const p = card.property || {};
  const text = [
    p.rawText, p.location, p.complex, p.price, p.area, p.floor,
    ...(p.features || []), card.private_note?.memo
  ].filter(Boolean).join(' ');

  if (!text.trim()) return [];

  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 200,
        messages: [{
          role: 'user',
          content: `아래 부동산 매물 텍스트에서 태그를 추출해주세요.
태그 예시: 서울, 마포구, 합정동, 월세, 아파트, 원투룸, 역세권, 풀옵션, 남향, 주차가능, HUG가능, 즉시입주 등
JSON 배열로만 응답. 예: ["마포구","합정동","월세","원투룸","역세권"]

매물정보: ${text}`
        }]
      })
    });

    if (!res.ok) return [];
    const data = await res.json();
    const content = data.content?.[0]?.text || '';
    const match = content.match(/\[.*\]/s);
    if (!match) return [];
    return JSON.parse(match[0]).filter((t: any) => typeof t === 'string' && t.trim());
  } catch {
    return [];
  }
}

// 기존 매물에 태그 일괄 생성
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const agent_id = await getAuthUserId(req);
    if (!agent_id) throw new Error('인증이 필요합니다');

    // 단일 카드 또는 일괄 처리
    let body: any = {};
    try { body = await req.json(); } catch {}
    const { card_id } = body;

    let cards: any[] = [];
    if (card_id) {
      // 단일 카드 태그 재생성 (saveEdit 등에서 호출)
      const { data, error } = await supabase
        .from('cards')
        .select('id, property, private_note, price_number, deposit, monthly_rent, move_in_date, wanted_trade_type, wanted_categories, wanted_conditions, tags')
        .eq('id', card_id)
        .eq('agent_id', agent_id)
        .single();
      if (error || !data) throw new Error('카드를 찾을 수 없습니다');
      cards = [data];
    } else {
      // 태그가 없거나 2개 이하인 카드 일괄 조회
      const { data: allCards, error } = await supabase
        .from('cards')
        .select('id, property, private_note, price_number, deposit, monthly_rent, move_in_date, wanted_trade_type, wanted_categories, wanted_conditions, tags')
        .eq('agent_id', agent_id)
        .limit(500);
      if (error) throw error;
      cards = (allCards || []).filter(c => !c.tags || c.tags.length <= 2);
    }

    if (!cards.length) {
      return new Response(JSON.stringify({ success: true, updated: 0, message: '태그 생성할 카드 없음' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    let updated = 0;
    let aiUsed = 0;

    for (const card of cards) {
      // 1단계: 규칙 기반 태그 생성
      let tags = generateTags(card);

      // 2단계: 태그가 2개 이하면 AI로 보완
      if (tags.length <= 2) {
        const aiTags = await generateTagsWithAI(card);
        if (aiTags.length) {
          tags = [...new Set([...tags, ...aiTags])].filter(t => t && t.trim());
          aiUsed++;
        }
      }

      if (tags.length) {
        const updateData: any = { tags };
        // 손님 카드: required_tags/excluded_tags도 생성
        const p = card.property || {};
        if (p.type === '손님') {
          const rawText = p.rawText || '';
          const excluded = extractExcludedTags(rawText);
          const required = extractRequiredTags(rawText, tags);
          if (excluded.length) updateData.excluded_tags = excluded;
          if (required.length) updateData.required_tags = required;
        }
        const { error: updateErr } = await supabase
          .from('cards')
          .update(updateData)
          .eq('id', card.id);
        if (!updateErr) updated++;

        // 미매칭 키워드 로깅
        const unmatched = extractUnmatchedKeywords(card, tags);
        if (unmatched.length) {
          const rows = unmatched.map(kw => ({
            keyword: kw,
            source: 'feature',
            agent_id,
            card_id: card.id,
          }));
          await supabase.from('unmatched_keywords').insert(rows);
        }
      }
    }

    return new Response(JSON.stringify({
      success: true,
      total: cards.length,
      updated,
      ai_used: aiUsed,
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
