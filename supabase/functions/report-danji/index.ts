// report-danji — 단지 데이터 오류 신고
// POST { danji_id, danji_name, report_type, memo, page_url }
// → data_reports 테이블 저장 + 텔레그램 알림

import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const SUPABASE_URL    = Deno.env.get('SUPABASE_URL')!
const SERVICE_ROLE    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
const BOT_TOKEN       = Deno.env.get('TELEGRAM_BOT_TOKEN') || ''
const ADMIN_CHAT_ID   = Deno.env.get('TELEGRAM_ADMIN_CHAT_ID') || ''

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false }
})

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'content-type',
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS })

  try {
    const { danji_id, danji_name, report_type, memo, page_url } = await req.json()

    // 필수값 검증
    if (!danji_id || !report_type) {
      return new Response(JSON.stringify({ error: '필수값 누락' }), {
        status: 400, headers: { ...CORS, 'Content-Type': 'application/json' }
      })
    }

    // DB 저장
    const { error: dbErr } = await admin.from('data_reports').insert({
      danji_id,
      danji_name: danji_name || '',
      report_type,
      memo: memo || null,
      page_url: page_url || null,
    })

    if (dbErr) {
      console.error('DB insert error:', dbErr)
      return new Response(JSON.stringify({ error: 'DB 저장 실패' }), {
        status: 500, headers: { ...CORS, 'Content-Type': 'application/json' }
      })
    }

    // 텔레그램 알림 (설정된 경우만)
    if (BOT_TOKEN && ADMIN_CHAT_ID) {
      const text = [
        `📋 <b>데이터 오류 신고</b>`,
        `단지: ${danji_name || danji_id}`,
        `유형: ${report_type}`,
        memo ? `메모: ${memo}` : null,
        page_url ? `\n<a href="${page_url}">페이지 바로가기</a>` : null,
      ].filter(Boolean).join('\n')

      await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: ADMIN_CHAT_ID,
          text,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        }),
      }).catch(() => {}) // 텔레그램 실패해도 신고 자체는 성공 처리
    }

    return new Response(JSON.stringify({ ok: true }), {
      headers: { ...CORS, 'Content-Type': 'application/json' }
    })

  } catch (e) {
    console.error(e)
    return new Response(JSON.stringify({ error: '서버 오류' }), {
      status: 500, headers: { ...CORS, 'Content-Type': 'application/json' }
    })
  }
})
