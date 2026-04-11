// 휙 텔레그램 봇 ↔ 중개사 1:1 대화 연동
//
// 플로우:
//   1) /start → 연동 안 됐으면 폰번호 요구, 됐으면 환영 + 사용법
//   2) 폰번호 입력 → profiles 에서 매칭 → telegram_chat_id 저장
//   3) 자유 텍스트 → parse-property (service_role 로 내부 호출) → cards insert
//   4) 손님이면 match-properties, 매물이면 auto-match 비동기 트리거
//
// 배포:
//   supabase functions deploy telegram-webhook --no-verify-jwt
//   (텔레그램은 JWT 안 보내므로 gateway JWT 체크 끔 — 대신 webhook secret 사용)
//
// 필수 Secrets:
//   TELEGRAM_BOT_TOKEN
//   TELEGRAM_WEBHOOK_SECRET  (선택 — 있으면 X-Telegram-Bot-Api-Secret-Token 헤더 검증)
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (Supabase가 자동 주입)
//
// 웹훅 등록:
//   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
//     -H "Content-Type: application/json" \
//     -d '{"url":"https://<project>.supabase.co/functions/v1/telegram-webhook","secret_token":"<SECRET>"}'

import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const BOT_TOKEN = Deno.env.get('TELEGRAM_BOT_TOKEN')!
const WEBHOOK_SECRET = Deno.env.get('TELEGRAM_WEBHOOK_SECRET') || ''
const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
const SERVICE_ROLE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false }
})

// ========== 중개사 메인 키보드 (입력창 아래 상시 고정) ==========
// 타이핑 부담 제거 — 버튼 탭으로 주요 기능 모두 접근
const MAIN_KEYBOARD = {
  keyboard: [
    [{ text: '📋 오늘 브리핑' }],
    [{ text: '🏠 매물 등록' }, { text: '🙋 손님 등록' }],
    [{ text: 'ⓘ 내 정보' }],
  ],
  resize_keyboard: true,
  is_persistent: true,
}

// ========== Telegram API helpers ==========
async function tg(method: string, body: Record<string, unknown>) {
  return fetch(`https://api.telegram.org/bot${BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function reply(chatId: number, text: string, extra: Record<string, unknown> = {}) {
  return tg('sendMessage', {
    chat_id: chatId,
    text,
    parse_mode: 'HTML',
    disable_web_page_preview: true,
    ...extra,
  })
}

// ========== 도메인 helpers ==========
function normalizePhone(s: string): string | null {
  const digits = (s || '').replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('01')) {
    return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
  }
  if (digits.length === 10 && digits.startsWith('01')) {
    return `0${digits.slice(0, 2)}-${digits.slice(2, 6)}-${digits.slice(6)}`
  }
  return null
}

async function findAgentByChatId(chatId: number) {
  const { data } = await admin
    .from('profiles')
    .select('id, agent_name, business_name, phone, phone_verified, telegram_linked_at')
    .eq('telegram_chat_id', chatId)
    .maybeSingle()
  return data
}

async function findAgentByPhone(phone: string) {
  // 하이픈/공백 변형 다 대응하려고 여러 형태로 시도
  const digits = phone.replace(/\D/g, '')
  const variants = Array.from(new Set([phone, digits, `${digits.slice(0,3)}-${digits.slice(3,7)}-${digits.slice(7)}`]))
  const { data } = await admin
    .from('profiles')
    .select('id, agent_name, business_name, phone, phone_verified')
    .in('phone', variants)
    .maybeSingle()
  return data
}

async function linkAgent(agentId: string, chatId: number) {
  return admin
    .from('profiles')
    .update({
      telegram_chat_id: chatId,
      telegram_linked_at: new Date().toISOString(),
    })
    .eq('id', agentId)
}

// ========== 브리핑 ==========
// mobile.html _buildBriefQueue 의 봇 버전. 오늘/지연 알림 + 매칭 요약.
async function buildBriefing(agentId: string): Promise<string> {
  const nowIso = new Date().toISOString()
  const today = nowIso.slice(0, 10)

  const [overdueRes, upcomingRes, matchRes] = await Promise.all([
    admin.from('client_notes')
      .select('id, client_card_id, content, alert_date, type')
      .eq('agent_id', agentId)
      .eq('alert_done', false)
      .not('alert_date', 'is', null)
      .lt('alert_date', nowIso)
      .order('alert_date', { ascending: true })
      .limit(20),
    admin.from('client_notes')
      .select('id, client_card_id, content, alert_date, type')
      .eq('agent_id', agentId)
      .eq('alert_done', false)
      .not('alert_date', 'is', null)
      .gte('alert_date', nowIso)
      .lte('alert_date', today + 'T23:59:59.999Z')
      .order('alert_date', { ascending: true })
      .limit(20),
    admin.from('match_notifications')
      .select('id', { count: 'exact', head: true })
      .eq('agent_id', agentId)
      .eq('is_read', false),
  ])

  // log/match 타입 제외 (mobile.html 과 동일 필터)
  const excludeTypes = new Set(['log', 'match', '로그', '매칭'])
  const overdue = (overdueRes.data || []).filter((a: any) => !excludeTypes.has(a.type))
  const upcoming = (upcomingRes.data || []).filter((a: any) => !excludeTypes.has(a.type))
  const newMatches = matchRes.count || 0

  const lines: string[] = []
  const hour = new Date(Date.now() + 9 * 3600 * 1000).getUTCHours()
  const greet = hour < 6 ? '새벽이에요' : hour < 12 ? '좋은 아침이에요' : hour < 18 ? '좋은 오후에요' : '좋은 저녁이에요'
  lines.push(`🌅 <b>${greet}</b>`)
  lines.push('')

  const typeIcon: Record<string, string> = {
    '방문': '🏠', '전화': '📞', '계약': '📋', '상담': '💬', '매물소개': '📤',
  }

  if (upcoming.length) {
    lines.push(`📅 <b>오늘 일정 ${upcoming.length}건</b>`)
    upcoming.slice(0, 10).forEach((a: any) => {
      const ad = new Date(a.alert_date)
      const h = ad.getUTCHours() + 9
      const hh = h >= 24 ? h - 24 : h
      const mm = ad.getUTCMinutes()
      const time = `${hh}시${mm ? mm + '분' : ''}`
      const icon = typeIcon[a.type] || '📌'
      const content = (a.content || '').replace(/\n/g, ' ').slice(0, 50)
      lines.push(`${icon} ${time} · ${content}`)
    })
    if (upcoming.length > 10) lines.push(`  외 ${upcoming.length - 10}건`)
    lines.push('')
  }

  if (newMatches > 0) {
    lines.push(`🎯 <b>새 매칭 ${newMatches}건</b>`)
    lines.push(`https://hwik.kr/mobile.html 에서 확인`)
    lines.push('')
  }

  if (overdue.length) {
    lines.push(`⏰ <b>지연 ${overdue.length}건</b>`)
    overdue.slice(0, 5).forEach((a: any) => {
      const dateStr = a.alert_date.slice(5, 10).replace('-', '/')
      const content = (a.content || '').replace(/\n/g, ' ').slice(0, 40)
      lines.push(`• ${dateStr} · ${content}`)
    })
    if (overdue.length > 5) lines.push(`  외 ${overdue.length - 5}건`)
    lines.push('')
  }

  if (!upcoming.length && !newMatches && !overdue.length) {
    lines.push('📭 오늘은 예정된 일정이 없어요.')
    lines.push('편한 하루 보내세요 🙂')
  }

  return lines.join('\n').trim()
}

async function parseProperty(text: string) {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/parse-property`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${SERVICE_ROLE}`,
    },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    const msg = await res.text()
    throw new Error(`parse-property ${res.status}: ${msg.slice(0, 200)}`)
  }
  return res.json()
}

// ========== Command handlers ==========
async function handleCommand(chatId: number, cmd: string, agent: any) {
  switch (cmd) {
    case '/start': {
      if (agent) {
        const name = agent.agent_name || agent.business_name || '중개사'
        return reply(
          chatId,
          `안녕하세요, <b>${name}</b>님! 🙂\n\n아래 버튼을 눌러서 시작하세요.\n\n• <b>📋 오늘 브리핑</b> — 지연·오늘 일정·새 매칭 한눈에\n• <b>🏠 매물 등록</b> — 매물 정보 자유롭게 입력\n• <b>🙋 손님 등록</b> — 찾는 손님 조건 입력\n• <b>ⓘ 내 정보</b> — 내 프로필 확인`,
          { reply_markup: MAIN_KEYBOARD }
        )
      }
      return reply(
        chatId,
        `안녕하세요! 휙 봇입니다. 🙂\n\n처음이시네요. 휙에 가입된 <b>전화번호</b>를 입력해주세요.\n\n예: <code>010-1234-5678</code>\n\n아직 가입 안 하셨다면 먼저 https://hwik.kr 에서 가입해주세요.`
      )
    }

    case '/me': {
      if (!agent) return reply(chatId, '아직 연동이 안 됐어요. /start 로 시작해주세요.')
      const linkedDate = agent.telegram_linked_at
        ? new Date(agent.telegram_linked_at).toLocaleDateString('ko-KR')
        : '-'
      return reply(
        chatId,
        `<b>${agent.agent_name || '(이름없음)'}</b>\n${agent.business_name || ''}\n${agent.phone || ''}\n\n연동일: ${linkedDate}`,
        { reply_markup: MAIN_KEYBOARD }
      )
    }

    case '/unlink': {
      if (!agent) return reply(chatId, '연동된 계정이 없어요.')
      await admin
        .from('profiles')
        .update({ telegram_chat_id: null, telegram_linked_at: null })
        .eq('id', agent.id)
      return reply(chatId, '연동 해제 완료. 다시 연결하려면 /start', {
        reply_markup: { remove_keyboard: true },
      })
    }
  }
  return reply(chatId, '아래 버튼을 이용해주세요.', { reply_markup: MAIN_KEYBOARD })
}

// ========== Text handlers ==========
async function handleText(chatId: number, text: string, agent: any) {
  // 연동 안 됐으면 폰번호로 연결 시도
  if (!agent) {
    const phone = normalizePhone(text)
    if (!phone) {
      return reply(
        chatId,
        '먼저 연동이 필요해요. 휙에 가입된 <b>전화번호</b>를 입력해주세요.\n\n예: <code>010-1234-5678</code>'
      )
    }
    const found = await findAgentByPhone(phone)
    if (!found) {
      return reply(
        chatId,
        `<code>${phone}</code> 으로 가입된 계정을 찾을 수 없어요.\n\n먼저 https://hwik.kr 에서 가입해주세요.`
      )
    }
    if (!found.phone_verified) {
      return reply(
        chatId,
        '전화번호 인증이 아직 안 됐어요. https://hwik.kr 에서 인증 후 다시 시도해주세요.'
      )
    }
    await linkAgent(found.id, chatId)
    const name = found.agent_name || found.business_name || '중개사'
    return reply(
      chatId,
      `<b>${name}</b>님, 연동 완료! 🎉\n\n아래 버튼을 눌러서 바로 시작하세요 👇`,
      { reply_markup: MAIN_KEYBOARD }
    )
  }

  // ========== 버튼 텍스트 분기 (타이핑 부담 제거 UX) ==========
  if (text === '📋 오늘 브리핑') {
    await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
    try {
      const brief = await buildBriefing(agent.id)
      return reply(chatId, brief, { reply_markup: MAIN_KEYBOARD })
    } catch (e: any) {
      return reply(chatId, `❌ 브리핑 조회 실패: ${e.message}`, { reply_markup: MAIN_KEYBOARD })
    }
  }
  if (text === '🏠 매물 등록') {
    return reply(
      chatId,
      `🏠 <b>매물 등록</b>\n\n다음 메시지에 매물 정보를 자유롭게 입력해주세요. AI 가 알아서 분석합니다.\n\n<b>예시</b>\n<code>래미안 32평 15억 남향 고층 깨끗해 010-9999-8888 박사장</code>\n\n가격·위치·면적·층·특징·연락처 등 아는 것만 적으면 돼요.`,
      { reply_markup: MAIN_KEYBOARD }
    )
  }
  if (text === '🙋 손님 등록') {
    return reply(
      chatId,
      `🙋 <b>손님 등록</b>\n\n다음 메시지에 찾는 손님 조건을 입력해주세요.\n\n<b>예시</b>\n<code>강남구 20억 이하 아파트 찾는 분 010-1111-2222 김손님</code>\n\n등록하면 자동으로 매칭 매물을 찾아드려요 🎯`,
      { reply_markup: MAIN_KEYBOARD }
    )
  }
  if (text === 'ⓘ 내 정보') {
    return handleCommand(chatId, '/me', agent)
  }

  if (text.trim().length < 10) {
    return reply(chatId, '매물 정보가 너무 짧아요. 가격·위치·면적 등을 더 적어주세요.', { reply_markup: MAIN_KEYBOARD })
  }

  // 파싱 시작
  await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
  const thinkingRes = await reply(chatId, '🤖 분석 중...')
  const thinkingJson = await thinkingRes.json().catch(() => ({}))
  const thinkingId = thinkingJson?.result?.message_id as number | undefined

  try {
    const parsed = await parseProperty(text)
    const isClient = parsed.type === '손님' || /손님|찾는/.test(parsed.type || '')

    const cardId = crypto.randomUUID().replace(/-/g, '').slice(0, 12)
    const cardData: Record<string, unknown> = {
      id: cardId,
      agent_id: agent.id,
      property: { ...parsed, rawText: text },
      style: 'noimg',
      color: 'blue',
      trade_status: '계약가능',
      search_text: parsed.search_text || text,
      search_text_private: parsed.search_text_private || null,
      embedding: parsed.embedding || null,
      price_number: parsed.price_number || null,
      deposit: parsed.deposit || null,
      monthly_rent: parsed.monthly_rent || null,
      contact_name: parsed.contact_name || null,
      contact_phone: parsed.contact_phone || null,
      tags: parsed.tags || [],
    }
    if (isClient) cardData.client_status = '탐색중'

    const { error } = await admin.from('cards').insert(cardData)
    if (error) throw new Error(`DB insert 실패: ${error.message}`)

    // "분석 중" 버블 삭제
    if (thinkingId) {
      await tg('deleteMessage', { chat_id: chatId, message_id: thinkingId }).catch(() => {})
    }

    // 확인 메시지
    const typeEmoji: Record<string, string> = {
      '매매': '🏠', '전세': '🔑', '월세': '💰', '손님': '🙋',
    }
    const emoji = typeEmoji[parsed.type] || '🏠'
    const summary = [
      `${emoji} <b>${parsed.type || '매물'} 등록 완료</b>`,
      parsed.price ? `💵 ${parsed.price}` : null,
      parsed.complex ? `🏢 ${parsed.complex}` : null,
      parsed.location ? `📍 ${parsed.location}` : null,
      parsed.area ? `📐 ${parsed.area}` : null,
      parsed.contact_name
        ? `👤 ${parsed.contact_name}${parsed.contact_phone ? ' · ' + parsed.contact_phone : ''}`
        : null,
    ].filter(Boolean).join('\n')

    await reply(chatId, `${summary}\n\n🔗 https://hwik.kr/property_chat.html?id=${cardId}`, {
      reply_markup: MAIN_KEYBOARD,
    })

    // 비동기 매칭 트리거 (응답 기다리지 않음)
    if (isClient) {
      fetch(`${SUPABASE_URL}/functions/v1/match-properties`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${SERVICE_ROLE}`,
        },
        body: JSON.stringify({
          client_card_id: cardId,
          agent_id: agent.id,
          limit: 3,
          threshold: 0.15,
        }),
      })
        .then((r) => r.json())
        .then((m) => {
          const matches = m?.results || []
          if (!matches.length) return
          const lines = matches
            .slice(0, 3)
            .map((x: any) => {
              const p = x.property || {}
              return `• ${p.type || ''} ${p.price || ''} — ${p.complex || p.location || ''}`
            })
            .join('\n')
          return reply(chatId, `🎯 <b>매칭 매물 ${matches.length}건</b>\n${lines}`)
        })
        .catch(() => {})
    } else {
      fetch(`${SUPABASE_URL}/functions/v1/auto-match`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${SERVICE_ROLE}`,
        },
        body: JSON.stringify({ card_id: cardId, agent_id: agent.id }),
      }).catch(() => {})
    }
  } catch (e: any) {
    const errMsg = `❌ 등록 실패: ${e.message || e}`
    if (thinkingId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: thinkingId,
        text: errMsg,
      }).catch(() => {
        return reply(chatId, errMsg)
      })
    } else {
      await reply(chatId, errMsg)
    }
  }
}

// ========== Main ==========
Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('ok')

  // Webhook secret 검증 (설정된 경우)
  if (WEBHOOK_SECRET) {
    const header = req.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if (header !== WEBHOOK_SECRET) {
      return new Response('unauthorized', { status: 401 })
    }
  }

  let update: any
  try {
    update = await req.json()
  } catch {
    return new Response('bad request', { status: 400 })
  }

  const msg = update.message || update.edited_message
  if (!msg?.chat?.id) return new Response('ok')

  const chatId = msg.chat.id as number
  const text = (msg.text || '').trim()
  if (!text) return new Response('ok')

  const agent = await findAgentByChatId(chatId)

  try {
    if (text.startsWith('/')) {
      const cmd = text.split(/\s+/)[0].toLowerCase()
      await handleCommand(chatId, cmd, agent)
    } else {
      await handleText(chatId, text, agent)
    }
  } catch (e: any) {
    console.error('handler error:', e)
    await reply(chatId, `❌ 오류: ${e.message || e}`).catch(() => {})
  }

  // Telegram 은 200 OK 만 받으면 됨 (재시도 방지)
  return new Response('ok')
})
