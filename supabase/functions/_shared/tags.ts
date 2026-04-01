// ═══════════════════════════════════════════════════════════
// 휙 태그 시스템 — 표준 태그 사전 + 동의어 + generateTags
// ═══════════════════════════════════════════════════════════

// ── 동의어 → 표준 태그 변환 사전 ──
export const SYNONYM_MAP: Record<string, string> = {
  // 거래유형
  'ㅁㅁ':'매매','매도':'매매','분양':'매매','사려':'매매','매입':'매매','구매':'매매','직거래':'매매',
  'ㅈㅅ':'전세','젼세':'전세','임차':'전세','전세권설정':'전세',
  'ㅇㅅ':'월세','웜세':'월세','렌트':'월세','빌려':'월세','임대':'월세','달세':'월세',
  '준전세':'반전세','보증금높은월세':'반전세',
  // 매물유형
  'apt':'아파트','주상복합':'아파트','단지형':'아파트','대단지':'아파트',
  '옵텔':'오피스텔','officetel':'오피스텔',
  '다세대':'빌라','연립':'빌라','다가구':'빌라','신축빌라':'빌라',
  '1룸':'원룸','1.5룸':'원룸','스튜디오형':'원룸',
  '2룸':'투룸',
  '3룸':'쓰리룸',
  '단독주택':'주택','다가구주택':'주택','타운하우스':'주택',
  '점포':'상가','매장':'상가','식당':'상가','카페':'상가','편의점':'상가','치킨집':'상가','미용실':'상가','약국':'상가','베이커리':'상가',
  '오피스':'사무실','업무용':'사무실','코워킹':'사무실','지식산업센터':'사무실',
  '빌딩':'건물','꼬마빌딩':'건물',
  '물류':'공장창고','창고':'공장창고','공장':'공장창고',
  '대지':'토지','임야':'토지','전답':'토지',
  // 시설
  '올리':'올수리','전체수리':'올수리','새로수리':'올수리','올리모델링':'올수리',
  '일부수리':'부분수리','도배장판':'부분수리','욕실수리':'부분수리',
  '리모':'리모델링',
  '풀옵':'풀옵션','가전풀':'풀옵션','가구포함':'풀옵션',
  '즉입':'즉시입주',
  '관포':'관리비포함','관리비없음':'관리비포함','관없음':'관리비포함',
  '붙박이':'빌트인',
  '시에':'시스템에어컨','천장형에어컨':'시스템에어컨','천장에어컨':'시스템에어컨','중앙에어컨':'시스템에어컨',
  '베확':'베란다확장','발코니확장':'베란다확장',
  '전기레인지':'인덕션',
  '식세기':'식기세척기',
  // 구조
  '분리형원룸':'분리형',
  '옥상테라스':'루프탑','옥상':'루프탑',
  // 보안
  'CCTV':'보안','경비':'보안','24시간관리':'보안',
  '관리실':'경비실','관리인':'경비실',
  '디지털도어록':'현관보안','번호키':'현관보안',
  '택배함':'무인택배','택배보관':'무인택배',
  // 편의
  'EV':'엘리베이터','승강기':'엘리베이터',
  '주차1대':'주차가능','주차2대':'주차가능','주차무료':'주차가능','주차장':'주차가능',
  // 교통
  '역도보1분':'초역세권','역도보2분':'초역세권','역바로앞':'초역세권',
  '역도보':'역세권','역에서':'역세권','지하철근처':'역세권',
  '트리플역세권':'더블역세권','2개노선':'더블역세권',
  '버스정류장':'대중교통편리','교통편리':'대중교통편리',
  '큰길가':'대로변','간선도로':'대로변',
  // 교육
  '학교근처':'학군좋음','초등학교':'학군좋음','중학교':'학군좋음','명문학군':'학군좋음',
  '학원밀집':'학원가',
  '대학교근처':'학세권','대학가':'학세권',
  // 뷰
  '한강조망':'한강뷰','리버뷰':'한강뷰',
  '공원근처':'공원뷰','공원앞':'공원뷰','공원조망':'공원뷰',
  '산조망':'산뷰','산이보이는':'산뷰',
  '도심조망':'시티뷰','야경':'시티뷰',
  '탁트인':'탁트인전망','뷰좋음':'탁트인전망','전망좋음':'탁트인전망','오픈뷰':'탁트인전망','시야넓음':'탁트인전망',
  // 금융조건
  '허그':'HUG가능','안심전세':'HUG가능','보증보험':'HUG가능','허그가능':'HUG가능',
  '무융자':'무융자','융자없음':'무융자','등기깨끗':'무융자','선순위없음':'무융자',
  '전세대출':'대출가능','버팀목':'대출가능','신생아특례':'대출가능','디딤돌':'대출가능',
  '네고가능':'가격협의','가격조절':'가격협의','조절가능':'가격협의','급매':'가격협의',
  // 신조어
  '초품아':'초품아','초등학교품은':'초품아','단지내초교':'초품아','초세권':'초품아',
  '슬세권':'슬세권','상권좋은':'슬세권',
  '런세권':'런세권','천변길':'런세권','조깅':'런세권',
  '숲세권':'숲세권','숲근처':'숲세권',
  '맥세권':'맥세권','맥도날드':'맥세권',
  '스세권':'스세권','별세권':'스세권','스타벅스':'스세권',
  '몰세권':'몰세권','대형마트':'몰세권','쇼핑몰':'몰세권',
  '편세권':'편세권',
  '의세권':'의세권','대형병원':'의세권',
  'GTX':'GTX역세권','A노선':'GTX역세권','B노선':'GTX역세권','C노선':'GTX역세권',
  '자주식주차':'주차가능','주차1대이상':'주차가능',
  // 환경
  '한적':'조용한동네','주택가':'조용한동네',
  '환한':'채광좋음','밝은':'채광좋음','일조량':'채광좋음',
  '마트':'편의시설근처','편의점근처':'편의시설근처','상가근처':'편의시설근처',
  '의원':'병원근처','약국근처':'병원근처',
  '반려동물':'애견가능','펫':'애견가능','강아지':'애견가능','고양이':'애견가능',
  '바로입주':'즉시입주','입주가능':'즉시입주',
  '협의가능':'입주협의',
  // 상가
  '전면':'전면넓음','전면광고':'전면넓음',
  '코너상가':'코너자리','모퉁이':'코너자리',
  '유동많음':'유동인구많음','사람많은':'유동인구많음',
  '대형간판':'간판가능','간판':'간판가능',
  '무권리':'권리금없음','권리금0':'권리금없음',
  '업종자유':'업종제한없음','모든업종':'업종제한없음',
  // 상태
  '새건물':'신축',
  '상태좋음':'깨끗한',
  '청결':'깨끗한',
  '정남향':'남향',
};

// ── 아파트 브랜드 → "아파트" 태그 ──
export const APT_BRANDS = [
  '래미안','자이','힐스테이트','푸르지오','아크로','더샵','롯데캐슬','e편한세상',
  '아이파크','트리마제','파크리오','헬리오시티','한신','현대','SK뷰','우방','삼성',
  '대림','두산위브','반도유보라','중흥S클래스','호반써밋','계룡리슈빌','금호어울림',
  '동부','동아','벽산','부영','삼부','삼환','성원','쌍용','한화포레나','포스코더샵',
  '디에이치','시그니엘','르엘','센트레빌','미래도','목동','은마','압구정','잠실',
  '갈현','도곡','개포'
];

// ── 가중치 ──
export const TAG_WEIGHTS: Record<string, number> = {
  // 필수 (불일치 시 제외)
  _region: 30,
  _trade: 30,
  _type: 20,
  _price: 25,  // 숫자 비교
  _area: 15,   // 숫자 비교
  _movein: 15,
  // 선호
  _room: 10,
  _floor: 5,
  _direction: 5,
  // 보너스 (시설/환경 — 각 태그당)
  _facility: 10,
  _environment: 10,
  // 상가 전용
  _commercial: 15,
};

// ── 가격 구간 (검색/UI용, 매칭은 숫자 직접비교) ──
export function priceBracket(priceNumber: number, tradeType: string): string[] {
  const tags: string[] = [];
  if (tradeType === '월세' || !priceNumber || priceNumber <= 0 || isNaN(priceNumber)) return tags;
  if (priceNumber <= 5000) tags.push('5천이하');
  else if (priceNumber <= 10000) tags.push('5천~1억');
  else if (priceNumber <= 20000) tags.push('1~2억');
  else if (priceNumber <= 30000) tags.push('2~3억');
  else if (priceNumber <= 50000) tags.push('3~5억');
  else if (priceNumber <= 70000) tags.push('5~7억');
  else if (priceNumber <= 100000) tags.push('7~10억');
  else if (priceNumber <= 150000) tags.push('10~15억');
  else if (priceNumber <= 200000) tags.push('15~20억');
  else tags.push('20억이상');
  return tags;
}

export function depositBracket(deposit: number): string {
  if (!deposit || deposit <= 0 || isNaN(deposit)) return '';
  if (deposit <= 500) return '보증금500이하';
  if (deposit <= 1000) return '보증금500~1천';
  if (deposit <= 2000) return '보증금1~2천';
  if (deposit <= 3000) return '보증금2~3천';
  if (deposit <= 5000) return '보증금3~5천';
  if (deposit <= 10000) return '보증금5천~1억';
  return '보증금1억이상';
}

export function monthlyBracket(monthly: number): string {
  if (!monthly || monthly <= 0 || isNaN(monthly)) return '';
  if (monthly <= 30) return '월세30이하';
  if (monthly <= 50) return '월세30~50';
  if (monthly <= 80) return '월세50~80';
  if (monthly <= 100) return '월세80~100';
  if (monthly <= 150) return '월세100~150';
  if (monthly <= 200) return '월세150~200';
  return '월세200이상';
}

// ── 면적 구간 ──
export function areaBracket(pyeong: number): string {
  if (!pyeong || pyeong <= 0 || isNaN(pyeong)) return '';
  if (pyeong <= 5) return '5평이하';
  if (pyeong <= 10) return '5~10평';
  if (pyeong <= 15) return '10~15평';
  if (pyeong <= 20) return '15~20평';
  if (pyeong <= 25) return '20~25평';
  if (pyeong <= 30) return '25~30평';
  if (pyeong <= 40) return '30~40평';
  if (pyeong <= 50) return '40~50평';
  return '50평이상';
}

// ── 층수 구간 ──
export function floorBracket(floorStr: string): string {
  if (/반지하|반지층|B1|지하/.test(floorStr)) return '반지하';
  if (/옥탑|탑층|펜트/.test(floorStr)) return '옥탑';
  if (/복층/.test(floorStr)) return '복층';
  const m = floorStr.match(/(\d+)\s*층/);
  if (!m) return '';
  const f = parseInt(m[1]);
  if (f === 1) return '1층';
  if (f <= 3) return '저층';
  if (f <= 8) return '중층';
  if (f <= 15) return '고층';
  return '초고층';
}

// ── 입주시기 구간 ──
export function moveinBracket(moveIn: string): string {
  if (/즉시|바로|공실|입주가능/.test(moveIn)) return '즉시입주';
  if (/협의/.test(moveIn)) return '입주협의';
  const ym = moveIn.match(/(20\d{2})\s*[-년.]\s*(\d{1,2})/);
  if (ym) {
    const y = parseInt(ym[1]), mo = parseInt(ym[2]);
    if (y === 2026 && mo <= 6) return '2026상반기';
    if (y === 2026 && mo > 6) return '2026하반기';
    return `${y}년`;
  }
  const mm = moveIn.match(/(\d{1,2})\s*월/);
  if (mm) {
    const mo = parseInt(mm[1]);
    return mo <= 6 ? '2026상반기' : '2026하반기';
  }
  return '';
}

// ── 카테고리 코드 → 표준 태그 ──
const CAT_MAP: Record<string, string> = {
  apartment: '아파트', officetel: '오피스텔', room: '원투룸',
  commercial: '상가', office: '사무실',
};

// ── rawText에서 추가 키워드 감지 ──
function extractFromText(text: string): string[] {
  const tags: string[] = [];
  const t = text;
  // 지하철 노선
  if (/1호선/.test(t)) tags.push('1호선');
  if (/2호선/.test(t)) tags.push('2호선');
  if (/3호선/.test(t)) tags.push('3호선');
  if (/4호선/.test(t)) tags.push('4호선');
  if (/5호선/.test(t)) tags.push('5호선');
  if (/6호선/.test(t)) tags.push('6호선');
  if (/7호선/.test(t)) tags.push('7호선');
  if (/8호선/.test(t)) tags.push('8호선');
  if (/9호선/.test(t)) tags.push('9호선');
  if (/신분당/.test(t)) tags.push('신분당선');
  if (/경의중앙/.test(t)) tags.push('경의중앙선');
  if (/분당/.test(t)&&!/신분당/.test(t)) tags.push('분당선');
  // 교통
  if (/지하철\s*[1-5]\s*분|역\s*도보\s*[1-3]\s*분|역\s*바로/.test(t)) tags.push('초역세권');
  else if (/지하철|역\s*도보|역세권|역\s*\d분/.test(t)) tags.push('역세권');
  if (/더블역세권|2개\s*노선|트리플/.test(t)) tags.push('더블역세권');
  if (/버스|대중교통|교통\s*편리/.test(t)) tags.push('대중교통편리');
  if (/대로변|큰\s*길/.test(t)) tags.push('대로변');
  // 교육
  if (/학군|학교\s*근처|초등학교|중학교/.test(t)) tags.push('학군좋음');
  if (/학원가|학원\s*밀집/.test(t)) tags.push('학원가');
  if (/학세권|대학교|대학가/.test(t)) tags.push('학세권');
  // 뷰
  if (/한강\s*뷰|한강\s*조망|리버뷰/.test(t)) tags.push('한강뷰');
  if (/공원\s*뷰|공원\s*근처|공원\s*앞/.test(t)) tags.push('공원뷰');
  if (/산\s*뷰|산\s*조망/.test(t)) tags.push('산뷰');
  if (/시티뷰|도심\s*조망|야경/.test(t)) tags.push('시티뷰');
  if (/탁트인|전망\s*좋|오픈뷰/.test(t)) tags.push('탁트인전망');
  // 환경
  if (/조용|한적/.test(t)) tags.push('조용한동네');
  if (/채광|환한|밝은/.test(t)) tags.push('채광좋음');
  if (/마트|편의점\s*근처/.test(t)) tags.push('편의시설근처');
  if (/병원|의원|약국\s*근처/.test(t)) tags.push('병원근처');
  // 보안
  if (/CCTV|24시간\s*관리/.test(t)) tags.push('보안');
  if (/무인택배|택배함/.test(t)) tags.push('무인택배');
  // 시설
  if (/분리형/.test(t)) tags.push('분리형');
  if (/복도식/.test(t)) tags.push('복도식');
  if (/계단식/.test(t)) tags.push('계단식');
  // 상가
  if (/전면\s*넓|전면\s*광고/.test(t)) tags.push('전면넓음');
  if (/코너|모퉁이/.test(t)) tags.push('코너자리');
  if (/유동\s*인구|유동\s*많/.test(t)) tags.push('유동인구많음');
  if (/간판\s*가능|대형\s*간판/.test(t)) tags.push('간판가능');
  if (/권리금\s*없|무권리/.test(t)) tags.push('권리금없음');
  if (/업종\s*제한\s*없|업종\s*자유|모든\s*업종/.test(t)) tags.push('업종제한없음');
  // 상태
  if (/깨끗|청결|상태\s*좋/.test(t)) tags.push('깨끗한');
  if (/통풍/.test(t)) tags.push('통풍좋음');
  // 금융조건
  if (/HUG|허그|안심전세|보증보험/.test(t)) tags.push('HUG가능');
  if (/무융자|융자\s*없|등기\s*깨끗|선순위\s*없/.test(t)) tags.push('무융자');
  if (/전세대출|버팀목|신생아특례|디딤돌|대출\s*가능/.test(t)) tags.push('대출가능');
  if (/관포|관리비\s*포함|관리비\s*없|관\s*없/.test(t)) tags.push('관리비포함');
  // 신조어
  if (/초품아|초등학교\s*품|단지\s*내\s*초교|초세권/.test(t)) tags.push('초품아');
  if (/슬세권|슬리퍼/.test(t)) tags.push('슬세권');
  if (/런세권|산책로|천변/.test(t)) tags.push('런세권');
  if (/숲세권/.test(t)) tags.push('숲세권');
  if (/GTX/.test(t)) tags.push('GTX역세권');
  if (/맥세권|맥도날드/.test(t)) tags.push('맥세권');
  if (/스세권|별세권|스타벅스/.test(t)) tags.push('스세권');
  if (/몰세권|쇼핑몰|대형마트/.test(t)) tags.push('몰세권');
  // 가격
  if (/네고|가격\s*조절|협의\s*가능/.test(t)) tags.push('가격협의');
  return tags;
}

// ═══════════════════════════════════════════════════════════
// generateTags — 카드 데이터 → 표준 태그 배열
// ═══════════════════════════════════════════════════════════
export function generateTags(card: any): string[] {
  if (!card) return [];
  const p = card.property || {};
  const tags: string[] = [];

  // 1. 지역 (계층: 서울 > 구 > 동)
  tags.push('서울'); // 현재 서울만
  const loc = p.location || '';
  const guMatch = loc.match(/([\uAC00-\uD7AF]+구)/);
  if (guMatch) tags.push(guMatch[1]);
  const dongMatch = loc.match(/([\uAC00-\uD7AF]+동)/);
  if (dongMatch && dongMatch[1] !== guMatch?.[1]) tags.push(dongMatch[1]);

  // 1-1. 단지명 태그
  const complex = (p.complex || '').replace(/아파트|오피스텔/g, '').trim();
  if (complex && complex.length >= 2) tags.push(complex);

  // 2. 거래유형
  const type = p.type || '';
  if (type && type !== '손님') {
    const stdType = SYNONYM_MAP[type] || type;
    if (stdType && ['매매','전세','월세','반전세'].includes(stdType)) tags.push(stdType);
  }

  // 3. 매물유형
  let propType = CAT_MAP[p.category] || '';
  if (!propType) {
    const all = [p.complex, p.location, p.rawText, ...(p.features || [])].filter(Boolean).join(' ');
    if (/상가|점포|매장|식당|카페|편의점/.test(all)) propType = '상가';
    else if (/사무실|오피스(?!텔)|업무/.test(all)) propType = '사무실';
    else if (/오피스텔/.test(all)) propType = '오피스텔';
    else if (/아파트/.test(all)) propType = '아파트';
    else if (APT_BRANDS.some(b => all.includes(b))) propType = '아파트';
    else if (/빌라|다세대|연립|원룸|투룸|쓰리룸|1룸|2룸|3룸/.test(all)) propType = '원투룸';
  }
  if (propType) tags.push(propType);
  // 세부 유형 태그 (카테고리와 별도)
  const allForSub = [p.complex, p.location, p.rawText, ...(p.features || [])].filter(Boolean).join(' ');
  if (/빌라|다세대|연립/.test(allForSub) && !tags.includes('빌라')) tags.push('빌라');
  if (/원룸|1룸/.test(allForSub) && !tags.includes('원룸')) tags.push('원룸');
  if (/투룸|2룸/.test(allForSub) && !tags.includes('투룸')) tags.push('투룸');
  if (/쓰리룸|3룸/.test(allForSub) && !tags.includes('쓰리룸')) tags.push('쓰리룸');

  // 4. 가격대 (UI/검색용 태그)
  const pn = card.price_number || 0;
  const tradeType = type === '손님' ? (card.wanted_trade_type || '') : type;
  if (tradeType === '월세') {
    if (card.deposit) tags.push(depositBracket(card.deposit));
    if (card.monthly_rent) tags.push(monthlyBracket(card.monthly_rent));
  } else if (pn > 0) {
    tags.push(...priceBracket(pn, tradeType));
  }

  // 5. 면적
  const areaStr = p.area || '';
  const pyMatch = areaStr.match(/(\d+\.?\d*)\s*평/) || areaStr.match(/(\d+\.?\d*)\s*㎡/);
  if (pyMatch) {
    let py = parseFloat(pyMatch[1]);
    if (areaStr.includes('㎡')) py = Math.round(py / 3.305785);
    tags.push(areaBracket(py));
  }

  // 6. 층수
  const floorStr = p.floor || '';
  const fb = floorBracket(floorStr);
  if (fb) tags.push(fb);

  // 7. 방구조
  const room = p.room || '';
  if (/원룸|1룸/.test(room)) tags.push('원룸');
  else if (/투룸|2룸/.test(room)) tags.push('투룸');
  else if (/쓰리룸|3룸/.test(room)) tags.push('쓰리룸');
  else if (/4룸|포룸/.test(room)) tags.push('포룸이상');

  // 8. features → 표준 태그 변환
  (p.features || []).forEach((f: string) => {
    const std = SYNONYM_MAP[f] || f;
    if (!tags.includes(std)) tags.push(std);
  });

  // 9. 입주시기
  const moveIn = p.moveIn || card.move_in_date || '';
  const mb = moveinBracket(moveIn);
  if (mb) tags.push(mb);

  // 10. rawText 추가 감지
  const rawText = p.rawText || '';
  extractFromText(rawText).forEach(t => { if (!tags.includes(t)) tags.push(t); });

  // 11. 손님 전용: wanted_trade_type, wanted_categories
  if (type === '손님') {
    const wt = card.wanted_trade_type;
    if (wt) tags.push(wt);
    const wcs = card.wanted_categories || [];
    wcs.forEach((c: string) => {
      const std = CAT_MAP[c] || c;
      if (!tags.includes(std)) tags.push(std);
    });
    // wanted_conditions에서 복수 거래유형
    const conds = card.wanted_conditions || [];
    conds.forEach((c: any) => {
      if (c.trade_type && !tags.includes(c.trade_type)) tags.push(c.trade_type);
    });
  }

  // 중복 제거 + 빈 문자열 필터
  return [...new Set(tags)].filter(t => t && t.trim());
}

// ═══════════════════════════════════════════════════════════
// 제외 태그 추출 — "빼고", "싫어요", "안돼요", "제외"
// ═══════════════════════════════════════════════════════════
export function extractExcludedTags(text: string): string[] {
  const excluded: string[] = [];
  const patterns = [
    /반지하\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
    /옥탑\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
    /1층\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
    /저층\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
    /북향\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
    /복도식\s*(?:빼고|싫|안돼|제외|말고|NO)/i,
  ];
  const tagMap: Record<string, string> = {
    '반지하':'반지하','옥탑':'옥탑','1층':'1층','저층':'저층','북향':'북향','복도식':'복도식'
  };
  for (const [keyword, tag] of Object.entries(tagMap)) {
    const re = new RegExp(`${keyword}\\s*(?:빼고|싫|안돼|안됨|제외|말고|NO|안되|빼|빼주)`, 'i');
    if (re.test(text)) excluded.push(tag);
  }
  return excluded;
}
