// telegram-agent — 텔레그램 봇 전용 AI 에이전트
//
// 역할: 중개사가 자유롭게 말한 내용을 이해하고
//       필요한 정보를 자연스럽게 추출·질문·응답
//
// 호출: telegram-webhook 에서만 (x-hwik-internal 헤더 필수)
//
// Input:  { text, draft, draft_type, mode }
// Output: { intent, updates, reply, action, missing_question }

import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!
const HWIK_INTERNAL_SECRET = Deno.env.get('HWIK_INTERNAL_SECRET') || ''
const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
const SERVICE_ROLE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false }
})

// ========== DB에서 최신 프롬프트 로드 (5분 캐시) ==========

const promptCache: Record<string, { text: string; expires: number }> = {}

async function loadPrompt(draftType: string): Promise<string | null> {
  const key = draftType
  if (promptCache[key] && Date.now() < promptCache[key].expires) {
    return promptCache[key].text
  }
  const { data } = await admin
    .from('agent_prompts')
    .select('prompt_text')
    .eq('draft_type', draftType)
    .eq('is_current', true)
    .order('version', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (data?.prompt_text) {
    promptCache[key] = { text: data.prompt_text, expires: Date.now() + 5 * 60 * 1000 }
    return data.prompt_text
  }
  return null
}

// ========== 하드코딩 프롬프트 (DB에 없을 때 fallback) ==========

function buildPrompt(draftType: 'property' | 'client', draft: any, mode: string): string {
  const draftJson = JSON.stringify(draft || {}, null, 2)

  // 등록 후 추가 작업 모드
  if (mode === 'post_register') {
    return `당신은 한국 부동산 중개사의 AI 어시스턴트입니다.
매물이 방금 등록됐습니다. 중개사가 추가 작업을 자유롭게 말합니다.

현재 등록된 정보:
${draftJson}

중개사 메시지의 의도를 파악하고 JSON으로만 응답하세요.

의도 분류 기준:
- 사진: "사진 올릴게", "나중에 사진", "사진 없어", "사진 보낼게" → action: photo
- 공유방: "공유방에 올려줘", "강남팀에", "공유해줘" → action: share
- 완료: "됐어", "끝", "없어", "그냥", "완료", "괜찮아", "다음에" → action: finish
- 메모 추가: 손님에게 전할 말 → updates.agent_comment에 저장, action: continue
- 그 외: action: continue

{
  "intent": "photo|share|finish|update|other",
  "updates": {},
  "reply": "짧은 한국어 응답 (1줄)",
  "action": "continue|finish|photo|share"
}`
  }

  // 매물 등록 모드
  if (draftType === 'property') {
    return `당신은 한국 부동산 중개사의 AI 어시스턴트입니다.
중개사가 매물 정보를 텔레그램으로 자유롭게 말합니다. 정보를 추출하고 자연스럽게 대화합니다.

현재까지 파악된 정보:
${draftJson}

필수 정보:
- contact: 집주인 또는 세입자 이름/전화번호
  (없으면 "없음" 이라고 해도 됨 → contact_skipped: true로 처리)

규칙:
- 부동산 매물과 무관한 메시지(일정, 인사, 일상 대화 등) → intent: off_topic
  reply는 자연스럽게 인정하되 봇 기능 짧게 안내
  예) "내일 3시 방문 예정이군요. 저는 매물·손님 등록을 도와드릴 수 있어요."
- 단, "없음", "없어", "나중에", "모름", "스킵", "패스" 는 off_topic 아님 → contact_skipped: true + action: confirm
- 이미 draft에 있는 정보는 절대 다시 묻지 말 것
- draft에 정보 있는 상태에서 추가 정보(층수, 특징 등)가 들어오면 → intent: property_data, action: confirm (이미 필수 채워졌으면)
- confirm 조건 (아래 중 하나):
    a) contact_name 또는 contact_phone 있음
    b) contact_skipped: true (없음/나중에/모름/스킵 발화)
  contact 외 나머지(층수, 단지명, 면적, 특징)는 없어도 confirm 가능
- 질문할 게 있으면 딱 하나만. 층수/단지명/면적/주차/향 같은 선택 정보는 절대 묻지 말 것
- 월세+monthly_rent 있으면 보증금 묻지 말 것
- 가격 숫자 변환: 7억→700000000, 3억5천→350000000
  월세: 보증금1000 월50 → deposit:10000000, monthly_rent:50000
  월세만 있을 때: 250만→monthly_rent:2500000
- category: 아파트→apartment, 오피스텔→officetel, 빌라→villa,
            원룸→room, 상가→commercial, 사무실→office, 주택→house
- 전화번호만 보내도(draft에 매물 정보 있으면) → contact_phone 저장 + action: confirm

JSON으로만 응답 (null 필드는 생략):
{
  "intent": "property_data|update|off_topic",
  "updates": {
    "type": "매매|전세|월세|반전세",
    "price": "7억",
    "price_number": 700000000,
    "deposit": null,
    "monthly_rent": null,
    "location": "중랑구 신내동",
    "complex": "영풍마드레빌",
    "area": "32평",
    "floor": "10층",
    "contact_name": "박사장",
    "contact_phone": "010-1234-5678",
    "contact_skipped": false,
    "features": ["남향", "깨끗해"],
    "category": "apartment"
  },
  "reply": "자연스러운 한국어 응답 (1~2줄)",
  "action": "continue|confirm",
  "missing_question": "다음 질문 (action이 continue일 때만)"
}`
  }

  // 손님 등록 모드
  return `당신은 한국 부동산 중개사의 AI 어시스턴트입니다.
중개사가 손님 조건을 텔레그램으로 자유롭게 말합니다. 정보를 추출하고 자연스럽게 대화합니다.

현재까지 파악된 정보:
${draftJson}

필수 정보 4가지 (이것만 있으면 confirm):
1. trade (거래유형): 매매/전세/월세/반전세
2. location (지역): 구+동 또는 단지명 수준
3. price (가격/예산): 금액
4. contact (손님 연락처): 이름 또는 전화번호 중 하나만 있어도 됨

category(매물종류)는 선택사항 — 없어도 confirm 가능

규칙:
- 부동산 손님 조건과 무관한 메시지 → intent: off_topic
  reply는 메시지 내용을 자연스럽게 인정하되 봇 기능 짧게 안내
- "찾아요", "원해요", "원하는", "구해요", "살고 싶어", "가능" 등 수요 표현 → intent: client_data
- 이미 파악된 필드는 다시 묻지 말 것
- draft에 있는 필드는 이미 채워진 것. 절대 다시 묻지 말 것
- confirm 조건: trade + location + price + contact(이름 또는 전화번호 중 하나) 4개 있으면 반드시 confirm
  (category/층수/단지명/면적 없어도 confirm. draft 포함해서 판단)
  contact는 이름 하나만 있어도 됨. 전화번호 하나만 있어도 됨. 둘 다 필요 없음.
- "모름", "없어", "나중에", "스킵" 발화 시 해당 필드 스킵 처리 후 나머지 필드로 진행
- draft에 정보 있는 상태에서 추가 발화(특징, 층수 등)가 들어오면 → intent: update, action: confirm (이미 필수 4개 있으면)
- 질문은 딱 하나만. 한 번에 1개만 물어볼 것
- 가격 숫자 변환: 5억→500000000, 보증금1000 월60→deposit:10000000,monthly_rent:60000
- category: 아파트→apartment, 오피스텔→officetel, 빌라→villa,
            원룸→room, 상가→commercial, 사무실→office, 주택→house

JSON으로만 응답 (null 필드는 생략):
{
  "intent": "client_data|update|off_topic",
  "updates": {
    "wanted_trade_type": "전세",
    "price": "5억 이하",
    "price_number": 500000000,
    "deposit": null,
    "monthly_rent": null,
    "location": "강남구",
    "complex": null,
    "category": "apartment",
    "contact_name": "홍길동",
    "contact_phone": "010-1234-5678",
    "features": []
  },
  "reply": "자연스러운 한국어 응답 (1~2줄)",
  "action": "continue|confirm",
  "missing_question": "다음 질문 (action이 continue일 때만)"
}`
}

// ========== JSON 안전 파싱 ==========

function parseJsonSafe(text: string): any {
  try {
    const cleaned = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim()
    const start = cleaned.indexOf('{')
    const end = cleaned.lastIndexOf('}')
    if (start === -1 || end === -1) throw new Error('no json')
    return JSON.parse(cleaned.slice(start, end + 1))
  } catch {
    // JSON 파싱 실패 → 안전한 fallback
    return {
      intent: 'off_topic',
      updates: {},
      reply: '말씀해주신 내용을 이해했어요. 계속 알려주세요.',
      action: 'continue',
    }
  }
}

// ========== null/undefined 필드 제거 ==========

function cleanUpdates(updates: any): Record<string, unknown> {
  if (!updates || typeof updates !== 'object') return {}
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(updates)) {
    if (v !== null && v !== undefined && v !== '') result[k] = v
    if (Array.isArray(v) && v.length === 0) continue
  }
  return result
}

// ========== Main ==========

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('ok')

  // 내부 호출 인증
  const internalHeader = req.headers.get('x-hwik-internal') || ''
  if (!HWIK_INTERNAL_SECRET || internalHeader !== HWIK_INTERNAL_SECRET) {
    return new Response('unauthorized', { status: 401 })
  }

  let body: any
  try {
    body = await req.json()
  } catch {
    return new Response('bad request', { status: 400 })
  }

  const { text, draft, draft_type, mode = 'register' } = body

  if (!text || !draft_type) {
    return new Response(
      JSON.stringify({ error: 'text, draft_type required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    )
  }

  // DB에 최적화된 프롬프트가 있으면 사용, 없으면 하드코딩 fallback
  const dbPrompt = mode === 'register' ? await loadPrompt(draft_type) : null
  const basePrompt = dbPrompt || buildPrompt(draft_type, draft || {}, mode)
  // draft 컨텍스트를 프롬프트에 주입 (DB 프롬프트는 {DRAFT} 플레이스홀더 사용)
  const prompt = basePrompt.includes('{DRAFT}')
    ? basePrompt.replace('{DRAFT}', JSON.stringify(draft || {}, null, 2))
    : dbPrompt
      ? basePrompt + `\n\n현재까지 파악된 정보:\n${JSON.stringify(draft || {}, null, 2)}`
      : basePrompt

  // Claude Haiku 호출 (25초 타임아웃)
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 25000)

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 600,
        messages: [
          {
            role: 'user',
            content: `${prompt}\n\n중개사 메시지: "${text}"`,
          },
        ],
      }),
    })
    clearTimeout(timeoutId)

    const data = await response.json()
    if (data.error) {
      return new Response(
        JSON.stringify({ error: data.error.message }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      )
    }

    const rawText = data.content?.[0]?.text || ''
    const result = parseJsonSafe(rawText)
    result.updates = cleanUpdates(result.updates)

    return new Response(JSON.stringify(result), {
      headers: { 'Content-Type': 'application/json' },
    })

  } catch (e: any) {
    clearTimeout(timeoutId)

    // 타임아웃
    if (e.name === 'AbortError') {
      return new Response(
        JSON.stringify({
          intent: 'off_topic',
          updates: {},
          reply: '잠깐 생각 중이에요. 다시 한 번 말씀해 주세요.',
          action: 'continue',
        }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ error: e.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    )
  }
})
