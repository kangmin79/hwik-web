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
const ANON_KEY = Deno.env.get('HWIK_ANON_KEY') || Deno.env.get('SUPABASE_ANON_KEY')!
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

// ========== Idle 메시지용 inline 메뉴 (데스크톱/모바일 공통 영구 버튼) ==========
// reply_keyboard 가 데스크톱에서 사라지는 이슈 대응 — 메시지 자체에 박는 버튼
const MAIN_INLINE = {
  inline_keyboard: [
    [
      { text: '브리핑', callback_data: 'menu:brief' },
      { text: '매물', callback_data: 'menu:property' },
      { text: '손님', callback_data: 'menu:client' },
      { text: '내 정보', callback_data: 'menu:me' },
    ],
  ],
}

// 등록 플로우 중 질문 메시지에 붙이는 버튼 — 취소 하나만 (채팅 공간 최소화)
const FLOW_CANCEL_INLINE = {
  inline_keyboard: [
    [{ text: '등록 취소', callback_data: 'flow:cancel' }],
  ],
}

// 선택적 단계(한마디/공유방/사진)에서 건너뛰기 버튼
const SKIP_INLINE = {
  inline_keyboard: [
    [{ text: '건너뛰기', callback_data: 'step:skip' }],
  ],
}

// 사진 추가 후 완료 버튼
const DONE_INLINE = {
  inline_keyboard: [
    [{ text: '완료', callback_data: 'step:skip' }],
  ],
}

const RESET_RE = /^(처음부터|리셋|취소|초기화)$/

// 확인 카드 inline keyboard (메시지 하단 버튼)
const CONFIRM_KEYBOARD = {
  inline_keyboard: [[
    { text: '등록', callback_data: 'confirm_register' },
    { text: '수정', callback_data: 'confirm_edit' },
    { text: '취소', callback_data: 'confirm_cancel' },
  ]],
}

// 카테고리 슬러그 → 한국어 라벨 (확인 카드용)
const CATEGORY_KO: Record<string, string> = {
  apartment: '아파트', officetel: '오피스텔', villa: '빌라',
  room: '원룸/빌라', commercial: '상가', office: '사무실', house: '주택',
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
    ? parsed.tags.slice(0, 6).map((t: string) => `#${t}`).join(' ')
    : null

  const lines: string[] = []
  if (sumParts.length) lines.push(sumParts.join(' '))
  if (contactLine) lines.push(`<b>${contactLine}</b> 손님`)
  if (tagLine) lines.push(tagLine)

  const hasName = !!parsed.contact_name
  const hasPhone = !!parsed.contact_phone
  const missingLabel = !hasName && !hasPhone ? '이름·연락처' : !hasName ? '이름' : !hasPhone ? '연락처' : ''
  if (missingLabel) {
    lines.push('')
    lines.push(`${missingLabel} 없이 등록됩니다`)
  }

  lines.push('')
  lines.push('이대로 <b>등록할까요?</b>')
  return lines.join('\n')
}

// 매물 확인 카드 본문 생성
function buildPropertySummary(parsed: any): string {
  const tagLine = Array.isArray(parsed.tags) && parsed.tags.length
    ? parsed.tags.slice(0, 8).map((t: string) => `#${t}`).join(' ')
    : null

  const lines: string[] = [`<b>${parsed.type || '매물'} 등록 준비</b>`, '']
  if (parsed.price) lines.push(parsed.price)
  if (parsed.complex) lines.push(parsed.complex)
  if (parsed.location) lines.push(parsed.location)
  if (parsed.area) lines.push(parsed.area)
  if (parsed.floor) lines.push(parsed.floor)
  if (parsed.contact_name || parsed.contact_phone) {
    lines.push([parsed.contact_name, parsed.contact_phone].filter(Boolean).join(' · '))
  }
  if (tagLine) lines.push(tagLine)

  if (!(parsed.contact_name || parsed.contact_phone)) {
    lines.push('')
    lines.push('연락처 없이 등록됩니다')
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

// 중개사가 속한 공유방 목록
async function fetchAgentRooms(agentId: string) {
  const { data } = await admin
    .from('share_room_members')
    .select('share_rooms(id, name)')
    .eq('member_id', agentId)
    .eq('status', 'accepted')
  return (data || []).map((r: any) => r.share_rooms).filter(Boolean)
}

// 사진 업로드 대기 상태로 전환
async function askPhoto(chatId: number, agentId: string, draftRow: any) {
  await saveDraft(chatId, agentId, {
    draft: draftRow.draft,
    raw_text: draftRow.raw_text || '',
    skipped: draftRow.skipped || [],
    missing_field: null,
    state: 'photo_wait',
    draft_type: 'property',
  })
  return reply(chatId, '사진이 있으면 보내주세요.', { reply_markup: SKIP_INLINE })
}

// 공유방 선택 화면 (없으면 사진 단계로)
async function askShareOrFinish(chatId: number, agentId: string, draftRow: any) {
  const rooms = await fetchAgentRooms(agentId)
  if (!rooms.length) return askPhoto(chatId, agentId, draftRow)

  await saveDraft(chatId, agentId, {
    draft: draftRow.draft,
    raw_text: draftRow.raw_text || '',
    skipped: draftRow.skipped || [],
    missing_field: null,
    state: 'share_select',
    draft_type: 'property',
  })

  const buttons = rooms.slice(0, 8).map((r: any) => [
    { text: r.name, callback_data: `share:${r.id}` },
  ])
  buttons.push([{ text: '건너뛰기', callback_data: 'step:skip' }])
  return reply(chatId, '공유방에 올릴까요?', { reply_markup: { inline_keyboard: buttons } })
}

// 매물 등록 최종 완료 메시지
async function finishProperty(chatId: number, draftRow: any) {
  const cardId = draftRow.draft?._pending_card_id as string
  const displayName = draftRow.draft?._display_name as string || '매물'
  await clearDraft(chatId)
  return reply(
    chatId,
    `<b>${displayName}</b> 등록 완료\nhttps://hwik.kr/property_chat.html?id=${cardId}`,
    { reply_markup: MAIN_INLINE, disable_web_page_preview: true } as Record<string, unknown>
  )
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

  if (upcoming.length) {
    lines.push(`<b>오늘 일정 ${upcoming.length}건</b>`)
    upcoming.slice(0, 10).forEach((a: any) => {
      const ad = new Date(a.alert_date)
      const h = ad.getUTCHours() + 9
      const hh = h >= 24 ? h - 24 : h
      const mm = ad.getUTCMinutes()
      const time = `${hh}시${mm ? mm + '분' : ''}`
      const content = (a.content || '').replace(/\n/g, ' ').slice(0, 50)
      lines.push(`${time} · ${content}`)
    })
    if (upcoming.length > 10) lines.push(`외 ${upcoming.length - 10}건`)
    lines.push('')
  }

  if (newMatches > 0) {
    lines.push(`<b>새 매칭 ${newMatches}건</b>`)
    lines.push(`https://hwik.kr/mobile.html`)
    lines.push('')
  }

  if (overdue.length) {
    lines.push(`<b>지연 ${overdue.length}건</b>`)
    overdue.slice(0, 5).forEach((a: any) => {
      const dateStr = a.alert_date.slice(5, 10).replace('-', '/')
      const content = (a.content || '').replace(/\n/g, ' ').slice(0, 40)
      lines.push(`${dateStr} · ${content}`)
    })
    if (overdue.length > 5) lines.push(`외 ${overdue.length - 5}건`)
    lines.push('')
  }

  if (!upcoming.length && !newMatches && !overdue.length) {
    lines.push('오늘 예정된 일정이 없어요.')
  }

  return lines.join('\n').trim()
}

// ========== 사진 업로드 처리 ==========
async function handlePhoto(chatId: number, photos: any[], agent: any) {
  const draftRow = await getDraftRow(chatId)
  if (!draftRow || draftRow.state !== 'photo_wait') return

  const cardId = draftRow.draft?._pending_card_id as string
  if (!cardId) return

  // 가장 큰 사이즈 선택
  const photo = photos[photos.length - 1]

  // 텔레그램에서 파일 경로 취득
  const fileRes = await tg('getFile', { file_id: photo.file_id })
  const fileJson = await fileRes.json()
  const filePath = fileJson?.result?.file_path
  if (!filePath) {
    return reply(chatId, '사진 다운로드 실패. 다시 시도해주세요.', { reply_markup: DONE_INLINE })
  }

  // 파일 다운로드
  const imgRes = await fetch(`https://api.telegram.org/file/bot${BOT_TOKEN}/${filePath}`)
  if (!imgRes.ok) {
    return reply(chatId, '사진 다운로드 실패. 다시 시도해주세요.', { reply_markup: DONE_INLINE })
  }
  const imgBytes = await imgRes.arrayBuffer()

  // Supabase Storage 업로드
  const ext = filePath.split('.').pop() || 'jpg'
  const storagePath = `${cardId}/${Date.now()}.${ext}`
  const { error: upErr } = await admin.storage.from('photos').upload(storagePath, imgBytes, {
    contentType: 'image/jpeg',
    upsert: false,
  })
  if (upErr) {
    return reply(chatId, `사진 업로드 실패: ${upErr.message}`, { reply_markup: DONE_INLINE })
  }

  // 공개 URL
  const { data: urlData } = admin.storage.from('photos').getPublicUrl(storagePath)
  const publicUrl = urlData.publicUrl

  // cards.photos 배열에 추가
  const { data: card } = await admin.from('cards').select('photos').eq('id', cardId).single()
  const existingPhotos: string[] = (card?.photos || []).filter((p: any) => typeof p === 'string')
  await admin.from('cards').update({ photos: [...existingPhotos, publicUrl], style: 'memo' }).eq('id', cardId)

  return reply(
    chatId,
    `사진 ${existingPhotos.length + 1}장 추가됐어요. 더 보내주시면 추가할게요.`,
    { reply_markup: DONE_INLINE }
  )
}

// ========== telegram-agent 호출 ==========
async function callAgent(payload: {
  text: string
  draft: Record<string, unknown>
  draft_type: 'property' | 'client'
  mode?: string
}) {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/telegram-agent`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${ANON_KEY}`,
      'apikey': ANON_KEY,
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const msg = await res.text()
    throw new Error(`telegram-agent ${res.status}: ${msg.slice(0, 100)}`)
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
          `<b>${name}</b>님, 안녕하세요.\n\n브리핑 · 매물 · 손님 · 내 정보`,
          { reply_markup: MAIN_INLINE }
        )
      }
      return reply(
        chatId,
        `휙에 가입된 <b>전화번호</b>를 입력해주세요.`
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
        { reply_markup: MAIN_INLINE }
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

    // ========== 주요 기능 명령어 (하단 키보드 대체 접근 경로) ==========
    // 텔레그램 데스크톱에서 reply_keyboard 가 사라지는 이슈 대응
    case '/brief':
    case '/briefing': {
      if (!agent) return reply(chatId, '아직 연동이 안 됐어요. /start 로 시작해주세요.')
      return handleText(chatId, '📋 브리핑', agent)
    }
    case '/property':
    case '/add_property': {
      if (!agent) return reply(chatId, '아직 연동이 안 됐어요. /start 로 시작해주세요.')
      return handleText(chatId, '🏠 매물', agent)
    }
    case '/client':
    case '/add_client': {
      if (!agent) return reply(chatId, '아직 연동이 안 됐어요. /start 로 시작해주세요.')
      return handleText(chatId, '🙋 손님', agent)
    }
    case '/cancel': {
      if (!agent) return reply(chatId, '아직 연동이 안 됐어요. /start 로 시작해주세요.')
      return handleText(chatId, '❌ 등록 취소', agent)
    }
    case '/menu': {
      return reply(
        chatId,
        '📋 <b>메뉴</b>\n\n• /brief — 오늘 브리핑\n• /property — 매물 등록\n• /client — 손님 등록\n• /me — 내 정보\n• /cancel — 진행 중인 등록 취소',
        { reply_markup: MAIN_INLINE }
      )
    }

    // 봇 명령어 목록을 텔레그램에 등록 (최초 1회만 실행)
    case '/setup_commands': {
      const commands = [
        { command: 'brief', description: '오늘 브리핑 (지연·일정·새 매칭)' },
        { command: 'property', description: '매물 등록' },
        { command: 'client', description: '손님 등록' },
        { command: 'me', description: '내 정보' },
        { command: 'cancel', description: '진행 중인 등록 취소' },
        { command: 'menu', description: '메뉴 도움말' },
        { command: 'start', description: '봇 시작' },
      ]
      const res1 = await tg('setMyCommands', { commands })
      const res2 = await tg('setChatMenuButton', {
        menu_button: { type: 'commands' },
      })
      const ok = res1.ok && res2.ok
      return reply(
        chatId,
        ok
          ? '✅ 명령어 메뉴 등록 완료 — 이제 하단 왼쪽의 ⋮ 메뉴 버튼이나 / 입력으로 접근 가능합니다.'
          : `❌ 등록 실패: ${await res1.text().catch(() => '')} / ${await res2.text().catch(() => '')}`,
        { reply_markup: MAIN_INLINE }
      )
    }
  }
  return reply(chatId, '아래 버튼을 이용해주세요. (/menu 로도 접근 가능)', { reply_markup: MAIN_INLINE })
}

// ========== Text handlers ==========
async function handleText(chatId: number, text: string, agent: any) {
  // 연동 안 됐으면 폰번호로 연결 시도
  if (!agent) {
    const phone = normalizePhone(text)
    if (!phone) {
      return reply(
        chatId,
        '휙에 가입된 <b>전화번호</b>를 입력해주세요.'
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
      `<b>${name}</b>님, 연동 완료.`,
      { reply_markup: MAIN_INLINE }
    )
  }

  // ========== 리셋 / 취소 키워드 (어느 상태에서든 처음부터) ==========
  if (RESET_RE.test(text) || text === '등록 취소') {
    await clearDraft(chatId)
    return reply(
      chatId,
      '취소했어요.',
      { reply_markup: MAIN_INLINE }
    )
  }

  // ========== 버튼 텍스트 분기 (타이핑 부담 제거 UX) ==========
  if (text === '📋 브리핑') {
    await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
    try {
      const brief = await buildBriefing(agent.id)
      return reply(chatId, brief, { reply_markup: MAIN_INLINE })
    } catch (e: any) {
      return reply(chatId, `브리핑 조회 실패: ${e.message}`, { reply_markup: MAIN_INLINE })
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
      `🏠 <b>매물 등록</b>\n\n매물 정보를 자유롭게 입력해주세요.`,
      { reply_markup: FLOW_CANCEL_INLINE }
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
      `🙋 <b>손님 등록</b>\n\n손님이 찾는 조건을 알려주세요.`,
      { reply_markup: FLOW_CANCEL_INLINE }
    )
  }
  if (text === 'ⓘ 내 정보') {
    return handleCommand(chatId, '/me', agent)
  }

  // ========== 현재 draft 로드 ==========
  const existingDraft = await getDraftRow(chatId)
  const draftType = (existingDraft?.draft_type || 'property') as 'property' | 'client'
  const currentDraft = existingDraft?.draft || {}
  const inAnyFlow = !!(existingDraft?.draft_type)

  // ========== 등록 후 추가 작업 모드 (post_register) ==========
  if (existingDraft?.state === 'post_register') {
    await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
    try {
      const result = await callAgent({ text, draft: currentDraft, draft_type: draftType, mode: 'post_register' })
      const cardId = currentDraft._pending_card_id as string

      if (result.action === 'finish') return finishProperty(chatId, existingDraft)
      if (result.action === 'photo') return askPhoto(chatId, agent.id, existingDraft)
      if (result.action === 'share') return askShareOrFinish(chatId, agent.id, existingDraft)

      // 업데이트 있으면 카드에 반영
      if (cardId && result.updates && Object.keys(result.updates).length > 0) {
        await admin.from('cards').update(result.updates).eq('id', cardId).catch(() => {})
      }
      return reply(chatId, result.reply || '알겠어요.', { reply_markup: DONE_INLINE })
    } catch {
      return reply(chatId, '잠시 오류가 났어요. 다시 말씀해 주세요.', { reply_markup: DONE_INLINE })
    }
  }

  // ========== 사진 대기 중 ==========
  if (existingDraft?.state === 'photo_wait') {
    return reply(chatId, '사진을 보내주시거나 완료를 눌러주세요.', { reply_markup: SKIP_INLINE })
  }

  // ========== 공유방 선택 중 ==========
  if (existingDraft?.state === 'share_select') {
    return askShareOrFinish(chatId, agent.id, existingDraft)
  }

  // ========== AI 에이전트로 대화 처리 ==========
  await tg('sendChatAction', { chat_id: chatId, action: 'typing' })
  const thinkingRes = await reply(chatId, '...', {
    reply_markup: inAnyFlow ? FLOW_CANCEL_INLINE : MAIN_INLINE,
  })
  const thinkingId = (await thinkingRes.json().catch(() => ({}))).result?.message_id as number | undefined

  const deleteThinking = () =>
    thinkingId
      ? tg('deleteMessage', { chat_id: chatId, message_id: thinkingId }).catch(() => {})
      : Promise.resolve()

  try {
    const result = await callAgent({ text, draft: currentDraft, draft_type: draftType })

    await deleteThinking()

    // 부동산 무관 메시지
    if (result.intent === 'off_topic') {
      return reply(chatId, '매물이나 손님 등록 정보를 알려주세요.', { reply_markup: MAIN_INLINE })
    }

    // AI가 추출한 필드를 기존 draft에 병합
    const mergedDraft = mergeDraft(currentDraft, result.updates || {})

    // intent에서 draft_type 자동 감지 (버튼 없이 바로 타이핑한 경우)
    const detectedType: 'property' | 'client' =
      result.intent === 'client_data' ? 'client'
      : result.intent === 'property_data' ? 'property'
      : draftType

    if (result.action === 'confirm') {
      // 필수 정보 다 모임 → 확인 카드
      await saveDraft(chatId, agent.id, {
        draft: mergedDraft,
        raw_text: text,
        skipped: [],
        missing_field: null,
        state: 'confirm',
        draft_type: detectedType,
      })
      const summary = detectedType === 'property'
        ? buildPropertySummary(mergedDraft)
        : buildClientSummary(mergedDraft)
      return reply(chatId, summary, { reply_markup: CONFIRM_KEYBOARD })
    }

    // 아직 부족 → draft 저장 + AI가 만든 질문 전송
    await saveDraft(chatId, agent.id, {
      draft: mergedDraft,
      raw_text: text,
      skipped: [],
      missing_field: null,
      state: 'idle',
      draft_type: detectedType,
    })
    const replyText = result.missing_question || result.reply || '조금 더 알려주세요.'
    return reply(chatId, replyText, { reply_markup: FLOW_CANCEL_INLINE })

  } catch (e: any) {
    await deleteThinking()
    return reply(chatId, '잠시 오류가 났어요. 다시 말씀해 주세요.', { reply_markup: MAIN_INLINE })
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

  // ========== 메뉴 버튼 (draft 유무와 무관하게 동작) ==========
  // 모든 메시지에 박힌 MAIN_INLINE / FLOW_CANCEL_INLINE 에서 트리거
  if (data.startsWith('menu:')) {
    const target = data.slice(5)
    const textMap: Record<string, string> = {
      brief: '📋 브리핑',
      property: '🏠 매물',
      client: '🙋 손님',
      me: 'ⓘ 내 정보',
    }
    const buttonText = textMap[target]
    if (buttonText) {
      return handleText(chatId, buttonText, agent)
    }
    return
  }

  // ========== 등록 취소 (flow 밖에서 눌러도 무해) ==========
  if (data === 'flow:cancel') {
    await clearDraft(chatId)
    return reply(chatId, '취소했어요.', { reply_markup: MAIN_INLINE })
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
          text: `등록 실패: ${error.message}`,
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
          text: `<b>${displayName}</b>님 등록 완료\nhttps://hwik.kr/property_chat.html?id=${cardId}`,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        }).catch(() => {})
      }

      await reply(chatId, '매칭 매물 찾는 중...', {
        reply_markup: MAIN_INLINE,
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
              '지금 맞는 매물이 없어요. 새 매물 등록 시 알림 드릴게요.',
              { reply_markup: MAIN_INLINE }
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
            `<b>매칭 매물 ${matches.length}건</b>\n${lines}`,
            { reply_markup: MAIN_INLINE }
          )
        })
        .catch(() => {})
      return
    }

    // 매물 등록 완료 → auto-match 비동기 + 공유방/사진 단계로
    const displayName = parsed.complex || parsed.location || '매물'
    fetch(`${SUPABASE_URL}/functions/v1/auto-match`, {
      method: 'POST',
      headers: internalHeaders,
      body: JSON.stringify({ card_id: cardId, agent_id: agent.id }),
    }).catch(() => {})

    // 확인 카드 → "등록됨" 으로 교체
    if (messageId) {
      await tg('editMessageText', {
        chat_id: chatId,
        message_id: messageId,
        text: `<b>${displayName}</b> 등록됨.`,
        parse_mode: 'HTML',
      }).catch(() => {})
    }

    // 등록 완료 → post_register 모드 (AI가 추가 작업 자유롭게 처리)
    const pendingDraft = { ...parsed, _pending_card_id: cardId, _display_name: displayName }
    await saveDraft(chatId, agent.id, {
      draft: pendingDraft,
      raw_text: draftRow.raw_text || '',
      skipped: [],
      missing_field: null,
      state: 'post_register',
      draft_type: 'property',
    })
    return reply(
      chatId,
      `<b>${displayName}</b> 등록됐어요.\n사진, 공유방, 메모 등 추가할 게 있으면 말씀해 주세요.`,
      { reply_markup: DONE_INLINE }
    )
  }

  // ========== 공유방/사진 건너뛰기 ==========
  if (data === 'step:skip') {
    if (draftRow.state === 'share_select') return askPhoto(chatId, agent.id, draftRow)
    if (draftRow.state === 'photo_wait') return finishProperty(chatId, draftRow)
    return
  }

  // ========== 공유방 선택 ==========
  if (data.startsWith('share:')) {
    const roomId = data.slice(6)
    const cardId = draftRow.draft?._pending_card_id as string
    if (cardId && roomId) {
      await admin.from('card_shares').insert({
        card_id: cardId,
        room_id: roomId,
        shared_by: agent.id,
      }).catch(() => {})
    }
    return askPhoto(chatId, agent.id, draftRow)
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
        ? '✏️ <b>수정 모드</b>\n추가하거나 바꿀 내용을 알려주세요.'
        : '✏️ <b>수정 모드</b>\n추가하거나 바꿀 내용을 알려주세요.'
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
        text: '취소했어요.',
        parse_mode: 'HTML',
      }).catch(() => {})
    }
    // reply_keyboard 를 MAIN_KEYBOARD 로 되돌리기 위해 follow-up
    await reply(chatId, '취소했어요.', { reply_markup: MAIN_INLINE })
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

  // ========== 사진 메시지 ==========
  if (msg.photo) {
    try {
      const agent = await findAgentByChatId(chatId)
      if (agent) await handlePhoto(chatId, msg.photo, agent)
    } catch (e: any) {
      console.error('photo error:', e)
    }
    return new Response('ok')
  }

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
    await reply(chatId, `오류: ${e.message || e}`, {
      reply_markup: MAIN_INLINE,
    }).catch(() => {})
  }

  // Telegram 은 200 OK 만 받으면 됨 (재시도 방지)
  return new Response('ok')
})
