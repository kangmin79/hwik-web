// eval-agent — Haiku 데이터 수집 루프
//
// 매 run:
//   1) 고정 20개 + 새 시나리오 10개 실행 (Haiku only)
//   2) 전체 결과 DB 저장 (eval_runs + eval_cases)
//   3) 50 run마다 auto-improve 호출 (Sonnet 배치 분석)
//
// 프롬프트 개선은 auto-improve가 담당 — 여기선 데이터만 수집

import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!
const HWIK_INTERNAL_SECRET = Deno.env.get('HWIK_INTERNAL_SECRET') || ''
const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
const SERVICE_ROLE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
const ANON_KEY = Deno.env.get('HWIK_ANON_KEY') || Deno.env.get('SUPABASE_ANON_KEY')!

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false }
})

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

// ========== 고정 기준 시나리오 20개 ==========

const FIXED_SCENARIOS = [
  { id:1,  message:'래미안 84 전세 5억 3층 깨끗해요 김철수 010-1234-5678', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'confirm' },
  { id:2,  message:'강남구 도곡동 빌라 월세 150만원 박영희 010-5678-1234', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'confirm' },
  { id:3,  message:'반전세 보증금5천 월50 강서구 화곡동 빌라 010-6666-7777', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'confirm' },
  { id:4,  message:'강남 아파 매매 10억 홍사장 010-9999-8888', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'confirm' },
  { id:5,  message:'월세 100 보증 500 마포 원룸 이름 최씨 연락 없음', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'confirm' },
  { id:6,  message:'송파구 잠실 롯데캐슬 84 매매 12억 남향 고층', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'continue' },
  { id:7,  message:'은평구 신사동 빌라 전세 1억5천 깨끗하고 조용함', draft_type:'property', draft:{}, expected_intent:'property_data', expected_action:'continue' },
  { id:8,  message:'010-1234-5678', draft_type:'property', draft:{type:'전세',price:'5억',price_number:500000000,location:'강남구',complex:'래미안'}, expected_intent:'property_data', expected_action:'confirm' },
  { id:9,  message:'없음', draft_type:'property', draft:{type:'매매',price:'7억',location:'중랑구',complex:'영풍마드레빌'}, expected_intent:'property_data', expected_action:'confirm' },
  { id:10, message:'나중에', draft_type:'property', draft:{type:'전세',price:'4억',location:'서초구'}, expected_intent:'property_data', expected_action:'confirm' },
  { id:11, message:'강남구 아파트 전세 5억 이하 홍길동 010-0000-1111', draft_type:'client', draft:{}, expected_intent:'client_data', expected_action:'confirm' },
  { id:12, message:'마포구 합정 원룸 월세 60만 이하 찾아요 이지은 010-2222-0000', draft_type:'client', draft:{}, expected_intent:'client_data', expected_action:'confirm' },
  { id:13, message:'분당 판교 오피스텔 매매 3억대 원하는 박준호 010-3030-4040', draft_type:'client', draft:{}, expected_intent:'client_data', expected_action:'confirm' },
  { id:14, message:'홍길동이요 연락처는 010-9999-0000', draft_type:'client', draft:{wanted_trade_type:'전세',location:'강남구',price:'5억 이하',price_number:500000000}, expected_intent:'client_data', expected_action:'confirm' },
  { id:15, message:'강남구 아파트 전세 찾고 있어요', draft_type:'client', draft:{}, expected_intent:'client_data', expected_action:'continue' },
  { id:16, message:'월세 싼 거 있어요?', draft_type:'client', draft:{}, expected_intent:'client_data', expected_action:'continue' },
  { id:17, message:'내일 3시에 강동욱 손님 방문 예정', draft_type:'property', draft:{}, expected_intent:'off_topic', expected_action:'continue' },
  { id:18, message:'안녕하세요 오늘도 화이팅해요!', draft_type:'property', draft:{}, expected_intent:'off_topic', expected_action:'continue' },
  { id:19, message:'계약 완료됐습니다 감사합니다', draft_type:'property', draft:{}, expected_intent:'off_topic', expected_action:'continue' },
  { id:20, message:'모름', draft_type:'client', draft:{wanted_trade_type:'전세',location:'강남',price:'5억',contact_phone:'010-1234-5678'}, expected_intent:'client_data', expected_action:'confirm' },
]

// ========== Haiku 헬퍼 ==========

async function callHaiku(prompt: string): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1500,
      messages: [{ role: 'user', content: prompt }],
    }),
  })
  const data = await res.json()
  if (data.error) throw new Error(data.error.message)
  return data.content?.[0]?.text || ''
}

function parseJson(text: string): any {
  try {
    const c = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim()
    const a = c.indexOf('['), b = c.lastIndexOf(']')
    const x = c.indexOf('{'), y = c.lastIndexOf('}')
    if (a !== -1 && b !== -1 && (x === -1 || a < x)) return JSON.parse(c.slice(a, b + 1))
    if (x !== -1 && y !== -1) return JSON.parse(c.slice(x, y + 1))
    return null
  } catch { return null }
}

// ========== 새 시나리오 10개 생성 (매 run마다 다른 엣지케이스) ==========

async function generateNewScenarios(runId: string): Promise<any[]> {
  // 이전 run들에서 자주 실패한 패턴 조회
  const { data: recentFails } = await admin
    .from('eval_cases')
    .select('message, expected_action, actual_action, draft_type')
    .eq('pass', false)
    .order('created_at', { ascending: false })
    .limit(20)

  const failPatterns = recentFails?.map(f =>
    `"${f.message}" (${f.draft_type}, expected:${f.expected_action}, got:${f.actual_action})`
  ).join('\n') || '없음'

  const raw = await callHaiku(`한국 부동산 중개사 텔레그램 봇 테스트 시나리오 10개를 JSON 배열로만 출력하세요.

최근 자주 실패한 패턴:
${failPatterns}

위 패턴과 비슷한 어려운 케이스 + 다양한 새 케이스를 섞어서.

[{"id":201,"message":"실제 메시지","draft_type":"property|client","draft":{},"expected_intent":"property_data|client_data|off_topic","expected_action":"continue|confirm","note":"포인트"}]

규칙:
- 실제 중개사 말투 (구어체, 오타, 줄임말)
- property 7개, client 2개, off_topic 1개
- JSON만 출력`)

  const parsed = parseJson(raw)
  return Array.isArray(parsed) ? parsed.slice(0, 10).map((s: any, i: number) => ({
    ...s,
    id: 200 + i,
    is_generated: true,
  })) : []
}

// ========== telegram-agent 호출 ==========

async function callAgent(text: string, draft: any, draftType: 'property' | 'client'): Promise<any> {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/telegram-agent`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${ANON_KEY}`,
      'apikey': ANON_KEY,
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
    },
    body: JSON.stringify({ text, draft, draft_type: draftType, mode: 'register' }),
  })
  if (!res.ok) return { error: `HTTP ${res.status}`, intent: null, action: null }
  return res.json()
}

// ========== 시나리오 실행 ==========

async function runScenario(s: any): Promise<any> {
  const start = Date.now()
  const result = await callAgent(s.message, s.draft || {}, s.draft_type || 'property')
  return {
    case_id: s.id,
    draft_type: s.draft_type || 'property',
    message: s.message,
    draft_json: s.draft || {},
    expected_intent: s.expected_intent,
    expected_action: s.expected_action,
    actual_intent: result.intent,
    actual_action: result.action,
    actual_reply: result.reply,
    actual_updates: result.updates,
    pass: result.intent === s.expected_intent && result.action === s.expected_action,
    latency_ms: Date.now() - start,
    error: result.error || null,
  }
}

// ========== auto-improve 트리거 판단 ==========

async function shouldTriggerImprove(): Promise<boolean> {
  // 마지막 개선 이후 50 run이 쌓였으면 true
  const { count } = await admin
    .from('eval_runs')
    .select('id', { count: 'exact', head: true })
    .eq('improved', false)
    .gte('created_at', new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString())

  return (count || 0) >= 50
}

async function triggerAutoImprove(): Promise<void> {
  await fetch(`${SUPABASE_URL}/functions/v1/auto-improve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
    },
    body: JSON.stringify({}),
  }).catch(() => {})
}

// ========== Main ==========

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('ok')

  const internalHeader = req.headers.get('x-hwik-internal') || ''
  if (!HWIK_INTERNAL_SECRET || internalHeader !== HWIK_INTERNAL_SECRET)
    return new Response('unauthorized', { status: 401 })

  const runId = crypto.randomUUID()
  const startTotal = Date.now()

  // 1) 새 시나리오 생성
  const newScenarios = await generateNewScenarios(runId).catch(() => [])
  const allScenarios = [...FIXED_SCENARIOS, ...newScenarios]

  // 2) 순차 실행 (300ms 간격, API 제한 방지)
  const results: any[] = []
  for (const s of allScenarios) {
    results.push(await runScenario(s))
    await sleep(300)
  }

  const passCount = results.filter(r => r.pass).length
  const total = results.length
  const accuracy = passCount / total

  // 3) DB 저장 — eval_runs
  const { data: runRow } = await admin
    .from('eval_runs')
    .insert({
      run_id: runId,
      pass_count: passCount,
      total_count: total,
      single_accuracy: accuracy,
      multi_accuracy: null,
      duration_ms: Date.now() - startTotal,
      improved: false,
    })
    .select('id')
    .single()

  // 4) DB 저장 — eval_cases (개별 케이스)
  const caseRows = results.map(r => ({
    run_id: runId,
    case_type: 'single',
    ...r,
  }))
  await admin.from('eval_cases').insert(caseRows).catch(() => {})

  // 5) 50 run마다 auto-improve 비동기 트리거
  const shouldImprove = await shouldTriggerImprove()
  if (shouldImprove) {
    triggerAutoImprove() // 비동기, 결과 안 기다림
  }

  return new Response(JSON.stringify({
    run_id: runId,
    pass: passCount,
    total,
    accuracy: Math.round(accuracy * 100) + '%',
    duration_ms: Date.now() - startTotal,
    auto_improve_triggered: shouldImprove,
    failures: results.filter(r => !r.pass).map(r => ({
      id: r.case_id,
      message: r.message?.slice(0, 40),
      expected: r.expected_action,
      actual: r.actual_action,
    })),
  }, null, 2), { headers: { 'Content-Type': 'application/json' } })
})
