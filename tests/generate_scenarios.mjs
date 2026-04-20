#!/usr/bin/env node
// 시나리오 자동 생성기 — 축별 파라미터를 조합해서 다양한 테스트 케이스 생산
// 실행: node tests/generate_scenarios.mjs > tests/scenarios.json

// ─ 축 ─
const REGIONS = [
  // [손님용 키워드, 매물용 주소, 구(구/동 둘 다 잡는 단서), 동]
  { client: '강남 역삼', property: '강남 역삼 힐스테이트', gu: '강남', dong: '역삼' },
  { client: '강남 대치', property: '강남 대치 미도', gu: '강남', dong: '대치' },
  { client: '서초 반포', property: '서초 반포 자이', gu: '서초', dong: '반포' },
  { client: '서초 방배', property: '서초 방배 아크로', gu: '서초', dong: '방배' },
  { client: '송파 잠실', property: '송파 잠실 엘스', gu: '송파', dong: '잠실' },
  { client: '송파 문정', property: '송파 문정 올림픽훼밀리', gu: '송파', dong: '문정' },
  { client: '마포 공덕', property: '마포 공덕 래미안', gu: '마포', dong: '공덕' },
  { client: '마포 합정', property: '마포 합정 메세나폴리스', gu: '마포', dong: '합정' },
  { client: '용산 이촌', property: '용산 이촌 한가람', gu: '용산', dong: '이촌' },
  { client: '성동 성수', property: '성동 성수 갤러리아포레', gu: '성동', dong: '성수' },
  { client: '영등포 여의도', property: '영등포 여의도 삼부', gu: '영등포', dong: '여의도' },
  { client: '강서 마곡', property: '강서 마곡 엠밸리', gu: '강서', dong: '마곡' },
  { client: '양천 목동', property: '양천 목동 신시가지', gu: '양천', dong: '목동' },
  { client: '동작 상도', property: '동작 상도 래미안', gu: '동작', dong: '상도' },
  { client: '관악 신림', property: '관악 신림 푸르지오', gu: '관악', dong: '신림' },
  { client: '광진 자양', property: '광진 자양 더샵스타시티', gu: '광진', dong: '자양' },
  { client: '중랑 망우', property: '중랑 망우 금호어울림', gu: '중랑', dong: '망우' },
  { client: '노원 상계', property: '노원 상계 주공', gu: '노원', dong: '상계' },
  { client: '도봉 창동', property: '도봉 창동 힐스테이트', gu: '도봉', dong: '창동' },
  { client: '성북 길음', property: '성북 길음 래미안', gu: '성북', dong: '길음' },
];

// 전세 가격(만원) 후보 — 평당 3~10억 범위 다양하게
const JEONSE_PRICES = [15000, 25000, 35000, 45000, 55000, 70000, 90000, 120000]; // 1.5억 ~ 12억
const MAEMAE_PRICES = [50000, 80000, 120000, 180000, 250000, 350000, 500000]; // 5억 ~ 50억

// 월세(보증금/월세 만원) 후보
const WOLSE_COMBOS = [
  { dep: 500, mon: 40 }, { dep: 1000, mon: 60 }, { dep: 2000, mon: 80 },
  { dep: 3000, mon: 100 }, { dep: 5000, mon: 150 }, { dep: 10000, mon: 200 },
];

// 면적(평) 후보
const AREAS = [15, 18, 22, 25, 30, 33, 42, 50];

const CATEGORIES = [
  { key: 'apartment', word: '아파트' },
  { key: 'officetel', word: '오피스텔' },
  { key: 'room', word: '원룸' },
  { key: 'commercial', word: '상가' },
  { key: 'office', word: '사무실' },
];

// 원룸/오피스텔은 아파트 단지명이 있으면 parse-property가 category를 apartment로 오분류함
// → 단지명 없이 구·동만 사용
const propLoc = (r, cat) => {
  if (cat === '원룸' || cat === '오피스텔' || cat === 'room' || cat === 'officetel') return r.client;
  return r.property;
};

// ─ 헬퍼 ─
const priceToKor = (man) => {
  if (man >= 10000) {
    const ek = Math.floor(man / 10000);
    const rem = man % 10000;
    const chun = Math.floor(rem / 1000);
    return chun ? `${ek}억${chun}천` : `${ek}억`;
  }
  if (man >= 1000) return `${man / 1000}천`;
  return `${man}`;
};

let seq = 0;
const nextId = () => `G${String(++seq).padStart(3, '0')}`;

const scenarios = [];

// ═══ 1. 전세 × 20개 구 × 기본 매칭 (20개) ═══
for (const r of REGIONS) {
  const price = JEONSE_PRICES[seq % JEONSE_PRICES.length];
  const area = AREAS[seq % AREAS.length];
  const cat = seq % 2 === 0 ? CATEGORIES[0] : CATEGORIES[2]; // 아파트 or 원룸
  scenarios.push({
    id: nextId(),
    axis: `전세-${r.gu}-${cat.word}-기본`,
    property: `${propLoc(r, cat.word)} 전세 ${priceToKor(price)} ${cat.word} ${area}평`,
    client: `${r.client} 전세 ${priceToKor(price)} 이하 ${cat.word} 구합니다`,
    expect: 'match',
    matchOn: 'client',
  });
}

// ═══ 2. 전세 가격 초과 케이스 (20개) ═══
for (const r of REGIONS) {
  const priceHigh = JEONSE_PRICES[(seq + 3) % JEONSE_PRICES.length];
  const priceLow = Math.round(priceHigh * 0.5);
  const area = AREAS[seq % AREAS.length];
  scenarios.push({
    id: nextId(),
    axis: `전세-${r.gu}-가격초과`,
    property: `${r.property} 전세 ${priceToKor(priceHigh)} 아파트 ${area}평`,
    client: `${r.client} 전세 ${priceToKor(priceLow)} 이하 아파트 구합니다`,
    expect: 'no-match',
    matchOn: 'client',
  });
}

// ═══ 3. 매매 정확 매칭 (15개) ═══
for (let i = 0; i < 15; i++) {
  const r = REGIONS[i];
  const price = MAEMAE_PRICES[i % MAEMAE_PRICES.length];
  const area = AREAS[i % AREAS.length];
  scenarios.push({
    id: nextId(),
    axis: `매매-${r.gu}-정확`,
    property: `${r.property} 매매 ${priceToKor(price)} 아파트 ${area}평`,
    client: `${r.client} 매매 ${priceToKor(price)} 이하 아파트 찾아요`,
    expect: 'match',
    matchOn: 'client',
  });
}

// ═══ 4. 매매 가격 초과 (15개) ═══
for (let i = 0; i < 15; i++) {
  const r = REGIONS[i];
  const priceHigh = MAEMAE_PRICES[(i + 3) % MAEMAE_PRICES.length];
  const priceLow = Math.round(priceHigh * 0.5);
  scenarios.push({
    id: nextId(),
    axis: `매매-${r.gu}-가격초과`,
    property: `${r.property} 매매 ${priceToKor(priceHigh)} 아파트 30평`,
    client: `${r.client} 매매 ${priceToKor(priceLow)} 이하 아파트 찾아요`,
    expect: 'no-match',
    matchOn: 'client',
  });
}

// ═══ 5. 월세 정확 (20개) ═══ (원룸 → 단지명 제거)
for (let i = 0; i < 20; i++) {
  const r = REGIONS[i];
  const c = WOLSE_COMBOS[i % WOLSE_COMBOS.length];
  scenarios.push({
    id: nextId(),
    axis: `월세-${r.gu}-정확`,
    property: `${r.client} 월세 보증금 ${priceToKor(c.dep)} 월 ${c.mon} 원룸`,
    client: `${r.client} 월세 보증금 ${priceToKor(c.dep)} 월 ${c.mon} 이하 원룸 구해요`,
    expect: 'match',
    matchOn: 'client',
  });
}

// ═══ 6. 월세 월세초과 (15개) ═══ — property 월세가 반드시 client 월세를 초과하도록
for (let i = 0; i < 15; i++) {
  const r = REGIONS[i];
  const c = WOLSE_COMBOS[i % WOLSE_COMBOS.length];
  const propMon = Math.max(c.mon * 2, c.mon + 100); // client 월세보다 확실히 크게
  scenarios.push({
    id: nextId(),
    axis: `월세-${r.gu}-월세초과`,
    property: `${r.client} 월세 보증금 ${priceToKor(c.dep)} 월 ${propMon} 원룸`,
    client: `${r.client} 월세 보증금 ${priceToKor(c.dep)} 월 ${c.mon} 이하 원룸 구해요`,
    expect: 'no-match',
    matchOn: 'client',
  });
}

// ═══ 7. 월세 보증금초과 (15개) ═══ — property 보증금이 반드시 client 보증금을 초과하도록
for (let i = 0; i < 15; i++) {
  const r = REGIONS[i];
  const c = WOLSE_COMBOS[i % WOLSE_COMBOS.length];
  const propDep = Math.max(c.dep * 2, c.dep + 5000); // client 보증금보다 확실히 크게
  scenarios.push({
    id: nextId(),
    axis: `월세-${r.gu}-보증금초과`,
    property: `${r.client} 월세 보증금 ${priceToKor(propDep)} 월 ${c.mon} 원룸`,
    client: `${r.client} 월세 보증금 ${priceToKor(c.dep)} 월 ${c.mon} 이하 원룸 구해요`,
    expect: 'no-match',
    matchOn: 'client',
  });
}

// ═══ 8. 다른 구 (탈락) (20개) ═══
for (let i = 0; i < 20; i++) {
  const rProp = REGIONS[i];
  const rCli = REGIONS[(i + 10) % REGIONS.length]; // 멀리 떨어진 구
  scenarios.push({
    id: nextId(),
    axis: `다른구-${rProp.gu}vs${rCli.gu}`,
    property: `${rProp.property} 전세 4억 아파트 24평`,
    client: `${rCli.client} 전세 4억 이하 아파트 구합니다`,
    expect: 'no-match',
    matchOn: 'client',
  });
}

// ═══ 9. 카테고리 (25개) ═══
const CAT_MATCH_PAIRS = [
  { p: '아파트', c: '아파트', expect: 'match' },
  { p: '원룸', c: '원룸', expect: 'match' },
  { p: '오피스텔', c: '오피스텔', expect: 'match' },
  { p: '상가', c: '상가', expect: 'match' },
  { p: '사무실', c: '사무실', expect: 'match' },
  { p: '아파트', c: '원룸', expect: 'no-match' },
  { p: '원룸', c: '아파트', expect: 'no-match' },
  { p: '아파트', c: '상가', expect: 'no-match' },
  { p: '오피스텔', c: '아파트', expect: 'no-match' },
  { p: '상가', c: '사무실', expect: 'no-match' },
];
for (let i = 0; i < 25; i++) {
  const r = REGIONS[i % REGIONS.length];
  const pair = CAT_MATCH_PAIRS[i % CAT_MATCH_PAIRS.length];
  scenarios.push({
    id: nextId(),
    axis: `카테고리-${pair.p}vs${pair.c}-${pair.expect}`,
    property: `${propLoc(r, pair.p)} 전세 3억 ${pair.p} 20평`,
    client: `${r.client} 전세 3억 이하 ${pair.c} 구합니다`,
    expect: pair.expect,
    matchOn: 'client',
  });
}

// ═══ 10. 방향성 — 매물먼저 (20개) ═══
for (let i = 0; i < 20; i++) {
  const r = REGIONS[i];
  const price = JEONSE_PRICES[i % JEONSE_PRICES.length];
  scenarios.push({
    id: nextId(),
    axis: `방향-매물먼저-${r.gu}`,
    property: `${r.property} 전세 ${priceToKor(price)} 아파트 25평`,
    client: `${r.client} 전세 ${priceToKor(price)} 이하 아파트 찾아요`,
    expect: 'match',
    matchOn: 'property',
  });
}

// ═══ 11. 가격 경계 (정확히 일치) (10개) ═══
for (let i = 0; i < 10; i++) {
  const r = REGIONS[i];
  const price = JEONSE_PRICES[i % JEONSE_PRICES.length];
  scenarios.push({
    id: nextId(),
    axis: `가격-경계정확-${r.gu}`,
    property: `${r.property} 전세 ${priceToKor(price)} 아파트 22평`,
    client: `${r.client} 전세 ${priceToKor(price)} 이하 아파트 구합니다`,
    expect: 'match',
    matchOn: 'client',
  });
}

// ═══ 12. 가격 범위 (min~max) (5개) ═══
for (let i = 0; i < 5; i++) {
  const r = REGIONS[i];
  const pMin = JEONSE_PRICES[i];
  const pMax = JEONSE_PRICES[i + 2];
  const pMid = JEONSE_PRICES[i + 1];
  scenarios.push({
    id: nextId(),
    axis: `가격-범위내-${r.gu}`,
    property: `${r.property} 전세 ${priceToKor(pMid)} 아파트 22평`,
    client: `${r.client} 전세 ${priceToKor(pMin)} 이상 ${priceToKor(pMax)} 이하 아파트 구해요`,
    expect: 'match',
    matchOn: 'client',
  });
}

// ═══ 13. 면적 조건 (10개) ═══
for (let i = 0; i < 10; i++) {
  const r = REGIONS[i];
  const minP = 15 + i * 2;
  scenarios.push({
    id: nextId(),
    axis: `면적-${minP}평이상-${r.gu}`,
    property: `${r.property} 전세 3억 아파트 ${minP + 5}평`,
    client: `${r.client} 전세 3억 이하 ${minP}평 이상 아파트 구합니다`,
    expect: 'match',
    matchOn: 'client',
  });
}

console.log(JSON.stringify(scenarios, null, 2));
console.error(`\n생성: ${scenarios.length}개 시나리오`);
