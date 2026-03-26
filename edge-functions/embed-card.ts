import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    if (!OPENAI_API_KEY) throw new Error('OPENAI_API_KEY not set');

    // ★ 인증 체크: 로그인한 사용자만 임베딩 업데이트 가능
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) throw new Error('인증이 필요합니다');
    const token = authHeader.replace('Bearer ', '');
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { data: { user }, error: authError } = await supabase.auth.getUser(token);
    if (authError || !user) throw new Error('인증이 필요합니다');

    const { card_id, text } = await req.json();
    if (!card_id || !text) throw new Error('card_id and text required');

    // ★ 본인 카드인지 확인
    const { data: card, error: cardCheckErr } = await supabase
      .from('cards')
      .select('agent_id')
      .eq('id', card_id)
      .single();
    if (cardCheckErr || !card) throw new Error('카드를 찾을 수 없습니다');
    if (card.agent_id !== user.id) throw new Error('본인 카드만 업데이트 가능합니다');

    // 임베딩 생성
    const embedResp = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'text-embedding-3-small', input: text })
    });

    const embedData = await embedResp.json();
    const embedding = embedData.data?.[0]?.embedding;
    if (!embedding) throw new Error('임베딩 생성 실패');

    // DB 업데이트
    const { error } = await supabase.from('cards').update({
      embedding: embedding,
      search_text: text
    }).eq('id', card_id).eq('agent_id', user.id);

    if (error) throw error;

    return new Response(JSON.stringify({ success: true }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
