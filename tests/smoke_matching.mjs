#!/usr/bin/env node
// 매칭 E2E 매트릭스 테스트 — 브라우저와 동일한 HTTP 경로로 호출
// 실행: node tests/smoke_matching.mjs [--only S01,S02]
// 전제: .env.test에 HWIK_TEST_JWT, HWIK_TEST_AGENT_ID 설정됨

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

function loadEnv() {
  try {
    const raw = readFileSync(resolve(ROOT, '.env.test'), 'utf8');
    for (const line of raw.split(/\r?\n/)) {
      const m = line.match(/^([A-Z_]+)=(.*)$/);
      if (m) process.env[m[1]] = m[2].trim();
    }
  } catch { /* no .env.test */ }
}
loadEnv();

const SUPABASE_URL = 'https://api.hwik.kr';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxYXhlamd6a2NoeGJmemd6eXppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2MzI3NTIsImV4cCI6MjA4MjIwODc1Mn0.-njNdAKVA7Me60H98AYaf-Z3oi45SfUmeoBNvuRJugE';
const JWT = process.env.HWIK_TEST_JWT || '';
const AGENT_ID = process.env.HWIK_TEST_AGENT_ID || '';

if (!JWT || !AGENT_ID) {
  console.error('❌ .env.test에 HWIK_TEST_JWT, HWIK_TEST_AGENT_ID 설정 필요');
  process.exit(1);
}

const TEST_PREFIX = 'test_';
const onlyArg = (process.argv.find(a => a.startsWith('--only=')) || '').replace('--only=', '');
const onlyIds = onlyArg ? onlyArg.split(',').map(s => s.trim()) : null;
const concurrencyArg = (process.argv.find(a => a.startsWith('--concurrency=')) || '').replace('--concurrency=', '');
const CONCURRENCY = Math.max(1, parseInt(concurrencyArg || '1') || 1);
const fileArg = (process.argv.find(a => a.startsWith('--file=')) || '').replace('--file=', '');
const SCENARIOS_FILE = fileArg || 'scenarios.json';

// ─ HTTP (브라우저와 동일한 헤더) ─
async function sbFetch(path, opts = {}) {
  const url = path.startsWith('http') ? path : `${SUPABASE_URL}${path}`;
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${JWT}`,
    'apikey': SUPABASE_KEY,
    ...(opts.headers || {}),
  };
  for (let attempt = 1; attempt <= 3; attempt++) {
    const res = await fetch(url, { ...opts, headers });
    const text = await res.text();
    let body;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (res.ok || ![502, 503, 504].includes(res.status) || attempt === 3) {
      return { ok: res.ok, status: res.status, body };
    }
    await new Promise(r => setTimeout(r, 800 * attempt));
  }
}

async function parseProperty(text) {
  const r = await sbFetch('/functions/v1/parse-property', {
    method: 'POST', body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`parse-property ${r.status}: ${JSON.stringify(r.body).slice(0, 200)}`);
  return r.body;
}

async function insertCard(cardData) {
  const r = await sbFetch('/rest/v1/cards', {
    method: 'POST',
    headers: { 'Prefer': 'return=minimal' },
    body: JSON.stringify([cardData]),
  });
  if (!r.ok) throw new Error(`insert ${r.status}: ${JSON.stringify(r.body).slice(0, 200)}`);
}

async function fetchCard(id) {
  const r = await sbFetch(`/rest/v1/cards?id=eq.${id}&select=id,property,embedding,lat,lng,price_number,deposit,monthly_rent,tags,wanted_trade_type,wanted_categories,wanted_conditions`, { method: 'GET' });
  return Array.isArray(r.body) && r.body[0] ? r.body[0] : null;
}

async function autoMatch(cardId) {
  const r = await sbFetch('/functions/v1/auto-match', {
    method: 'POST', body: JSON.stringify({ card_id: cardId }),
  });
  if (!r.ok) throw new Error(`auto-match ${r.status}: ${JSON.stringify(r.body).slice(0, 200)}`);
  return r.body;
}

async function pairNotification(propId, cliId) {
  const r = await sbFetch(
    `/rest/v1/match_notifications?and=(card_id.eq.${propId},client_card_id.eq.${cliId})&select=id,similarity`,
    { method: 'GET' }
  );
  return Array.isArray(r.body) ? r.body : [];
}

async function deleteTestData() {
  await sbFetch(`/rest/v1/match_notifications?or=(card_id.like.${TEST_PREFIX}*,client_card_id.like.${TEST_PREFIX}*)`, { method: 'DELETE' });
  await sbFetch(`/rest/v1/cards?id=like.${TEST_PREFIX}*&agent_id=eq.${AGENT_ID}`, { method: 'DELETE' });
}

// ─ 카드 제작 (브라우저 registerClient/confirmSave와 동일 필드 구성) ─
function buildCardFromParse(id, text, parsed, asClient) {
  const base = {
    id, agent_id: AGENT_ID, style: 'noimg', color: 'blue',
    property: {
      type: asClient ? '손님' : (parsed.type || null),
      price: parsed.price || null, location: parsed.location || null,
      complex: parsed.complex || null, area: parsed.area || null,
      floor: parsed.floor || null, room: parsed.room || null,
      features: parsed.features || [], moveIn: parsed.moveIn || null,
      category: parsed.category || null, rawText: text,
    },
    private_note: { memo: parsed.memo || null, rawText: text },
    embedding: parsed.embedding || null,
    search_text: parsed.search_text || null,
    price_number: parsed.price_number || null,
    deposit: parsed.deposit || null,
    monthly_rent: parsed.monthly_rent || null,
    tags: parsed.tags || [],
    trade_status: '계약가능',
  };
  if (asClient) {
    base.wanted_trade_type = parsed.wanted_trade_type || null;
    base.wanted_categories = parsed.wanted_categories || [];
    base.wanted_conditions = parsed.wanted_conditions || [];
    base.client_status = '탐색중';
  }
  return base;
}

// ─ 시나리오 1개 실행 ─
async function runScenario(s, idx) {
  const ts = Date.now() + idx;
  const propId = `${TEST_PREFIX}p_${s.id}_${ts}`;
  const cliId = `${TEST_PREFIX}c_${s.id}_${ts}`;

  const diag = {};
  try {
    const pr = await parseProperty(s.property);
    await insertCard(buildCardFromParse(propId, s.property, pr, false));
    diag.prop = { price_number: pr.price_number, cat: pr.category, type: pr.type, embedding: !!pr.embedding };

    const cr = await parseProperty(s.client);
    await insertCard(buildCardFromParse(cliId, s.client, cr, true));
    diag.cli = { wanted_trade_type: cr.wanted_trade_type, wanted_cats: cr.wanted_categories, price_number: cr.price_number, embedding: !!cr.embedding, wanted_conditions: cr.wanted_conditions };

    // 진단: DB에 저장된 값 확인
    if (onlyIds) {
      const pRow = await fetchCard(propId);
      const cRow = await fetchCard(cliId);
      diag.propDb = { deposit: pRow?.deposit, monthly_rent: pRow?.monthly_rent, price_number: pRow?.price_number, lat: pRow?.lat, cat: pRow?.property?.category, loc: pRow?.property?.location };
      diag.cliDb = { deposit: cRow?.deposit, monthly_rent: cRow?.monthly_rent, price_number: cRow?.price_number, wanted_conditions: cRow?.wanted_conditions, wanted_cats: cRow?.wanted_categories, wanted_trade: cRow?.wanted_trade_type, cat: cRow?.property?.category };
    }

    const targetId = s.matchOn === 'property' ? propId : cliId;
    const m = await autoMatch(targetId);
    diag.match = { matched: m.matched, saved: m.saved, reason: m.reason };

    const notifs = await pairNotification(propId, cliId);
    // 정확한 판정: "이 페어"가 매칭됐는지 (사용자의 기존 실데이터 오염 배제)
    const actualMatch = notifs.length > 0;
    const expectMatch = s.expect === 'match';
    const pass = actualMatch === expectMatch;

    return { ...s, pass, actualMatch, notifs: notifs.length, diag };
  } catch (e) {
    return { ...s, pass: false, error: e.message, diag };
  } finally {
    // 각 시나리오 후 개별 정리
    await sbFetch(`/rest/v1/match_notifications?or=(card_id.eq.${propId},client_card_id.eq.${cliId})`, { method: 'DELETE' });
    await sbFetch(`/rest/v1/cards?id=in.(${propId},${cliId})&agent_id=eq.${AGENT_ID}`, { method: 'DELETE' });
  }
}

// ─ 메인 ─
async function main() {
  const startedAt = Date.now();
  const raw = readFileSync(resolve(__dirname, SCENARIOS_FILE), 'utf8');
  let scenarios = JSON.parse(raw);
  if (onlyIds) scenarios = scenarios.filter(s => onlyIds.includes(s.id));
  console.log(`매칭 매트릭스 테스트 시작 — ${scenarios.length}개 시나리오\n`);

  await deleteTestData();

  const results = new Array(scenarios.length);
  const total = scenarios.length;
  let done = 0;

  async function worker(startIdx) {
    for (let i = startIdx; i < scenarios.length; i += CONCURRENCY) {
      const s = scenarios[i];
      const r = await runScenario(s, i);
      results[i] = r;
      done++;
      const status = r.error ? '⚠️' : (r.pass ? '✅' : '❌');
      const line = r.error
        ? `${status} [${s.id}] ${s.axis} — ERROR ${r.error}`
        : `${status} [${s.id}] ${s.axis} — expect=${s.expect}, actual=${r.actualMatch ? 'match' : 'no-match'}${r.diag?.match?.reason ? ' (' + r.diag.match.reason + ')' : ''}`;
      console.log(`[${done}/${total}] ${line}`);
      if (onlyIds && r.diag?.propDb) {
        console.log(`    prop.db:`, JSON.stringify(r.diag.propDb));
        console.log(`    cli.db :`, JSON.stringify(r.diag.cliDb));
      }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, (_, k) => worker(k)));

  await deleteTestData();

  // 결과 표
  console.log('\n─────────── 결과 요약 ───────────');
  const pass = results.filter(r => r.pass).length;
  const fail = results.filter(r => !r.pass && !r.error).length;
  const err = results.filter(r => r.error).length;
  console.log(`✅ PASS: ${pass}   ❌ FAIL: ${fail}   ⚠️ ERROR: ${err}   총 ${results.length}\n`);

  // false negative / false positive 분류
  const fn = results.filter(r => !r.pass && !r.error && r.expect === 'match');
  const fp = results.filter(r => !r.pass && !r.error && r.expect === 'no-match');

  if (fn.length) {
    console.log('🔴 FALSE NEGATIVE (매칭돼야 하는데 안 됨):');
    for (const r of fn) {
      console.log(`  [${r.id}] ${r.axis} — reason=${r.diag?.match?.reason}, cli.wanted_trade=${r.diag?.cli?.wanted_trade_type}, cli.cats=${JSON.stringify(r.diag?.cli?.wanted_cats)}, prop.cat=${r.diag?.prop?.cat}, prop.emb=${r.diag?.prop?.embedding}`);
    }
  }
  if (fp.length) {
    console.log('\n🟠 FALSE POSITIVE (매칭되면 안 되는데 됨):');
    for (const r of fp) {
      console.log(`  [${r.id}] ${r.axis} — matched=${r.diag?.match?.matched}, notifs=${r.notifs}`);
    }
  }

  console.log(`\n⏱  ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
  process.exit(pass === results.length ? 0 : 1);
}

main().catch(e => { console.error('❌ 치명:', e.message); process.exit(1); });
