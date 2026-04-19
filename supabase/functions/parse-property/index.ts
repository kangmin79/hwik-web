import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'
import { generateTags } from '../_shared/tags.ts'
import { fixTypos } from '../_shared/typo.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://hwik.kr',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// ========== ㎡ ↔ 평 변환 ==========
function sqmToPyeong(sqm: number): number {
  return Math.round(sqm / 3.305785 * 10) / 10;
}
function pyeongToSqm(pyeong: number): number {
  return Math.round(pyeong * 3.305785 * 10) / 10;
}

// 평/㎡ 중 한 쪽만 있으면 양쪽 병기한 문자열로 정규화
function extractAndConvertArea(areaStr: string): { original: string; normalized: string | null } {
  if (!areaStr) return { original: areaStr, normalized: null };
  const hasSqm = /(\d+\.?\d*)\s*㎡/.test(areaStr);
  const hasPyeong = /(\d+\.?\d*)\s*평/.test(areaStr);
  if (hasSqm && hasPyeong) return { original: areaStr, normalized: areaStr };
  if (hasSqm) {
    const sqm = parseFloat(areaStr.match(/(\d+\.?\d*)\s*㎡/)![1]);
    return { original: areaStr, normalized: `${sqmToPyeong(sqm)}평 (${sqm}㎡)` };
  }
  if (hasPyeong) {
    const py = parseFloat(areaStr.match(/(\d+\.?\d*)\s*평/)![1]);
    return { original: areaStr, normalized: `${py}평 (${pyeongToSqm(py)}㎡)` };
  }
  return { original: areaStr, normalized: null };
}

// ========== 임베딩 ==========
async function generateEmbedding(text: string): Promise<number[] | null> {
  const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY');
  if (!OPENAI_API_KEY) return null;
  try {
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${OPENAI_API_KEY}` },
      body: JSON.stringify({ input: text, model: 'text-embedding-3-small' })
    });
    const data = await response.json();
    return data.data?.[0]?.embedding || null;
  } catch (error) { return null; }
}

// ========== 실거래가 조회 (국토부 RTMS API) ==========
async function fetchRecentSales(complex: string, lawdCd: string, months = 12): Promise<any[]> {
  const GOV_SERVICE_KEY = Deno.env.get('GOV_SERVICE_KEY');
  if (!GOV_SERVICE_KEY || !complex || !lawdCd) return [];

  const SALES_API = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev';
  const allData: any[] = [];
  const now = new Date();
  const keywords = [complex.replace(/\s/g, '').slice(0, 4)];
  if (complex.replace(/\s/g, '').length > 4) {
    keywords.push(complex.replace(/\s/g, '').slice(2, 6));
  }

  for (let i = 0; i < months; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const ym = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
    try {
      const url = `${SALES_API}?serviceKey=${encodeURIComponent(GOV_SERVICE_KEY)}&LAWD_CD=${lawdCd}&DEAL_YMD=${ym}&pageNo=1&numOfRows=9999`;
      const resp = await fetch(url, { headers: { 'Accept': 'application/xml' } });
      if (!resp.ok) continue;
      const text = await resp.text();
      const items = text.match(/<item>([\s\S]*?)<\/item>/g) || [];
      for (const item of items) {
        const get = (tag: string) => item.match(new RegExp(`<${tag}>(.*?)<\/${tag}>`))?.[1]?.trim() || '';
        const aptNm = get('aptNm').replace(/\s/g, '');
        if (keywords.some(kw => aptNm.includes(kw))) {
          allData.push({
            year: get('dealYear'),
            month: get('dealMonth'),
            day: get('dealDay'),
            amount: get('dealAmount'),
            area: get('excluUseAr'),
            floor: get('floor'),
            aptNm: get('aptNm'),
          });
        }
      }
    } catch (e) { continue; }
  }
  return allData;
}

// ========== lawdCd 추출 (bjdCode 앞 5자리) ==========
const KAKAO_API_KEY = Deno.env.get('KAKAO_API_KEY') || '';

async function getLawdCd(address: string): Promise<string | null> {
  if (!address) return null;
  try {
    const url = `https://dapi.kakao.com/v2/local/search/address.json?query=${encodeURIComponent(address)}`;
    const res = await fetch(url, { headers: { 'Authorization': `KakaoAK ${KAKAO_API_KEY}` } });
    const data = await res.json();
    const bCode = data.documents?.[0]?.address?.b_code || '';
    return bCode.slice(0, 5) || null;
  } catch (e) { return null; }
}

// ========== agent_comment 생성 (실거래가 기반) ==========
async function generateAgentComment(parsedResult: any, salesData: any[], anthropicKey: string): Promise<string | null> {
  if (parsedResult.type === '손님') return null;

  let salesContext = '';
  if (salesData.length > 0) {
    const recent = salesData.slice(0, 5).map(s =>
      `${s.year}.${s.month}.${s.day} | ${s.area}㎡(${sqmToPyeong(parseFloat(s.area))}평) | ${s.amount}만원 | ${s.floor}층`
    ).join('\n');
    salesContext = `\n\n최근 실거래가:\n${recent}`;
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': anthropicKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 150,
        messages: [{
          role: 'user',
          content: `부동산 중개사가 손님에게 보내는 매물 소개 한 줄 코멘트를 작성해주세요.
이모지 1개로 시작하고, 30자 이내로 간결하게.
실거래가 데이터가 있으면 시세 대비 언급해주세요.
코멘트만 반환하세요.

매물: ${parsedResult.type} ${parsedResult.price} ${parsedResult.location} ${parsedResult.complex || ''} ${parsedResult.area || ''}${salesContext}`
        }]
      })
    });
    const data = await response.json();
    return data.content?.[0]?.text?.trim() || null;
  } catch (e) { return null; }
}

// ========== AI 크롤링용 public_data 생성 ==========
function createPublicData(parsedResult: any, salesData: any[]): object {
  const avgPrice = salesData.length > 0
    ? Math.round(salesData.reduce((sum, s) => {
        const amt = parseInt(s.amount.replace(/,/g, '')) || 0;
        return sum + amt;
      }, 0) / salesData.length)
    : null;

  return {
    schema_version: '1.0',
    property_type: parsedResult.category,
    trade_type: parsedResult.type,
    location: parsedResult.location,
    complex_name: parsedResult.complex,
    price: parsedResult.price,
    area: parsedResult.area,
    floor: parsedResult.floor,
    features: parsedResult.features || [],
    move_in: parsedResult.moveIn,
    recent_avg_price: avgPrice ? `${avgPrice.toLocaleString()}만원` : null,
    recent_trade_count: salesData.length,
    data_source: 'hwik',
    updated_at: new Date().toISOString(),
  };
}

// ========== 민감 키워드 ==========
const SENSITIVE_KEYWORDS = [
  '집주인', '세입자', '오너', '건물주', '관리실', '소유자', '임대인', '매도인', '임차인', '관리인', '현세입자', '전세입자',
  '관리사무소', '관리소', '관리팀', '융자', '근저당', '가압류', '대출', '대출승계', '담보', '실투자금', '선순위', '후순위',
  '호가', '시세', 'KB시세', '감정가', '공시가', '공시지가', '실거래가', '매매가', '전세가',
  '월수익', '순수익', '순이익', '월순익', '연수익', '예상수익', '임대수익',
  '이혼', '이혼정리', '상속', '상속정리', '이민', '급매', '급전세', '급월세', '급처분', '투자금회수',
  '계약일', '계약만료', '잔금', '잔금일', '만기', '만기일',
  '하자', '곰팡이', '누수', '누수이력', '벌레', '바퀴', '층간소음', '침수', '침수이력',
  '여성전용', '남성전용', '외국인불가', '네고', '협의가능', '가격협의', '권리금', '수익률',
  '월매출', '공실', '연체', '실입주만',
];

function createSearchTextPublic(parsed: any, rawText: string): string {
  let sanitized = rawText;
  sanitized = sanitized.replace(/(010|011|02|0[3-6][1-9])[-.\s]?\d{3,4}[-.\s]?\d{4}/g, '');
  sanitized = sanitized.replace(/\d{2,4}호/g, '');
  for (const kw of SENSITIVE_KEYWORDS) {
    sanitized = sanitized.replace(new RegExp(kw + '[\\d억천만원%개월있음없음중가능불가]*', 'gi'), '');
  }
  const catKoMap: Record<string, string> = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'};
  const catKo = catKoMap[parsed.category] || '';
  const parts = [
    parsed.type, parsed.price, parsed.location, parsed.complex,
    parsed.area, parsed.floor, parsed.room,
    ...(parsed.features || []), parsed.moveIn, parsed.category, catKo,
    sanitized.replace(/\s+/g, ' ').trim()
  ].filter(Boolean);
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

function createSearchTextPrivate(parsed: any, rawText: string): string {
  const catKoMap: Record<string, string> = {apartment:'아파트',officetel:'오피스텔',room:'원투룸',commercial:'상가',office:'사무실'};
  const catKo = catKoMap[parsed.category] || '';
  const parts = [
    parsed.type, parsed.price, parsed.location, parsed.complex,
    parsed.area, parsed.floor, parsed.room,
    ...(parsed.features || []), parsed.moveIn, parsed.memo, parsed.category, catKo, rawText
  ].filter(Boolean);
  return parts.join(' ');
}

// ========== 입주시기 텍스트 → YYYY-MM 정규화 ==========
function parseMoveInDate(moveIn: string | null | undefined): string | null {
  if (!moveIn) return null;
  const text = moveIn.trim();
  const now = new Date();
  const thisYear = now.getFullYear();
  const thisMonth = now.getMonth() + 1;

  // "즉시입주", "즉시", "공실", "바로", "급구"
  if (/즉시|공실|바로|급구|당장|비어있/.test(text)) {
    return `${thisYear}-${String(thisMonth).padStart(2, '0')}`;
  }
  // "협의", "미정"
  if (/협의|미정|상의|조율/.test(text)) return null;

  // "2026년 5월", "2026.05", "2026-05"
  const fullDate = text.match(/(20\d{2})\s*[년.\-/]\s*(\d{1,2})/);
  if (fullDate) {
    return `${fullDate[1]}-${String(parseInt(fullDate[2])).padStart(2, '0')}`;
  }
  // "내년 2월", "내년 초"
  if (/내년/.test(text)) {
    const monthMatch = text.match(/(\d{1,2})\s*월/);
    if (monthMatch) return `${thisYear + 1}-${String(parseInt(monthMatch[1])).padStart(2, '0')}`;
    if (/초/.test(text)) return `${thisYear + 1}-02`;
    if (/말/.test(text)) return `${thisYear + 1}-12`;
    return `${thisYear + 1}-06`; // 내년 (시기 불명확)
  }
  // "이번달", "이달"
  if (/이번\s*달|이달|금월/.test(text)) {
    return `${thisYear}-${String(thisMonth).padStart(2, '0')}`;
  }
  // "다음달", "내달"
  if (/다음\s*달|내달|차월/.test(text)) {
    const next = thisMonth === 12 ? 1 : thisMonth + 1;
    const nextYear = thisMonth === 12 ? thisYear + 1 : thisYear;
    return `${nextYear}-${String(next).padStart(2, '0')}`;
  }
  // "5월", "8월" (올해)
  const monthOnly = text.match(/(\d{1,2})\s*월/);
  if (monthOnly) {
    const m = parseInt(monthOnly[1]);
    const year = m < thisMonth ? thisYear + 1 : thisYear; // 지난 달이면 내년
    return `${year}-${String(m).padStart(2, '0')}`;
  }

  return null;
}

// 단일 가격 문자열 → 만원 단위 숫자
function parseSinglePrice(str: string, isMonthly = false): number | null {
  if (!str) return null;
  try {
    let s = str.replace(/[\s,원보증금월세]/g, '');
    // "3억5000" → 35000
    if (s.includes('억')) {
      const parts = s.split('억');
      return (parseInt(parts[0]) || 0) * 10000 + (parseInt(parts[1]) || 0);
    }
    // "4천904" → 4904, "1천88" → 1088
    if (s.includes('천')) {
      const parts = s.split('천');
      return (parseInt(parts[0]) || 0) * 1000 + (parseInt(parts[1]) || 0);
    }
    if (s.includes('만')) return parseInt(s.replace('만', '')) || null;
    const num = parseInt(s);
    // 월세 금액은 만원 그대로 (50 = 50만원), 매매/전세/보증금은 100 이하면 억 단위로 추정
    if (!isNaN(num)) return (!isMonthly && num <= 100) ? num * 10000 : num;
  } catch (_e) {}
  return null;
}

// 가격 문자열에서 price_number (대표가격), deposit, monthly_rent 추출
function parsePriceFields(priceStr: string, type: string): { price_number: number | null, deposit: number | null, monthly_rent: number | null } {
  if (!priceStr) return { price_number: null, deposit: null, monthly_rent: null };
  const clean = priceStr.replace(/[\s,]/g, '');

  // 슬래시 패턴: "1000/50", "보1065/월90" (월세, 반전세, 전세+관리비 등)
  if (clean.includes('/')) {
    const parts = clean.split('/');
    const deposit = parseSinglePrice(parts[0]);
    const monthly = parseSinglePrice(parts[1], true);  // 월세는 만원 그대로
    return { price_number: deposit, deposit, monthly_rent: monthly };
  }

  // 매매/전세: 단일 가격
  const price_number = parseSinglePrice(clean);
  return { price_number, deposit: null, monthly_rent: null };
}

// 하위 호환용
function parsePriceNumber(priceStr: string): number | null {
  if (!priceStr) return null;
  const clean = priceStr.replace(/[\s,]/g, '');
  if (clean.includes('/')) return parseSinglePrice(clean.split('/')[0]);
  return parseSinglePrice(clean);
}

function normalizeType(type: string): string {
  const typeMap: Record<string, string> = {
    '반전세': '월세', '보증금 월세': '월세', '보증금월세': '월세', '월세': '월세',
    '전세': '전세', '매매': '매매', '매도': '매매', '분양': '매매', '임대': '월세', '손님': '손님'
  };
  return typeMap[type] || type;
}

function normalizeText(text?: string): string | null {
  return text?.replace(/\s+/g, ' ').trim() || null;
}

// ========== 메인 ==========
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  const authHeader = req.headers.get('Authorization');
  if (!authHeader) {
    return new Response(JSON.stringify({ error: '로그인이 필요합니다.' }), {
      status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }

  const token = authHeader.replace('Bearer ', '');
  const SERVICE_ROLE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  // 내부 서비스 간 호출(telegram-webhook 등) — 전용 시크릿 헤더로 bypass
  const internalSecret = Deno.env.get('HWIK_INTERNAL_SECRET') || '';
  const internalHeader = req.headers.get('x-hwik-internal') || '';
  const isInternalCall = internalSecret.length > 0 && internalHeader === internalSecret;
  if (!isInternalCall) {
    // ★ supabase-js getUser()가 ES256 JWT 검증 실패하는 문제 우회 → Auth API 직접 호출
    try {
      const authRes = await fetch(`${Deno.env.get('SUPABASE_URL')!}/auth/v1/user`, {
        headers: { 'Authorization': `Bearer ${token}`, 'apikey': SERVICE_ROLE },
      });
      if (!authRes.ok) {
        return new Response(JSON.stringify({ error: '로그인이 필요합니다.' }), {
          status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    } catch (_) {
      return new Response(JSON.stringify({ error: '로그인이 필요합니다.' }), {
        status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
  }

  try {
    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    if (!ANTHROPIC_API_KEY) throw new Error('서버 설정 오류입니다.');

    let { text } = await req.json();
    // ★ 오타/띄어쓰기 교정 (AI 전달 전)
    text = fixTypos(text || '');
    if (!text || text.trim().length < 10)
      return new Response(JSON.stringify({ error: '매물 정보가 너무 짧습니다. 최소 10자 이상 입력해주세요.' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    if (text.length > 3000)
      return new Response(JSON.stringify({ error: '입력 텍스트가 너무 깁니다 (최대 3000자)' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });

    console.log('INPUT:', text);
    const startTime = Date.now();

    // ★ Claude 파싱 (좌표 조회 제거 → 클라이언트에서 처리)
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1024,
        messages: [{
          role: 'user',
          content: `당신은 부동산 매물 정보를 분석하는 전문가입니다.
아래 매물 정보를 분석해서 JSON으로 반환해주세요.

■ 중요: 반드시 JSON만 반환하고, 다른 설명은 하지 마세요.

■ type 판단 기준 (최우선):
먼저 이 입력이 "매물 등록"인지 "손님 요청"인지 판단하세요.
기본값은 "매물 등록"입니다. 확실한 손님 요청 근거가 없으면 매물로 처리하세요.

★ 매물 등록의 특징:
- 구체적 가격: "15억", "3억5000", "1000/80"
- 구체적 층/동: "15층", "101동"
- 구체적 단지명+면적: "래미안 32평"
- "내놓습니다", "올립니다", "팝니다", "구해드립니다"
- 초성/축약: ㅁㅁ=매매, ㅈㅅ=전세, ㅇㅅ=월세

★ 손님 요청의 특징:
- 구합니다, 구해요, 찾습니다, 원합니다, 원해요 등 요청 동사
- "사려고", "사길", "매입", "구매" → 손님 (매매)
- "빌려요", "빌리고", "임차", "렌트" → 손님 (월세)
- 예산 ~, 손님 요청, 이사 예정, 급구
- 예산/희망가 표현: 예산 5억, ~이하, ~이내, ~까지
- "이하", "이내", "미만", "넘지 않게", "선에서", "대" 등 상한 표현 → 손님
- "무보증 월세", "보증금 없이" → 손님 (보증금 0)
- "N호선 라인", "역 근처", "인근", "쪽" → 지역 조건
- "빼고", "싫어요", "안돼요", "제외" → 제외 조건 (features에 "제외:반지하" 형태로)
- "전세나 월세", "둘 다 괜찮" → 복수 거래유형

⚠️ 오분류 방지:
1. "구해드립니다" = 매물 등록 (중개사가 매물을 올리는 것)
2. "사려고 합니다" = 손님 (매수 희망)
3. 확신 없으면 매물로 처리
4. 호수(~호)는 절대 비공개 → memo에만

■ ㎡ ↔ 평 자동변환:
- area 필드에 ㎡만 있으면 평수 병기 (예: "84.8㎡" → "25.7평 (84.8㎡)")
- area 필드에 평만 있어도 ㎡ 병기 (예: "32평" → "32평 (105.8㎡)")
- 두 표기 모두 나오게 정규화

■ 상가/사무실 추가 필드 (category가 commercial/office일 때만):
- management_fee: 월 관리비 (숫자만, 만원 단위). "관리비 30만원" → 30. 없으면 null.
- rights_money: 권리금 (숫자만, 만원 단위). "권리금 3000만원" → 3000, "권리금 3000" → 3000. 없으면 null.
- 아파트/오피스텔/원투룸은 이 두 필드 모두 null.

■ category:
- apartment: 아파트, 주상복합
- officetel: 오피스텔, 도시형생활주택
- room: 원룸, 투룸, 빌라, 다세대, 주택
- commercial: 상가, 점포, 식당
- office: 사무실, 지식산업센터

■ features 화이트리스트 (★ 반드시 이 목록에서만 추출):
[시설] 올수리, 풀옵션, 신축, 리모델링, 시스템에어컨, 드레스룸, 베란다확장, 빌트인, 부분수리
[방향] 남향, 동향, 서향, 북향, 남동향, 남서향, 정남향
[위치] 역세권, 초역세권, 더블역세권, 학군좋음, 학원가, 대로변, 초품아, GTX역세권
[주차] 주차가능, 주차1대, 주차2대, 주차무료
[뷰/구조] 한강뷰, 공원뷰, 산뷰, 시티뷰, 탁트인전망, 복층, 테라스, 루프탑, 고층, 저층, 로얄층, 분리형
[편의] 애견가능, 엘리베이터, 경비실, 보안, 무인택배, 관리비포함
[입주] 즉시입주, 입주협의, 공실
[금융] HUG가능, 무융자, 대출가능
[생활] 슬세권, 런세권, 숲세권, 채광좋음, 조용한동네, 통풍좋음
[상가] 전면넓음, 코너자리, 유동인구많음, 권리금없음, 업종제한없음, 1층상가

★ 비정형 표현 → 표준 태그 변환 (중요!):
- "살기 좋은", "살기좋은" → 조용한동네
- "아이 키우기 좋은", "교육환경 좋은" → 학군좋음, 초품아
- "깔끔한", "깨끗한", "상태 좋은" → 올수리 또는 신축
- "밝은", "환한", "햇빛 잘 드는" → 채광좋음, 남향
- "지하철 가까운", "역 가까운", "교통 편한" → 역세권
- "공원 가까운", "산책할 수 있는" → 런세권 또는 공원뷰
- "주차 편한", "차 대기 쉬운" → 주차가능
- "편의점 가까운", "상권 좋은" → 슬세권
- "조용한", "한적한", "시끄럽지 않은" → 조용한동네
- "넓은", "통 큰" → area 필드에 반영
- "안전한", "보안 좋은" → 보안
- "강아지 키울 수 있는", "동물 가능" → 애견가능
- "커피숍 근처", "스타벅스 근처" → 슬세권
- "마트 가까운", "쇼핑 편한" → 슬세권
- "병원 가까운", "의료시설" → features에 추가 안 함 (일반적)
- "전세금 안전한", "보증보험 되는" → HUG가능
- "융자 없는", "깨끗한 등기" → 무융자

★ 부정어 처리 (매우 중요!):
- "반지하 아님", "반지하 아닙니다", "반지하X" → 반지하를 features에 넣지 마세요. 오히려 좋은 의미입니다.
- "융자 없음", "융자 없는", "무융자" → features에 "무융자" 추가. "융자"를 넣지 마세요.
- "하자 없음", "누수 없음", "곰팡이 없음" → features에 넣지 마세요. memo에 "하자없음 확인" 정도로 기록.
- "층간소음 없음", "소음 없음" → features에 "조용한동네" 추가.
- "주차 안됨", "주차 불가" → features에 "주차가능"을 넣지 마세요.
- "엘리베이터 없음" → features에 "엘리베이터"를 넣지 마세요.
- 핵심 원칙: "~없음/아님/안됨/불가/X" 앞의 단어는 반대 의미이므로, 해당 키워드를 features에 넣으면 안 됩니다.

★ 태그 정규화 (동의어 → 표준 태그):
- "전체수리", "올리모델링", "새로수리", "깔끔하게수리" → "올수리"
- "가전풀", "가구포함", "옵션풀" → "풀옵션"
- "즉입", "바로입주", "입주가능" → "즉시입주"
- "역앞", "역근처", "역도보" → "역세권"
- "학교근처", "학교앞", "교육환경" → "학군좋음"
- "주차됨", "주차OK", "차댈곳있음" → "주차가능"
- "반려견OK", "강아지OK", "동물가능" → "애견가능"
- "전세보증", "보증보험OK" → "HUG가능"
- 반드시 화이트리스트의 표준 태그명으로만 반환하세요.

■ memo (나만 보기 — 절대 공개 금지): 호수, 연락처, 사람이름, 사람정보, 이혼/상속/이민 사유, 하자/누수/곰팡이/층간소음 결함정보
■ shared_memo (중개사끼리 공유 OK — 손님에게는 비공개): 네고가능, 급매, 융자정보, 호가, 시세, 실투자금, 권리금, 수익률, 계약조건, 잔금일정, 입주협의 상세
■ agent_comment:
- 💬 이모지로 시작하는 줄이 있으면 추출
- 없으면 null (실거래가 기반으로 서버에서 생성)
- type이 "손님"이면 null

{
  "type": "매매/전세/월세/손님 중 하나",
  "price": "가격만 (네고/협의 등 제외)",
  "location": "지역 (구+동, 예: 마포구 합정동)",
  "address_road": "도로명주소 (있으면 추출, '○○로/길/대로 + 번지' 형태. 예: 서울 송파구 올림픽로 300. 없으면 null)",
  "address_jibun": "지번주소 (있으면 추출, '○○동 + 번지' 형태. 예: 서울 송파구 가락동 913. 번지 없이 동만 있으면 null)",
  "complex": "단지명 (없으면 null). ★ 주의: 동번호/호수 반드시 제외. 예: '한양에드가3차301동'→'한양에드가3차', '광교2차 푸르지오시티 C동'→'광교2차 푸르지오시티'. 괄호 포함 이름은 그대로 보존. 예: '느티마을(3단지)(공무원)'. 한글을 숫자로 변환 금지 (예: '백운'을 '100'으로 바꾸지 마세요). '도시형생활주택','다세대주택','연립주택','빌라','상가건물' 같은 건물 유형 단어만 있으면 null.",
  "area": "면적 (㎡있으면 평수 병기)",
  "floor": "동+층만 (호수 제외 — 호수는 memo로)",
  "room": "방 구조",
  "features": ["화이트리스트 특징만"],
  "moveIn": "입주일",
  "contact_name": "사람 이름 (있으면 추출. 없으면 null)",
  "contact_phone": "전화번호 (010-XXXX-XXXX 형태. 없으면 null)",
  "memo": "나만 보는 정보 (호수, 사람정보, 하자, 개인사유 등. 없으면 null)",
  "shared_memo": "중개사 공유 정보 (네고, 융자, 급매, 거래조건, 시세 등. 없으면 null)",
  "agent_comment": "중개사 코멘트 (없으면 null)",
  "category": "apartment/officetel/room/commercial/office",
  "management_fee": "월 관리비 (숫자, 만원 단위. commercial/office만. 없으면 null)",
  "rights_money": "권리금 (숫자, 만원 단위. commercial만. 없으면 null)"
}

매물 정보:
${text}`
        }]
      })
    });

    const claudeData = await response.json();
    if (claudeData.error) throw new Error(claudeData.error.message);

    let parsedResult: any;
    try {
      let jsonText = claudeData.content?.[0]?.text || '';
      jsonText = jsonText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const firstBrace = jsonText.indexOf('{');
      const lastBrace = jsonText.lastIndexOf('}');
      if (firstBrace !== -1 && lastBrace !== -1) jsonText = jsonText.slice(firstBrace, lastBrace + 1);
      parsedResult = JSON.parse(jsonText);
    } catch (e) {
      throw new Error('파싱 결과를 처리할 수 없습니다');
    }

    parsedResult.features = [...new Set(parsedResult.features || [])];
    parsedResult.type = normalizeType(parsedResult.type);
    parsedResult.location = normalizeText(parsedResult.location);
    parsedResult.complex = normalizeText(parsedResult.complex);
    // ★ complex 후처리: 동 번호 제거 + 건물 유형만 남으면 null
    if (parsedResult.complex) {
      parsedResult.complex = parsedResult.complex
        .replace(/\s*\d+\s*동\s*$/g, '')           // "101동" 제거
        .replace(/\s+\d+\s*동\s+/g, ' ')           // 중간 "101동" 제거
        .replace(/\s+[A-Za-z]\s*동\s*$/g, '')     // "C동" 제거
        .replace(/\s*\d+\s*호$/g, '')             // "501호" 제거
        .trim();
      // 건물 유형 단어만 있으면 null
      if (/^(도시형생활주택|다세대주택|연립주택|빌라|상가건물|오피스텔|주상복합)$/.test(parsedResult.complex)) {
        parsedResult.complex = null;
      }
    }
    if (parsedResult.floor) {
      parsedResult.floor = parsedResult.floor.replace(/\s+/g, ' ').replace(/\d+호/g, '').trim();
    }

    // 평 / ㎡ 중 한 쪽만 있으면 양쪽 병기 (모든 타입 일관화)
    if (parsedResult.area) {
      const converted = extractAndConvertArea(parsedResult.area);
      if (converted.normalized) parsedResult.area = converted.normalized;
    }

    const requiredFields = parsedResult.type === '손님'
      ? ['type', 'location', 'category']
      : ['type', 'price', 'location', 'category'];
    for (const field of requiredFields) {
      if (!parsedResult[field]) throw new Error(`필수 정보 누락: ${field}`);
    }
    // ★ category 유효성 검증 — 한글 반환 시 영문 코드로 변환
    const VALID_CATEGORIES = ['apartment', 'officetel', 'room', 'commercial', 'office'];
    const CATEGORY_FIX: Record<string, string> = {'아파트':'apartment','오피스텔':'officetel','원투룸':'room','빌라':'room','다세대':'room','주택':'room','상가':'commercial','점포':'commercial','사무실':'office'};
    if (parsedResult.category && !VALID_CATEGORIES.includes(parsedResult.category)) {
      parsedResult.category = CATEGORY_FIX[parsedResult.category] || 'room';
    }

    // ★ 관리비/권리금 — 해당 없는 카테고리는 강제 null (오분류 방지)
    const _mf = parsedResult.management_fee;
    parsedResult.management_fee = (parsedResult.category === 'commercial' || parsedResult.category === 'office') && _mf != null && !isNaN(Number(_mf)) ? Number(_mf) : null;
    const _rm = parsedResult.rights_money;
    parsedResult.rights_money = parsedResult.category === 'commercial' && _rm != null && !isNaN(Number(_rm)) ? Number(_rm) : null;

    console.log(`PARSED (${Date.now() - startTime}ms):`, parsedResult);

    const searchText = createSearchTextPublic(parsedResult, text);
    const searchTextPrivate = createSearchTextPrivate(parsedResult, text);
    const embeddingText = parsedResult.type === '손님' ? searchTextPrivate : searchText;

    // ★ 임베딩만 (lawdCd는 실거래가 이관과 함께 제거)
    const embedding = await generateEmbedding(embeddingText);
    const lawdCd: string | null = null;

    console.log(`임베딩 (${Date.now() - startTime}ms)`);

    // ★ 성능 최적화: 실거래가/agent_comment/public_data는 백그라운드로 이관
    //    (fetchRecentSales/generateAgentComment/AI 태그 진화 모두 제거 — 매물 등록 응답속도 우선)
    const salesData: any[] = [];
    const publicData = null;

    const moveInDate = parseMoveInDate(parsedResult.moveIn);

    // ★ 손님일 때 거래유형 복수 추출 + 각 유형별 가격 조건
    let wantedTradeType: string | null = null;
    let wantedConditions: any[] = [];
    if (parsedResult.type === '손님') {
      const allText = [parsedResult.price, parsedResult.location, parsedResult.memo, text].join(' ');
      const wantedTypes: string[] = [];
      if (/매매|매도|분양|사려|매입|구매/.test(allText)) wantedTypes.push('매매');
      if (/전세/.test(allText)) wantedTypes.push('전세');
      if (/월세|임대|빌려|렌트/.test(allText)) wantedTypes.push('월세');
      // 가격 패턴으로 추론
      if (!wantedTypes.length) {
        if (/\/\s*\d|월\s*\d|보증금.*월/.test(allText)) wantedTypes.push('월세');
        else if (/억|천만/.test(allText)) wantedTypes.push('전세');
      }
      wantedTradeType = wantedTypes[0] || null;

      // 각 유형별 가격 조건 추출
      // 헬퍼: 한글 가격 파싱
      function _pk(s: string): number {
        let t = 0;
        const ek = s.match(/(\d+\.?\d*)\s*억/);
        const ch = s.match(/(\d+)\s*천/);
        if (ek) t += parseFloat(ek[1]) * 10000;
        if (ch) t += parseInt(ch[1]) * 1000;
        if (t > 0) return t;
        const n = parseInt(s.replace(/[^\d]/g, ''));
        return isNaN(n) ? 0 : n;
      }

      for (const tt of wantedTypes) {
        const cond: any = { trade_type: tt };
        if (tt === '월세') {
          // "보증금 1000/월 50" 또는 "1000/50"
          const slash = allText.match(/(\d+)\s*\/\s*(\d+)/);
          if (slash) { cond.deposit = parseInt(slash[1]); cond.monthly = parseInt(slash[2]); }
          const depM = allText.match(/보증금\s*(\d+)/);
          if (depM && !cond.deposit) cond.deposit = parseInt(depM[1]);
          const monM = allText.match(/월(?:세)?\s*(\d+)/);
          if (monM && !cond.monthly) cond.monthly = parseInt(monM[1]);
        } else {
          // 매매/전세: "3억", "3억5천", "3억 3억5천까지 가능"
          const range = allText.match(/(\d+\.?\d*억(?:\s*\d+천)?)\s*[~에서]\s*(\d+\.?\d*억(?:\s*\d+천)?)/);
          if (range) { cond.min_price = _pk(range[1]); cond.max_price = _pk(range[2]); }
          const dual = allText.match(/(\d+\.?\d*억(?:\s*\d+천)?)\s+(\d+\.?\d*억(?:\s*\d+천)?)\s*(?:까지|이하|이내|도|면)?\s*(?:가능|괜찮|OK)/i);
          if (dual && !cond.max_price) { cond.min_price = _pk(dual[1]); cond.max_price = _pk(dual[2]); }
          const maxM = allText.match(/(\d+\.?\d*)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지)/);
          if (maxM && !cond.max_price) cond.max_price = parseFloat(maxM[1]) * 10000 + (maxM[2] ? parseInt(maxM[2]) * 1000 : 0);
          if (!cond.min_price && !cond.max_price) {
            const bare = allText.match(/(\d+\.?\d*)\s*억/);
            if (bare) { const b = parseFloat(bare[1]) * 10000; cond.min_price = Math.round(b * 0.85); cond.max_price = Math.round(b * 1.15); }
          }
        }
        wantedConditions.push(cond);
      }
    }

    // ★ 손님일 때 원하는 카테고리 복수 추출
    let wantedCategories: string[] = [];
    if (parsedResult.type === '손님') {
      const allText = [parsedResult.location, parsedResult.complex, parsedResult.memo, text, ...(parsedResult.features || [])].filter(Boolean).join(' ');
      if (/아파트|주상복합/.test(allText)) wantedCategories.push('apartment');
      if (/오피스텔|옵텔/.test(allText)) wantedCategories.push('officetel');
      if (/원룸|투룸|쓰리룸|빌라|다세대|연립|주택/.test(allText)) wantedCategories.push('room');
      if (/상가|점포|매장|식당|카페|편의점|치킨|미용|베이커리/.test(allText)) wantedCategories.push('commercial');
      if (/사무실|오피스(?!텔)|업무|코워킹/.test(allText)) wantedCategories.push('office');
      // category 필드가 있으면 포함
      if (parsedResult.category && !wantedCategories.includes(parsedResult.category)) {
        wantedCategories.push(parsedResult.category);
      }
      // 빈 배열이면 category에서 단일값 사용
      if (!wantedCategories.length && parsedResult.category) wantedCategories = [parsedResult.category];
    }

    // ★ 가격 필드 파싱 (매물: type 기준, 손님: wantedTradeType 기준)
    const priceType = parsedResult.type === '손님' ? (wantedTradeType || '') : parsedResult.type;
    const priceFields = parsePriceFields(parsedResult.price, priceType);

    // 손님이고 월세인 경우: 텍스트에서 보증금/월세 추가 추출 (price 필드에 없을 수 있음)
    if (parsedResult.type === '손님' && wantedTradeType === '월세') {
      const allText = [parsedResult.price, parsedResult.memo, text].join(' ');
      if (!priceFields.deposit) {
        const depMatch = allText.match(/보증금\s*(\d+)/);
        if (depMatch) priceFields.deposit = parseInt(depMatch[1]);
      }
      if (!priceFields.monthly_rent) {
        const monMatch = allText.match(/월(?:세)?\s*(\d+)/);
        if (monMatch) priceFields.monthly_rent = parseInt(monMatch[1]);
      }
      // "1000/50" 패턴
      if (!priceFields.deposit && !priceFields.monthly_rent) {
        const slashMatch = allText.match(/(\d+)\s*\/\s*(\d+)/);
        if (slashMatch) {
          priceFields.deposit = parseInt(slashMatch[1]);
          priceFields.monthly_rent = parseInt(slashMatch[2]);
        }
      }
    }

    const result = {
      ...parsedResult,
      move_in_date: moveInDate,
      wanted_trade_type: wantedTradeType,
      wanted_categories: wantedCategories.length ? wantedCategories : null,
      wanted_conditions: wantedConditions.length ? wantedConditions : null,
      lat: null,
      lng: null,
      coord_type: 'none',
      embedding,
      search_text: searchText,
      search_text_private: searchTextPrivate,
      price_number: priceFields.price_number,
      deposit: priceFields.deposit,
      monthly_rent: priceFields.monthly_rent,
      lawd_cd: lawdCd,
      recent_sales: salesData.slice(0, 5),
      recent_sales_count: salesData.length,
      public_data: publicData,
    };

    // ★ 태그 자동 생성
    const tags = generateTags({
      property: parsedResult,
      price_number: priceFields.price_number,
      deposit: priceFields.deposit,
      monthly_rent: priceFields.monthly_rent,
      move_in_date: moveInDate,
      wanted_trade_type: wantedTradeType,
      wanted_categories: wantedCategories,
      wanted_conditions: wantedConditions,
    });
    console.log(`태그 생성(1차 키워드): ${tags.length}개 [${tags.join(', ')}]`);

    // ★ 로컬 검증: 공개 필드에 남은 민감 키워드를 memo/shared_memo로 이동
    const PRIVATE_KW = ['집주인','세입자','오너','건물주','소유자','임대인','매도인','임차인','관리인','현세입자','전세입자','관리사무소','관리소','이혼','이혼정리','상속','상속정리','이민','하자','곰팡이','누수','누수이력','벌레','바퀴','층간소음','침수','침수이력','여성전용','남성전용','외국인불가','실입주만'];
    const SHARED_KW = ['네고','협의가능','가격협의','융자','근저당','가압류','대출','대출승계','담보대출','신용대출','사업자대출','주담대','전세대출','담보','실투자금','선순위','후순위','호가','시세','KB시세','감정가','공시가','공시지가','월수익','순수익','순이익','월순익','연수익','예상수익','임대수익','급매','급전세','급월세','급처분','투자금회수','계약일','계약만료','잔금','잔금일','만기','만기일','권리금','수익률','월매출','공실','연체','자금조달','자금계획서','자금출처','취득세','양도세','종부세','증여세','상속세','LTV','중도상환'];
    const publicFields = ['price','location','complex','area','floor','room'];
    let extraMemo: string[] = [];
    let extraShared: string[] = [];
    for (const field of publicFields) {
      const val = (result as any)[field] || '';
      if (!val) continue;
      for (const kw of PRIVATE_KW) {
        if (val.includes(kw)) { extraMemo.push(`${kw}(${field}에서 이동)`); (result as any)[field] = val.replace(new RegExp(kw + '[^\\s]*', 'g'), '').trim(); }
      }
      for (const kw of SHARED_KW) {
        if (val.includes(kw)) { extraShared.push(`${kw}(${field}에서 이동)`); (result as any)[field] = val.replace(new RegExp(kw + '[^\\s]*', 'g'), '').trim(); }
      }
    }
    // features에서도 체크
    if (result.features?.length) {
      result.features = result.features.filter((f: string) => {
        if (PRIVATE_KW.some(kw => f.includes(kw))) { extraMemo.push(f); return false; }
        if (SHARED_KW.some(kw => f.includes(kw))) { extraShared.push(f); return false; }
        return true;
      });
    }
    if (extraMemo.length) {
      result.memo = [result.memo, ...extraMemo].filter(Boolean).join(', ');
      console.log(`민감정보→memo 이동: ${extraMemo.join(', ')}`);
    }
    if (extraShared.length) {
      result.shared_memo = [result.shared_memo, ...extraShared].filter(Boolean).join(', ');
      console.log(`거래조건→shared_memo 이동: ${extraShared.join(', ')}`);
    }

    // ★ 성능 최적화: AI 자가진화 태그(Haiku Claude 호출)는 batchGenerateTags로 이관
    //    1차 키워드 태그만 즉시 반환, AI 보강은 등록 후 백그라운드

    (result as any).tags = tags;

    console.log(`총 소요: ${Date.now() - startTime}ms`);
    console.log('OUTPUT:', { ...result, embedding: embedding ? `[${embedding.length}d]` : null });

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error: any) {
    console.error('ERROR:', error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
