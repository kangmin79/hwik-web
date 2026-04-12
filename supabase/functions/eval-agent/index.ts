// eval-agent — telegram-agent 자동 평가 시스템
//
// 사용:
//   curl -X POST https://jqaxejgzkchxbfzgzyzi.supabase.co/functions/v1/eval-agent \
//     -H "x-hwik-internal: <secret>" -H "Content-Type: application/json" -d '{}'
//
// 흐름:
//   1) Claude가 실제 중개사 대화 시나리오 30개 생성
//   2) 각 시나리오를 telegram-agent에 병렬 실행
//   3) Claude가 결과 전체를 평가 (의도 분류 정확도, 필드 추출, 자연스러움)
//   4) 개선 제안 포함한 리포트 반환

import "jsr:@supabase/functions-js/edge-runtime.d.ts"

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!
const HWIK_INTERNAL_SECRET = Deno.env.get('HWIK_INTERNAL_SECRET') || ''
const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
const ANON_KEY = Deno.env.get('HWIK_ANON_KEY') || Deno.env.get('SUPABASE_ANON_KEY')!

// ========== Claude 호출 헬퍼 ==========

async function claude(prompt: string, maxTokens = 2000): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: prompt }],
    }),
  })
  const data = await res.json()
  return data.content?.[0]?.text || ''
}

function parseJson(text: string): any {
  try {
    // 마크다운 코드 블록 제거
    const cleaned = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim()
    const arrStart = cleaned.indexOf('[')
    const arrEnd = cleaned.lastIndexOf(']')
    const objStart = cleaned.indexOf('{')
    const objEnd = cleaned.lastIndexOf('}')
    // 배열이 있으면 배열 우선
    if (arrStart !== -1 && arrEnd !== -1 && (objStart === -1 || arrStart < objStart)) {
      return JSON.parse(cleaned.slice(arrStart, arrEnd + 1))
    }
    if (objStart !== -1 && objEnd !== -1) {
      return JSON.parse(cleaned.slice(objStart, objEnd + 1))
    }
    return null
  } catch {
    return null
  }
}

// ========== 1단계: 시나리오 생성 ==========

async function generateScenarios(): Promise<any[]> {
  const raw = await claude(`한국 부동산 중개사가 텔레그램 봇에 보내는 실제 메시지 20개를 JSON 배열로만 출력하세요. 다른 말 없이 JSON만.

유형별:
- 매물 등록 완전한 정보 (type+price+location+contact): 6개
- 매물 등록 정보 부족 (일부만): 4개
- 손님 등록 완전한 정보: 4개
- 손님 등록 정보 부족: 3개
- 무관 메시지 (일정/인사): 3개

실제 중개사처럼 자연스럽게 (구어체, 줄임말 포함).

[{"id":1,"message":"래미안 84 전세 5억 3층 깨끗해요 김철수 010-1234-5678","draft_type":"property","draft":{},"expected_intent":"property_data","expected_action":"confirm","expected_fields":["type","price","location","contact_phone"],"note":"완전한 매물 정보"},{"id":2,"message":"강남 아파트 전세 5억 이하 찾는 홍길동","draft_type":"client","draft":{},"expected_intent":"client_data","expected_action":"continue","expected_fields":["location","wanted_trade_type","price"],"note":"연락처 누락"}]

위 형식으로 20개 만들어주세요.`, 3000)

  const parsed = parseJson(raw)
  return Array.isArray(parsed) ? parsed : []
}

// ========== 2단계: telegram-agent 실행 ==========

async function runAgent(scenario: any): Promise<any> {
  const start = Date.now()
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/telegram-agent`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ANON_KEY}`,
        'apikey': ANON_KEY,
        'x-hwik-internal': HWIK_INTERNAL_SECRET,
      },
      body: JSON.stringify({
        text: scenario.message,
        draft: scenario.draft || {},
        draft_type: scenario.draft_type || 'property',
        mode: 'register',
      }),
    })
    const result = await res.json()
    return {
      scenario_id: scenario.id,
      message: scenario.message,
      expected_intent: scenario.expected_intent,
      expected_action: scenario.expected_action,
      expected_fields: scenario.expected_fields,
      note: scenario.note,
      actual_intent: result.intent,
      actual_action: result.action,
      actual_updates: result.updates,
      actual_reply: result.reply,
      actual_missing_question: result.missing_question,
      latency_ms: Date.now() - start,
      error: null,
    }
  } catch (e: any) {
    return {
      scenario_id: scenario.id,
      message: scenario.message,
      error: e.message,
      latency_ms: Date.now() - start,
    }
  }
}

// ========== 3단계: 평가 ==========

async function evaluate(results: any[]): Promise<any> {
  const summary = results.map(r => ({
    id: r.scenario_id,
    msg: r.message,
    expected: { intent: r.expected_intent, action: r.expected_action, fields: r.expected_fields },
    actual: { intent: r.actual_intent, action: r.actual_action, updates: r.actual_updates, reply: r.actual_reply },
    error: r.error,
    note: r.note,
  }))

  const raw = await claude(`
당신은 AI 시스템 평가 전문가입니다.
부동산 중개사 텔레그램 AI 에이전트(telegram-agent)의 응답을 평가해주세요.

테스트 결과:
${JSON.stringify(summary, null, 2)}

각 항목을 평가하고 전체 분석 리포트를 JSON으로 출력하세요:

{
  "total": 30,
  "pass": 개수,
  "fail": 개수,
  "intent_accuracy": 0.0~1.0,
  "avg_latency_ms": 숫자,
  "failures": [
    {
      "id": 번호,
      "message": "원본 메시지",
      "problem": "무엇이 잘못됐나",
      "expected": "기대했던 것",
      "actual": "실제 결과"
    }
  ],
  "weak_spots": ["자주 틀리는 패턴 설명"],
  "prompt_improvements": [
    "구체적인 프롬프트 개선 제안 (실제 문구 포함)"
  ],
  "overall_score": "A/B/C/D/F",
  "summary": "전체 평가 요약 (한국어, 3줄)"
}`, 3000)

  return parseJson(raw) || { error: 'evaluation parse failed', raw }
}

// ========== Main ==========

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('ok')

  const internalHeader = req.headers.get('x-hwik-internal') || ''
  if (!HWIK_INTERNAL_SECRET || internalHeader !== HWIK_INTERNAL_SECRET) {
    return new Response('unauthorized', { status: 401 })
  }

  const startTotal = Date.now()

  try {
    // 1) 시나리오 생성
    console.log('Phase 1: Generating scenarios...')
    const scenarios = await generateScenarios()
    if (!scenarios.length) {
      return new Response(JSON.stringify({ error: 'scenario generation failed' }), {
        status: 500, headers: { 'Content-Type': 'application/json' }
      })
    }
    console.log(`Generated ${scenarios.length} scenarios`)

    // 2) 순차 실행 (API 속도 제한 방지 — 병렬이면 절반이 빈 응답 반환)
    console.log('Phase 2: Running telegram-agent sequentially...')
    const results = []
    for (const s of scenarios) {
      results.push(await runAgent(s))
    }
    console.log('All runs complete')

    // 3) 평가
    console.log('Phase 3: Evaluating results...')
    const evaluation = await evaluate(results)

    const report = {
      generated_at: new Date().toISOString(),
      total_duration_ms: Date.now() - startTotal,
      scenarios_count: scenarios.length,
      evaluation,
      raw_results: results,
    }

    return new Response(JSON.stringify(report, null, 2), {
      headers: { 'Content-Type': 'application/json' },
    })

  } catch (e: any) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 500, headers: { 'Content-Type': 'application/json' }
    })
  }
})
