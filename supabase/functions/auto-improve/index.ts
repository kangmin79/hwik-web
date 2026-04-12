// auto-improve — Sonnet 배치 프롬프트 최적화
//
// eval-agent가 50 run 쌓이면 자동 트리거
// 수백 개 실패 케이스를 Sonnet에 한번에 분석시켜 프롬프트 대수술
//
// Input: {} (파라미터 없음)
// Output: { improved, property_score, client_score, changes_summary }

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

// ========== Sonnet 호출 ==========

async function callSonnet(prompt: string, maxTokens = 3000): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: prompt }],
    }),
  })
  const data = await res.json()
  if (data.error) throw new Error(data.error.message)
  return data.content?.[0]?.text || ''
}

// ========== 현재 프롬프트 로드 ==========

async function getCurrentPrompt(draftType: string): Promise<{ id: number; text: string; version: number } | null> {
  const { data } = await admin
    .from('agent_prompts')
    .select('id, prompt_text, version')
    .eq('draft_type', draftType)
    .eq('is_current', true)
    .order('version', { ascending: false })
    .limit(1)
    .maybeSingle()
  return data ? { id: data.id, text: data.prompt_text, version: data.version } : null
}

// ========== 배치 실패 케이스 로드 ==========

async function loadRecentFailures(draftType: string, limit = 200): Promise<any[]> {
  const { data } = await admin
    .from('eval_cases')
    .select('message, draft_json, expected_intent, expected_action, actual_intent, actual_action, actual_reply')
    .eq('pass', false)
    .eq('draft_type', draftType)
    .order('created_at', { ascending: false })
    .limit(limit)
  return data || []
}

async function loadRecentSuccesses(draftType: string, limit = 50): Promise<any[]> {
  const { data } = await admin
    .from('eval_cases')
    .select('message, expected_action, actual_reply')
    .eq('pass', true)
    .eq('draft_type', draftType)
    .order('created_at', { ascending: false })
    .limit(limit)
  return data || []
}

// ========== 단일 케이스로 telegram-agent 테스트 ==========

async function quickTest(message: string, draft: any, draftType: string): Promise<any> {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/telegram-agent`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${ANON_KEY}`,
      'apikey': ANON_KEY,
      'x-hwik-internal': HWIK_INTERNAL_SECRET,
    },
    body: JSON.stringify({ text: message, draft, draft_type: draftType }),
  })
  return res.ok ? res.json() : { error: 'failed' }
}

// ========== Sonnet으로 새 프롬프트 생성 ==========

async function generateImprovedPrompt(
  draftType: string,
  currentPrompt: string,
  failures: any[],
  successes: any[]
): Promise<string | null> {

  // 실패 패턴 분석
  const failSample = failures.slice(0, 150).map(f => ({
    msg: f.message?.slice(0, 50),
    draft: Object.keys(f.draft_json || {}).join(',') || 'empty',
    expected: f.expected_action,
    got: f.actual_action,
    reply: f.actual_reply?.slice(0, 60),
  }))

  const successSample = successes.slice(0, 30).map(s => ({
    msg: s.message?.slice(0, 40),
    action: s.expected_action,
  }))

  const prompt = `당신은 AI 프롬프트 최적화 전문가입니다.

부동산 중개사 텔레그램 봇의 [${draftType}] 등록 프롬프트를 개선해주세요.

=== 현재 프롬프트 ===
${currentPrompt}

=== 최근 실패 케이스 ${failures.length}건 중 샘플 ===
${JSON.stringify(failSample, null, 2)}

=== 최근 성공 케이스 샘플 ===
${JSON.stringify(successSample, null, 2)}

=== 분석 요청 ===
1. 실패 케이스들의 공통 패턴을 파악하세요
2. 현재 프롬프트에서 어떤 규칙이 부족하거나 잘못됐는지 찾으세요
3. 개선된 프롬프트를 작성하세요

중요:
- 현재 프롬프트 구조를 최대한 유지하되 문제가 되는 규칙만 수정/추가
- 프롬프트에 {DRAFT} 플레이스홀더를 반드시 포함 (draft 컨텍스트 주입 위치)
- 너무 길게 만들지 말 것 (현재 길이의 150% 이내)
- JSON 형식 유지 요구사항은 절대 변경 금지

아래 형식으로만 응답:
<improved_prompt>
[개선된 프롬프트 전문]
</improved_prompt>

<changes>
[무엇을 바꿨고 왜인지 3줄 요약]
</changes>`

  const response = await callSonnet(prompt, 4000)

  // 프롬프트 추출
  const promptMatch = response.match(/<improved_prompt>([\s\S]*?)<\/improved_prompt>/)
  return promptMatch ? promptMatch[1].trim() : null
}

// ========== 새 프롬프트 검증 (샘플 10개로 빠른 테스트) ==========

async function validatePrompt(newPromptText: string, draftType: string): Promise<number> {
  // DB에 임시 저장
  const { data: tmpPrompt } = await admin
    .from('agent_prompts')
    .insert({
      draft_type: draftType,
      prompt_text: newPromptText,
      is_current: false,
      version: 0,
      notes: 'validation_temp',
    })
    .select('id')
    .single()

  if (!tmpPrompt) return 0

  // 10개 고정 케이스로 빠른 검증 (순차)
  const FIXED = [
    { message:'래미안 84 전세 5억 3층 김철수 010-1234-5678', draft:{}, type:'property', expected:'confirm' },
    { message:'없음', draft:{type:'매매',price:'7억',location:'중랑구'}, type:'property', expected:'confirm' },
    { message:'010-1234-5678', draft:{type:'전세',price:'5억',location:'강남구'}, type:'property', expected:'confirm' },
    { message:'송파구 아파트 매매 12억', draft:{}, type:'property', expected:'continue' },
    { message:'내일 3시 방문 예정', draft:{}, type:'property', expected:'continue' },
    { message:'강남구 아파트 전세 5억 홍길동 010-0000-1111', draft:{}, type:'client', expected:'confirm' },
    { message:'홍길동 010-9999-0000', draft:{wanted_trade_type:'전세',location:'강남구',price:'5억'}, type:'client', expected:'confirm' },
    { message:'모름', draft:{wanted_trade_type:'전세',location:'강남',price:'5억',contact_phone:'010-1234-5678'}, type:'client', expected:'confirm' },
    { message:'강남 아파트 전세 찾아요', draft:{}, type:'client', expected:'continue' },
    { message:'계약 완료됐어요', draft:{}, type:'client', expected:'continue' },
  ]

  let pass = 0
  for (const tc of FIXED) {
    if (tc.type !== draftType) { pass++; continue } // 다른 타입은 패스
    const result = await quickTest(tc.message, tc.draft, tc.type as any)
    if (result.action === tc.expected) pass++
    await sleep(300)
  }

  // 임시 프롬프트 삭제
  await admin.from('agent_prompts').delete().eq('id', tmpPrompt.id)

  return pass / FIXED.length
}

// ========== 새 프롬프트 DB 저장 ==========

async function saveNewPrompt(
  draftType: string,
  currentId: number,
  newText: string,
  score: number,
  currentVersion: number,
  changes: string
): Promise<number> {
  // 기존 current 해제
  await admin.from('agent_prompts').update({ is_current: false }).eq('id', currentId)

  // 새 버전 저장
  const { data } = await admin
    .from('agent_prompts')
    .insert({
      draft_type: draftType,
      prompt_text: newText,
      score,
      is_current: true,
      version: currentVersion + 1,
      notes: changes,
    })
    .select('id')
    .single()

  return data?.id || 0
}

// ========== 50 run 표시 ==========

async function markRunsAsImproved(): Promise<void> {
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString()
  await admin
    .from('eval_runs')
    .update({ improved: true })
    .eq('improved', false)
    .gte('created_at', since)
}

// ========== Main ==========

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('ok')

  const internalHeader = req.headers.get('x-hwik-internal') || ''
  if (!HWIK_INTERNAL_SECRET || internalHeader !== HWIK_INTERNAL_SECRET)
    return new Response('unauthorized', { status: 401 })

  const startTotal = Date.now()
  const report: any = {
    triggered_at: new Date().toISOString(),
    property: { improved: false },
    client: { improved: false },
  }

  for (const draftType of ['property', 'client'] as const) {
    try {
      // 현재 프롬프트
      const current = await getCurrentPrompt(draftType)
      const currentText = current?.text || ''
      const currentVersion = current?.version || 0

      if (!currentText) {
        report[draftType].error = 'no current prompt in DB'
        continue
      }

      // 실패/성공 케이스 로드
      const failures = await loadRecentFailures(draftType, 200)
      const successes = await loadRecentSuccesses(draftType, 50)

      report[draftType].failure_count = failures.length
      report[draftType].success_count = successes.length

      if (failures.length < 10) {
        report[draftType].skipped = 'not enough failures yet'
        continue
      }

      // Sonnet으로 개선된 프롬프트 생성
      const newPromptText = await generateImprovedPrompt(draftType, currentText, failures, successes)
      if (!newPromptText) {
        report[draftType].error = 'prompt generation failed'
        continue
      }

      // 빠른 검증
      const newScore = await validatePrompt(newPromptText, draftType)
      report[draftType].new_score = Math.round(newScore * 100) + '%'

      // 현재 점수 계산
      const { data: recentRun } = await admin
        .from('eval_runs')
        .select('single_accuracy')
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()
      const currentScore = recentRun?.single_accuracy || 0

      // 개선됐으면 저장
      if (newScore > currentScore + 0.02) { // 2%p 이상 개선시만 적용
        const changes = `v${currentVersion + 1}: ${failures.length}개 실패 분석 → 점수 ${Math.round(currentScore*100)}%→${Math.round(newScore*100)}%`
        await saveNewPrompt(draftType, current!.id, newPromptText, newScore, currentVersion, changes)
        report[draftType].improved = true
        report[draftType].version = currentVersion + 1
        report[draftType].score_change = `${Math.round(currentScore*100)}% → ${Math.round(newScore*100)}%`
      } else {
        report[draftType].improved = false
        report[draftType].reason = `new score ${Math.round(newScore*100)}% not better than current ${Math.round(currentScore*100)}%`
      }

    } catch (e: any) {
      report[draftType].error = e.message
    }
  }

  // 50 run 처리 완료 표시
  await markRunsAsImproved()

  report.duration_ms = Date.now() - startTotal

  return new Response(JSON.stringify(report, null, 2), {
    headers: { 'Content-Type': 'application/json' }
  })
})
