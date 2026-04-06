import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// 매주 일요일 새벽: 미매칭 키워드 빈도순 리포트
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // 최근 7일간 미매칭 키워드
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

    const { data: rows, error } = await supabase
      .from('unmatched_keywords')
      .select('keyword, agent_id, card_id, created_at')
      .gte('created_at', weekAgo)
      .order('created_at', { ascending: false });

    if (error) throw error;

    // 빈도 집계
    const freq: Record<string, number> = {};
    for (const r of rows || []) {
      freq[r.keyword] = (freq[r.keyword] || 0) + 1;
    }

    // 빈도순 정렬
    const sorted = Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .map(([keyword, count]) => ({ keyword, count }));

    // 처리 완료된 오래된 데이터 정리 (30일 이상)
    const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
    await supabase.from('unmatched_keywords').delete().lt('created_at', monthAgo);

    return new Response(JSON.stringify({
      success: true,
      period: { from: weekAgo, to: new Date().toISOString() },
      total_unmatched: rows?.length || 0,
      unique_keywords: sorted.length,
      top_keywords: sorted.slice(0, 50),
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
