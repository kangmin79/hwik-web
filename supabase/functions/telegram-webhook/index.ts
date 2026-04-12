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
const ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY')!
const HWIK_INTERNAL_SECRET = Deno.env.get('HWIK_INTERNAL_SECRET') || ''

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false }
})

// ========== 중개사 메인 키보드 (입력창 아래 상시 고정) ==========
// 타이핑 부담 제거 — 버튼 탭으로 주요 기능 모두 접근
// PC/모바일 모두에서 한 줄로 붙도록 4개 한 row, 텍스트는 짧게
const MAIN_KEYBOARD = {
  keyboard: [
    [
      { text: '📋 브리핑' },
      { text: '🏠 매물' },
      { text: '🙋 손님' },
      { text: 'ⓘ 내 정보' },
    ],
  ],
  resize_keyboard: true,
  is_persistent: true,
}

// 등록 진행 중 키보드 — 하단에 "❌ 등록 취소" 추가 (손님/매물 공통)
// reply_keyboard 는 메시지 바깥 영역이라 double-tap 좋아요 반응과 충돌 X
const FLOW_KEYBOARD = {
  keyboard: [
    [
      { text: '📋 브리핑' },
      { text: '🏠 매물' },
      { text: '🙋 손님' },
      { text: 'ⓘ 내 정보' },
    ],
    [
      { text: '❌ 등록 취소' },
    ],
  ],
  resize_keyboard: true,
  is_persistent: true,
}

// ========== 등록 채팅 플로우 상수 (손님/매물 공통) ==========
// mobile.html _REQUIRED_FIELDS / _FIELD_QUESTIONS / _SKIP_KEYWORDS 의 봇 버전
const REQUIRED_CLIENT_FIELDS = ['trade', 'location', 'price', 'category', 'contact'] as const
const REQUIRED_PROPERTY_FIELDS = ['contact'] as const
const CLIENT_FIELD_QUESTIONS: Record<string, string> = {
  trade: '손님이 원하는 <b>거래</b>는요?',
  location: '손님이 원하는 <b>지역</b>은요?\n예) 강남구 역삼동, 마포구, 분당',
  price: '손님 <b>예산</b>은 어느 정도인가요?\n예) 5억 이하, 보증금 1000 월 60',
  category: '손님이 원하는 <b>매물 종류</b>는요?',
  contact: '손님 <b>이름이나 연락처</b> 알려주세요.\n예) 홍길동 010-1234-5678',
}
const PROPERTY_FIELD_QUESTIONS: Record<string, string> = {
  contact: '집주인이나 세입자 <b>이름과 연락처</b> 알려주세요.\n예) 박사장 010-1234-5678\n\n없으면 "없음" 이라고 적어주세요.',
}
const SKIP_RE = /^(없음|없어|없습니다|스킵|skip|상관없|몰라요?|모름|패스|pass|생략)$/i
const RESET_RE = /^(처음부터|리셋|취소|초기화)$/

// 확인 카드 inline keyboard (메시지 하단 버튼)
const CONFIRM_KEYBOARD = {
  inline_keyboard: [[
    { text: '✅ 등록하기', callback_data: 'confirm_register' },
    { text: '✏️ 수정', callback_data: 'confirm_edit' },
    { text: '❌ 취소', callback_data: 'confirm_cancel' },
  ]],
}

// 필드별 inline keyboard — 선택지 뻔한 필드만 (탭 한 번 = 파싱 없이 즉시 주입)
// 취소는 reply_keyboard (FLOW_KEYBOARD) 에만 두고 여기엔 안 넣음
// — 이유: 텔레그램 데스크톱 double-tap 좋아요 반응과 충돌 방지
const TRADE_KEYBOARD = {
  inline_keyboard: [
    [
      { text: '매매', callback_data: 'ft:매매' },
      { text: '전세', callback_data: 'ft:전세' },
      { text: '월세', callback_data: 'ft:월세' },
      { text: '반전세', callback_data: 'ft:반전세' },
    ],
    [{ text: '없음', callback_data: 'ft:skip' }],
  ],
}

const CATEGORY_KEYBOARD = {
  inline_keyboard: [
    [
      { text: '아파트', callback_data: 'fc:apartment' },
      { text: '오피스텔', callback_data: 'fc:officetel' },
    ],
    [
      { text: '빌라', callback_data: 'fc:villa' },
      { text: '원룸', callback_data: 'fc:room' },
    ],
    [
      { text: '상가', callback_data: 'fc:commercial' },
      { text: '사무실', callback_data: 'fc:office' },
    ],
    [{ text: '없음', callback_data: 'fc:skip' }],
  ],
}

const FIELD_KEYBOARDS: Record<string, any> = {
  trade: TRADE_KEYBOARD,
  category: CATEGORY_KEYBOARD,
}

// 카테고리 슬러그 → 한국어 라벨 (callback 후 확인 메시지용)
const CATEGORY_KO: Record<string, string> = {
  apartment: '아파트', officetel: '오피스텔', villa: '빌라',
  room: '원룸/빌라', commercial: '상가', office: '사무실', house: '주택',
}

// 누락 필드 질문 — 선택지 필드는 inline 버튼, 텍스트 필드는 FLOW_KEYBOARD 재적용
// (reply_markup 이 inline 이면 reply_keyboard 는 기존 상태 유지)
async function askField(chatId: number, field: string, draftType: string) {
  const kb = FIELD_KEYBOARDS[field]
  const questions = draftType === 'property' ? PROPERTY_FIELD_QUESTIONS : CLIENT_FIELD_QUESTIONS
  const text = questions[field] || CLIENT_FIELD_QUESTIONS[field]
  return reply(chatId, text, {
    reply_markup: kb || FLOW_KEYBOARD,
  })
}

// 파싱 결과에서 특정 필드가 채워졌는지 (skipped 포함)
function hasField(draft: any, skipped: string[], field: string): boolean {
  if (skipped.includes(field)) return true
  const p = draft || {}
  switch (field) {
    case 'trade':
      return !!(p.wanted_trade_type || (p.type && p.type !== '손님' && p.type !== ''))
    case 'location':
      return !!(p.location || p.complex)
    case 'price':
      return !!(p.price || p.price_number || p.deposit || p.monthly_rent)
    case 'category':
      return !!p.category
    case 'contact':
      return !!(p.contact_name || p.contact_phone)
  }
  return false
}

function findMissingField(draft: any, skipped: string[], draftType: string): string | null {
  const list = draftType === 'property' ? REQUIRED_PROPERTY_FIELDS : REQUIRED_CLIENT_FIELDS
  for (const f of list) {
    if (!hasField(draft, skipped, f)) return f
  }
  return null
}

// 새 파싱 결과를 기존 draft 에 병합 (non-empty 값이 이김)
function mergeDraft(existing: any, newParsed: any): any {
  const merged = { ...(existing || {}) }
  for (const k in newParsed) {
    const v = newParsed[k]
    if (v === null || v === undefined || v === '') continue
    if (Array.isArray(v) && v.length === 0) continue
    merged[k] = v
  }
  return merged
}

// 확인 카드 본문 생성 (mobile.html _chatParsed summaryBubble 의 텍스트 버전)
function buildClientSummary(parsed: any): string {
  const location = [parsed.location, parsed.complex].filter(Boolean).join(' ')
  const wantType = parsed.wanted_trade_type || parsed.type || ''
  const catKo: Record<string, string> = {
    apartment: '아파트', officetel: '오피스텔', room: '원룸/빌라',
    commercial: '상가', office: '사무실', villa: '빌라', house: '주택',
  }
  const catLabel = catKo[parsed.category] || parsed.category || ''

  const sumParts: string[] = []
  if (location) sumParts.push(`<b>${location}</b>`)
  if (wantType && wantType !== '손님') sumParts.push(`<b>${wantType}</b>`)
  if (parsed.price) sumParts.push(`<b>${parsed.price}</b>`)
  if (catLabel) sumParts.push(`<b>${catLabel}</b>`)

  const contactLine = [parsed.contact_name, parsed.contact_phone].filter(Boolean).join(' ')
  const tagLine = Array.isArray(parsed.tags) && parsed.tags.length
    ? '🏷 ' + parsed.tags.slice(0, 6).map((t: string) => `#${t}`).join(' ')
    : null

  const lines: string[] = ['정리해드릴게요 ✨', '']
  if (sumParts.length) lines.push(`📋 ${sumParts.join(' ')}`)
  if (contactLine) lines.push(`👤 <b>${contactLine}</b> 손님`)
  if (tagLine) lines.push(tagLine)

  // 누락 경고 (이름/연락처는 경고만, mobile.html 과 동일)
  const hasName = !!parsed.contact_name
  const hasPhone = !!parsed.contact_phone
  const missingLabel = !hasName && !hasPhone ? '이름·연락처' : !hasName ? '이름' : !hasPhone ? '연락처' : ''
  if (missingLabel) {
    lines.push('')
    lines.push(`⚠️ ${missingLabel} 없이 등록됩니다 — 나중에 수정할 수 있어요`)
  }

  lines.push('')
  lines.push('이대로 <b>등록할까요?</b>')
  return lines.join('\n')
}

// 매물 확인 카드 본문 생성
function buildPropertySummary(parsed: any): string {
  const typeEmoji: Record<string, string> = {
    '매매': '🏠', '전세': '🔑', '월세': '💰',
  }
  const emoji = typeEmoji[parsed.type] || '🏠'
  const tagLine = Array.isArray(parsed.tags) && parsed.tags.length
    ? '🏷 ' + parsed.tags.slice(0, 8).map((t: string) => `#${t}`).join(' ')
    : null

  const lines: string[] = [`${emoji} <b>${parsed.type || '매물'} 등록 준비</b>`, '']
  if (parsed.price) lines.push(`💵 ${parsed.price}`)
  if (parsed.complex) lines.push(`🏢 ${parsed.complex}`)
  if (parsed.location) lines.push(`📍 ${parsed.location}`)
  if (parsed.area) lines.push(`📐 ${parsed.area}`)
  if (parsed.floor) lines.push(`🏗 ${parsed.floor}`)
  if (parsed.contact_name || parsed.contact_phone) {
    const c = [parsed.contact_name, parsed.contact_phone].filter(Boolean).join(' · ')
    lines.push(`👤 ${c}`)
  }
  if (tagLine) lines.push(tagLine)

  const hasContact = !!(parsed.contact_name || parsed.contact_phone)
  if (!hasContact) {
    lines.push('')
    lines.push('⚠️ 연락처 없이 등록됩니다 — 나중에 수정할 수 있어요')
  }

  lines.push('')
  lines.push('이대로 <b>등록할까요?</b>')
  return lines.join('\n')
}

// ========== Draft DB helpers ==========
async function getDraftRow(chatId: number) {
  const { data } = await admin
    .from('telegram_drafts')
    .select('*')
    .eq('chat_id', chatId)
    .maybeSingle()
  return data
}

async function saveDraft(chatId: number, agentId: string, patch: Record<string, unknown>) {
  return admin.from('telegram_drafts').upsert({
    chat_id: chatId,
    agent_id: agentId,
    ...patch,
    updated_at: new Date().toISOString(),
  })
}

async function clearDraft(chatId: number) {
  return admin.from('telegram_drafts').delete().eq('chat_id', chatId)
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
  // ANON_KEY 로 gateway JWT 체크 통과 + x-hwik-internal 헤더로 함수 내부 bypass 트리거
  const res = await fetch(`${SUPABASE_URL}/functions/v1/parse-property`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${ANON_KEY}`,
      'apikey': ANON_KEY,
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
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

  // ========== 리셋 / 취소 키워드 (어느 상태에서든 처음부터) ==========
  if (RESET_RE.test(text) || text === '❌ 등록 취소') {
    await clearDraft(chatId)
    return reply(
      chatId,
      '❌ 등록 취소',
      { reply_markup: MAIN_KEYBOARD }
    )
  }

  // ========== 버튼 텍스트 분기 (타이핑 부담 제거 UX) ==========
  if (text === '📋 브리핑') {
    await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
    try {
      const brief = await buildBriefing(agent.id)
      return reply(chatId, brief, { reply_markup: MAIN_KEYBOARD })
    } catch (e: any) {
      return reply(chatId, `❌ 브리핑 조회 실패: ${e.message}`, { reply_markup: MAIN_KEYBOARD })
    }
  }
  if (text === '🏠 매물') {
    // 매물 모드 초기화 — 빈 draft 생성 (이후 첫 메시지부터 채팅 플로우)
    await saveDraft(chatId, agent.id, {
      draft: {}, raw_text: '', skipped: [],
      missing_field: null, state: 'idle', draft_type: 'property',
    })
    return reply(
      chatId,
      `🏠 <b>매물 등록</b>\n\n다음 메시지에 매물 정보를 자유롭게 입력해주세요. 한 번에 다 말해도 되고, 하나씩 알려주셔도 돼요.\n\n<b>예시</b>\n<code>래미안 32평 15억 남향 고층 깨끗해 박사장 010-9999-8888</code>\n\n💡 손님 조건이면 🙋 손님 탭하세요`,
      { reply_markup: FLOW_KEYBOARD }
    )
  }
  if (text === '🙋 손님') {
    // 손님 모드 초기화 — 빈 draft 생성 (이후 첫 메시지부터 채팅 플로우)
    await saveDraft(chatId, agent.id, {
      draft: {}, raw_text: '', skipped: [],
      missing_field: null, state: 'idle', draft_type: 'client',
    })
    return reply(
      chatId,
      `🙋 <b>손님 등록</b>\n\n다음 메시지에 손님이 찾는 조건을 알려주세요. 한 번에 다 말해도 되고, 하나씩 알려주셔도 돼요.\n\n<b>예시</b>\n<code>강남 전세 5억 이하 홍길동 010-1234-5678</code>\n\n💡 매물 등록하려던 거면 🏠 매물 탭하세요`,
      { reply_markup: FLOW_KEYBOARD }
    )
  }
  if (text === 'ⓘ 내 정보') {
    return handleCommand(chatId, '/me', agent)
  }

  // ========== 현재 draft 상태 로드 ==========
  const existingDraft = await getDraftRow(chatId)
  const draftType = existingDraft?.draft_type as string | undefined
  const inClientFlow = draftType === 'client'
  const inPropertyFlow = draftType === 'property'
  const inAnyFlow = inClientFlow || inPropertyFlow

  // ========== 스킵 키워드 (누락 필드 질문 대기 중일 때만) ==========
  if (inAnyFlow && existingDraft.missing_field && SKIP_RE.test(text)) {
    const newSkipped = [...(existingDraft.skipped || []), existingDraft.missing_field]
    const nextMissing = findMissingField(existingDraft.draft, newSkipped, draftType!)
    if (nextMissing) {
      await saveDraft(chatId, agent.id, {
        draft: existingDraft.draft,
        raw_text: existingDraft.raw_text,
        skipped: newSkipped,
        missing_field: nextMissing,
        state: 'idle',
        draft_type: draftType!,
      })
      return askField(chatId, nextMissing, draftType!)
    }
    // 모두 채워짐 또는 스킵 → 확인 카드
    await saveDraft(chatId, agent.id, {
      draft: existingDraft.draft,
      raw_text: existingDraft.raw_text,
      skipped: newSkipped,
      missing_field: null,
      state: 'confirm',
      draft_type: draftType!,
    })
    const summary = inClientFlow
      ? buildClientSummary(existingDraft.draft)
      : buildPropertySummary(existingDraft.draft)
    await reply(chatId, summary, { reply_markup: CONFIRM_KEYBOARD })
    return
  }

  // 너무 짧은 입력은 flow 중엔 허용, 그 외엔 거절
  if (!inAnyFlow && text.trim().length < 10) {
    return reply(chatId, '매물 정보가 너무 짧아요. 가격·위치·면적 등을 더 적어주세요.', { reply_markup: MAIN_KEYBOARD })
  }

  // ========== 파싱 ==========
  await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
  const thinkingRes = await reply(chatId, '🤖 분석 중...', {
    reply_markup: inAnyFlow ? FLOW_KEYBOARD : MAIN_KEYBOARD,
  })
  const thinkingJson = await thinkingRes.json().catch(() => ({}))
  const thinkingId = thinkingJson?.result?.message_id as number | undefined

  try {
    // 누적 raw (flow 중일 때만)
    const combinedRaw = inAnyFlow
      ? ((existingDraft.raw_text || '') + ' ' + text).trim()
      : text
    // 손님 flow: "손님 " 접두로 parse-property 힌트. 매물 flow: 그대로.
    const parseInput = inClientFlow ? '손님 ' + combinedRaw : combinedRaw
    const parsed = await parseProperty(parseInput)
    const isClient = inClientFlow || (!inPropertyFlow && (parsed.type === '손님' || /손님|찾는/.test(parsed.type || '')))

    if (thinkingId) {
      await tg('deleteMessage', { chat_id: chatId, message_id: thinkingId }).catch(() => {})
    }

    // ========== 손님 / 매물 채팅 플로우 (공통) ==========
    // 버튼 안 누르고 바로 타이핑해도 AI 판정대로 flow 시작 — 단발성 경로 제거
    const mergedDraft = mergeDraft(existingDraft?.draft || {}, parsed)
    const skipped = existingDraft?.skipped || []
    const newRaw = combinedRaw
    const flowType: 'client' | 'property' = isClient ? 'client' : 'property'

    const missing = findMissingField(mergedDraft, skipped, flowType)
    if (missing) {
      await saveDraft(chatId, agent.id, {
        draft: mergedDraft,
        raw_text: newRaw,
        skipped,
        missing_field: missing,
        state: 'idle',
        draft_type: flowType,
      })
      return askField(chatId, missing, flowType)
    }

    // 모두 채워짐 → 확인 카드
    await saveDraft(chatId, agent.id, {
      draft: mergedDraft,
      raw_text: newRaw,
      skipped,
      missing_field: null,
      state: 'confirm',
      draft_type: flowType,
    })
    const summary = flowType === 'property'
      ? buildPropertySummary(mergedDraft)
      : buildClientSummary(mergedDraft)
    await reply(chatId, summary, { reply_markup: CONFIRM_KEYBOARD })
  } catch (e: any) {
    const errMsg = `❌ 등록 실패: ${e.message || e}`
    if (thinkingId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: thinkingId,
        text: errMsg,
      }).catch(() => {
        return reply(chatId, errMsg, { reply_markup: MAIN_KEYBOARD })
      })
    } else {
      await reply(chatId, errMsg, { reply_markup: MAIN_KEYBOARD })
    }
  }
}

// ========== Callback query handler (inline keyboard 버튼 탭) ==========
async function handleCallbackQuery(cb: any) {
  const chatId = cb.message?.chat?.id as number | undefined
  const messageId = cb.message?.message_id as number | undefined
  const data = cb.data as string
  const cbId = cb.id

  if (!chatId || !data) return

  // 즉시 ack (버튼 로딩 표시 제거)
  await tg('answerCallbackQuery', { callback_query_id: cbId }).catch(() => {})

  const agent = await findAgentByChatId(chatId)
  if (!agent) {
    return reply(chatId, '연동이 해제되었어요. /start 로 다시 시작해주세요.')
  }

  const draftRow = await getDraftRow(chatId)
  if (!draftRow) {
    if (messageId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: '이미 처리된 요청이에요.',
        parse_mode: 'HTML',
      }).catch(() => {})
    }
    return
  }

  // ========== 필드 버튼 (거래/종류) ==========
  if (data.startsWith('ft:') || data.startsWith('fc:')) {
    const prefix = data.slice(0, 2)
    const value = data.slice(3)
    const field = prefix === 'ft' ? 'trade' : 'category'

    let newDraft = { ...(draftRow.draft || {}) }
    const newSkipped = [...(draftRow.skipped || [])]

    let selectedLabel = ''
    if (value === 'skip') {
      if (!newSkipped.includes(field)) newSkipped.push(field)
      selectedLabel = '없음'
    } else if (field === 'trade') {
      newDraft.wanted_trade_type = value
      selectedLabel = value
    } else {
      newDraft.category = value
      selectedLabel = CATEGORY_KO[value] || value
    }

    // 현재 질문 메시지 → "✅ 선택 완료" 로 변환 (버튼 제거)
    if (messageId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: `✅ <b>${field === 'trade' ? '거래' : '종류'}</b>: ${selectedLabel}`,
        parse_mode: 'HTML',
        reply_markup: { inline_keyboard: [] },
      }).catch(() => {})
    }

    const nextMissing = findMissingField(newDraft, newSkipped, 'client')
    if (nextMissing) {
      await saveDraft(chatId, agent.id, {
        draft: newDraft,
        raw_text: draftRow.raw_text,
        skipped: newSkipped,
        missing_field: nextMissing,
        state: 'idle',
        draft_type: 'client',
      })
      await askField(chatId, nextMissing, 'client')
      return
    }

    // 모두 채워짐 → 확인 카드
    await saveDraft(chatId, agent.id, {
      draft: newDraft,
      raw_text: draftRow.raw_text,
      skipped: newSkipped,
      missing_field: null,
      state: 'confirm',
      draft_type: 'client',
    })
    await reply(chatId, buildClientSummary(newDraft), {
      reply_markup: CONFIRM_KEYBOARD,
    })
    return
  }

  // ========== 등록하기 ==========
  if (data === 'confirm_register') {
    const parsed = draftRow.draft || {}
    const rawText = draftRow.raw_text || ''
    const isClientDraft = draftRow.draft_type === 'client'
    const cardId = crypto.randomUUID().replace(/-/g, '').slice(0, 12)

    const cardData: Record<string, unknown> = {
      id: cardId,
      agent_id: agent.id,
      property: isClientDraft
        ? { ...parsed, type: '손님', rawText }
        : { ...parsed, rawText },
      style: 'noimg',
      color: 'blue',
      trade_status: '계약가능',
      search_text: parsed.search_text || rawText,
      search_text_private: parsed.search_text_private || null,
      embedding: parsed.embedding || null,
      price_number: parsed.price_number || null,
      deposit: parsed.deposit || null,
      monthly_rent: parsed.monthly_rent || null,
      contact_name: parsed.contact_name || null,
      contact_phone: parsed.contact_phone || null,
      tags: parsed.tags || [],
    }
    if (isClientDraft) cardData.client_status = '탐색중'

    const { error } = await admin.from('cards').insert(cardData)
    if (error) {
      if (messageId) {
        await tg('editMessageText', {
          chat_id: chatId,
          message_id: messageId,
          text: `❌ 등록 실패: ${error.message}`,
          parse_mode: 'HTML',
        }).catch(() => {})
      }
      return
    }

    await clearDraft(chatId)

    const internalHeaders = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${ANON_KEY}`,
      'apikey': ANON_KEY,
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
      'x-agent-id': agent.id,
    }

    if (isClientDraft) {
      // 손님 등록 완료 → 확인 카드 교체 + 매칭 진행
      const displayName = parsed.contact_name || '손님'
      if (messageId) {
        await tg('editMessageText', {
          chat_id: chatId,
          message_id: messageId,
          text: `✅ <b>${displayName}</b>님 등록 완료\n\n🔗 https://hwik.kr/property_chat.html?id=${cardId}`,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        }).catch(() => {})
      }

      await reply(chatId, '🔍 AI가 딱 맞는 매물 찾고 있어요...', {
        reply_markup: MAIN_KEYBOARD,
      })
      fetch(`${SUPABASE_URL}/functions/v1/match-properties`, {
        method: 'POST',
        headers: internalHeaders,
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
          if (!matches.length) {
            return reply(
              chatId,
              '지금 당장 맞는 매물이 없네요 😅\n새 매물이 등록되면 알림으로 알려드릴게요',
              { reply_markup: MAIN_KEYBOARD }
            )
          }
          const lines = matches
            .slice(0, 3)
            .map((x: any) => {
              const p = x.property || {}
              const head = `• ${p.type || ''} ${p.price || ''} — ${p.complex || p.location || ''}`
              const tags = Array.isArray(x.tags) ? x.tags.slice(0, 3) : []
              return tags.length ? `${head}\n   ${tags.map((t: string) => `#${t}`).join(' ')}` : head
            })
            .join('\n')
          return reply(
            chatId,
            `🎯 <b>매칭 매물 ${matches.length}건</b>\n${lines}`,
            { reply_markup: MAIN_KEYBOARD }
          )
        })
        .catch(() => {})
      return
    }

    // 매물 등록 완료 → 확인 카드 교체 + auto-match 비동기
    const typeEmoji: Record<string, string> = { '매매': '🏠', '전세': '🔑', '월세': '💰' }
    const emoji = typeEmoji[parsed.type] || '🏠'
    const displayName = parsed.complex || parsed.location || '매물'
    if (messageId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: `✅ ${emoji} <b>${displayName}</b> 등록 완료\n\n🔗 https://hwik.kr/property_chat.html?id=${cardId}`,
        parse_mode: 'HTML',
        disable_web_page_preview: true,
      }).catch(() => {})
    }
    await reply(chatId, '메뉴로 돌아왔어요.', { reply_markup: MAIN_KEYBOARD })
    fetch(`${SUPABASE_URL}/functions/v1/auto-match`, {
      method: 'POST',
      headers: internalHeaders,
      body: JSON.stringify({ card_id: cardId, agent_id: agent.id }),
    }).catch(() => {})
    return
  }

  // ========== 수정 (기존 draft 유지, 추가 입력 받기) ==========
  if (data === 'confirm_edit') {
    const dt = (draftRow.draft_type as string) || 'client'
    await saveDraft(chatId, agent.id, {
      draft: draftRow.draft,
      raw_text: draftRow.raw_text,
      skipped: draftRow.skipped || [],
      missing_field: null,
      state: 'idle',
      draft_type: dt,
    })
    if (messageId) {
      const editText = dt === 'property'
        ? '✏️ <b>수정 모드</b>\n추가하거나 바꿀 내용을 알려주세요.\n예) 박사장 010-1234-5678\n예) 15억\n예) 남향 고층'
        : '✏️ <b>수정 모드</b>\n추가하거나 바꿀 내용을 알려주세요.\n예) 이름 홍길동\n예) 지역 강남구\n예) 예산 5억 이하'
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: editText,
        parse_mode: 'HTML',
      }).catch(() => {})
    }
    return
  }

  // ========== 취소 ==========
  if (data === 'confirm_cancel') {
    await clearDraft(chatId)
    if (messageId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: '❌ 등록 취소',
        parse_mode: 'HTML',
      }).catch(() => {})
    }
    // reply_keyboard 를 MAIN_KEYBOARD 로 되돌리기 위해 follow-up
    await reply(chatId, '메뉴로 돌아왔어요.', { reply_markup: MAIN_KEYBOARD })
    return
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

  // inline keyboard 버튼 탭
  if (update.callback_query) {
    try {
      await handleCallbackQuery(update.callback_query)
    } catch (e: any) {
      console.error('callback error:', e)
    }
    return new Response('ok')
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
    await reply(chatId, `❌ 오류: ${e.message || e}`, {
      reply_markup: MAIN_KEYBOARD,
    }).catch(() => {})
  }

  // Telegram 은 200 OK 만 받으면 됨 (재시도 방지)
  return new Response('ok')
})
