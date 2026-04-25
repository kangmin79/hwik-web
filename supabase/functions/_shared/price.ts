// ═══════════════════════════════════════════════════════════
// 휙 가격 파싱 — 손님 텍스트 → 구조화된 가격 조건
// auto-match, match-properties 등에서 공유
// ═══════════════════════════════════════════════════════════

export interface PriceCondition {
  minPrice: number | null;   // 매매/전세 최소 (만원)
  maxPrice: number | null;   // 매매/전세 최대 (만원)
  deposit: number | null;    // 월세 보증금 희망 (만원)
  maxDeposit: number | null; // 월세 보증금 최대 (만원)
  monthly: number | null;    // 월세 희망 (만원)
  maxMonthly: number | null; // 월세 최대 (만원)
}

// 한국식 가격 파싱: "3억5천" → 35000, "5천" → 5000, "800" → 800
export function parseKorPrice(s: string): number {
  let total = 0;
  const ek = s.match(/(\d+\.?\d*)\s*억/);
  const ch = s.match(/(\d+)\s*천/);
  const mn = s.match(/(\d+)\s*만/);
  if (ek) total += parseFloat(ek[1]) * 10000;
  if (ch) total += parseInt(ch[1]) * 1000;
  if (mn) total += parseInt(mn[1]);
  if (total > 0) return total;
  const n = parseInt(s.replace(/[^\d]/g, ''));
  return isNaN(n) ? 0 : n;
}

// 손님 텍스트에서 가격 조건 추출
export function parsePriceCondition(text: string, tradeType?: string): PriceCondition {
  const result: PriceCondition = {
    minPrice: null, maxPrice: null,
    deposit: null, maxDeposit: null,
    monthly: null, maxMonthly: null,
  };

  // ── 매매/전세 가격 ──

  // "3억 3억5천까지 가능/괜찮" (희망가 + 최대가)
  const dualPrice = text.match(/(\d+\.?\d*억(?:\s*\d+천)?)\s+(\d+\.?\d*억(?:\s*\d+천)?)\s*(?:까지|이하|이내|도|면)?\s*(?:가능|괜찮|OK|ok|됩니다|돼요|상관없|무방)/i);
  if (dualPrice) {
    result.minPrice = parseKorPrice(dualPrice[1]);
    result.maxPrice = parseKorPrice(dualPrice[2]);
    if (result.minPrice > result.maxPrice) {
      const t = result.minPrice; result.minPrice = result.maxPrice; result.maxPrice = t;
    }
  }

  // "3억~5억" / "3억에서 5억" / "3억부터 5억"
  if (!result.maxPrice) {
    const rangeMatch = text.match(/(\d+\.?\d*)\s*억\s*(?:~|에서|부터)\s*(\d+\.?\d*)\s*억/);
    if (rangeMatch) {
      result.minPrice = parseFloat(rangeMatch[1]) * 10000;
      result.maxPrice = parseFloat(rangeMatch[2]) * 10000;
    }
  }

  // "2억에서 3억 사이"
  if (!result.maxPrice) {
    const betw = text.match(/(\d+\.?\d*)\s*억\s*(?:에서|부터)\s*(\d+\.?\d*)\s*억\s*(?:사이|까지)/);
    if (betw) {
      result.minPrice = parseFloat(betw[1]) * 10000;
      result.maxPrice = parseFloat(betw[2]) * 10000;
    }
  }

  // "3억5천 이내/이하/미만/까지/밑으로"
  if (!result.maxPrice) {
    const maxMatch = text.match(/(\d+\.?\d*)\s*억\s*(\d+)?\s*천?\s*(?:이내|이하|미만|까지|밑으로|내로|안넘는|못넘는|넘지\s*않게|안넘게|초과\s*안)/);
    if (maxMatch) result.maxPrice = parseFloat(maxMatch[1]) * 10000 + (maxMatch[2] ? parseInt(maxMatch[2]) * 1000 : 0);
  }

  // "5천만원 이내" / "5천 이하"
  if (!result.maxPrice) {
    const chun = text.match(/(\d+)\s*천\s*(?:만원?)?\s*(?:이내|이하|밑으로|까지|넘지\s*않게)/);
    if (chun) result.maxPrice = parseInt(chun[1]) * 1000;
  }

  // "3억 이상" / "3억5천 이상"
  if (!result.minPrice) {
    const minMatch = text.match(/(\d+\.?\d*)\s*억\s*(\d+)?\s*천?\s*(?:이상|초과|넘는|부터|위로|넘게)/);
    if (minMatch) result.minPrice = parseFloat(minMatch[1]) * 10000 + (minMatch[2] ? parseInt(minMatch[2]) * 1000 : 0);
  }

  // "3억선" / "3억대" / "3억 정도/쯤/내외/안팎/전후/언저리" → ±15%
  if (!result.maxPrice && !result.minPrice) {
    const approx = text.match(/(\d+\.?\d*)\s*억\s*(?:\d*천?\s*)?(?:정도|쯤|선에서|선|대|내외|안팎|전후|언저리|근처)/);
    if (approx) {
      const base = parseFloat(approx[1]) * 10000;
      result.minPrice = Math.round(base * 0.85);
      result.maxPrice = Math.round(base * 1.15);
    }
  }

  // 가격만 단독 ("3억") → 희망가 ±15%
  if (!result.maxPrice && !result.minPrice) {
    const barePrice = text.match(/(\d+\.?\d*)\s*억/);
    if (barePrice) {
      const base = parseFloat(barePrice[1]) * 10000;
      result.minPrice = Math.round(base * 0.85);
      result.maxPrice = Math.round(base * 1.15);
    }
  }

  // ── 월세: 보증금 + 월세 ──
  if (tradeType === '월세' || /월세|ㅇㅅ|보증금|보\d|보\/월/.test(text)) {
    // "보800/월50" "보증금800/월세50"
    const boWolMatch = text.match(/보(?:증금)?\s*(\d[\d,]*)\s*\/\s*월(?:세)?\s*(\d[\d,]*)/);
    if (boWolMatch) {
      result.deposit = parseInt(boWolMatch[1].replace(/,/g, ''));
      result.monthly = parseInt(boWolMatch[2].replace(/,/g, ''));
    }

    // [C] 슬래시 + 상한 표현: "1000/200 이하" / "월세 1000/200 이하" → deposit 고정, maxMonthly 명시
    if (!result.maxMonthly) {
      const slashMax = text.match(/(\d+)\s*\/\s*(\d+)\s*(?:이하|까지|이내|미만|넘지\s*않게)/);
      if (slashMax) {
        if (!result.deposit) result.deposit = parseInt(slashMax[1]);
        result.maxMonthly = parseInt(slashMax[2]);
      }
    }

    // "1000/50 2000/40도 가능" — 두 번째 조건이 max
    if (!result.maxDeposit) {
      const dualSlash = text.match(/(\d+)\s*\/\s*(\d+)\s+(\d+)\s*\/\s*(\d+)\s*(?:도|면|까지)?\s*(?:가능|괜찮|OK)/i);
      if (dualSlash) {
        result.deposit = parseInt(dualSlash[1]);
        result.monthly = parseInt(dualSlash[2]);
        result.maxDeposit = parseInt(dualSlash[3]);
        result.maxMonthly = parseInt(dualSlash[4]);
      }
    }

    // "보증금 1000~2000" 범위
    if (!result.deposit) {
      const depRange = text.match(/보(?:증금)?\s*(\d+)\s*[~에서]\s*(\d+)/);
      if (depRange) {
        result.deposit = parseInt(depRange[1]);
        result.maxDeposit = parseInt(depRange[2]);
      }
    }

    // "월세 30~50" 범위
    if (!result.monthly) {
      const monRange = text.match(/월(?:세)?\s*(\d+)\s*[~에서]\s*(\d+)/);
      if (monRange) {
        result.monthly = parseInt(monRange[1]);
        result.maxMonthly = parseInt(monRange[2]);
      }
    }

    // "무보증" / "보증금 없이"
    if (/무보증|보증금\s*없|보증금\s*0/.test(text)) {
      result.deposit = 0;
      result.maxDeposit = 0;
    }

    // "보증금 2000 이하"
    if (!result.maxDeposit && result.maxDeposit !== 0) {
      const depMax = text.match(/보(?:증금)?\s*(\d+)\s*(?:이하|까지|이내|넘지\s*않게|미만)/);
      if (depMax) result.maxDeposit = parseInt(depMax[1]);
    }

    // "월세 50 이하"
    if (!result.maxMonthly) {
      const monMax = text.match(/월(?:세)?\s*(\d+)\s*(?:이하|까지|이내|넘지\s*않게|미만)/);
      if (monMax) result.maxMonthly = parseInt(monMax[1]);
    }

    // 단일 보증금 ("보증금800" 또는 "보800")
    if (!result.deposit && result.deposit !== 0) {
      const depMatch = text.match(/보(?:증금)?\s*(\d[\d,]*)/);
      if (depMatch) result.deposit = parseInt(depMatch[1].replace(/,/g, ''));
    }

    // 단일 월세 ("월50" 또는 "월세50")
    if (!result.monthly) {
      const monMatch = text.match(/월(?:세)?\s*(\d[\d,]*)/);
      if (monMatch) result.monthly = parseInt(monMatch[1].replace(/,/g, ''));
    }

    // "1000/50" 슬래시 패턴 (보증금/월세)
    if (!result.deposit && !result.monthly) {
      const slashMatch = text.match(/(\d+)\s*\/\s*(\d+)/);
      if (slashMatch) {
        result.deposit = parseInt(slashMatch[1]);
        result.monthly = parseInt(slashMatch[2]);
      }
    }

    // "천에 50" / "오백에 30" 한국어 말투 패턴
    if (!result.deposit && !result.monthly) {
      const koMatch = text.match(/([\d]+천|[\d]+백|[\d]+억|천|오백|이천|삼천|오천)\s*에\s*(\d+)/);
      if (koMatch) {
        let dep = koMatch[1];
        if (dep === '천') dep = '1000';
        else if (dep === '오백') dep = '500';
        else if (dep === '이천') dep = '2000';
        else if (dep === '삼천') dep = '3000';
        else if (dep === '오천') dep = '5000';
        else if (dep.includes('억')) dep = String(parseInt(dep) * 10000);
        else if (dep.includes('천')) dep = String(parseInt(dep) * 1000);
        else if (dep.includes('백')) dep = String(parseInt(dep) * 100);
        result.deposit = parseInt(dep);
        result.monthly = parseInt(koMatch[2]);
      }
    }
  }

  return result;
}

// ── 면적 조건 파싱 ──
export interface AreaCondition {
  minArea: number | null;  // 최소 평수
  maxArea: number | null;  // 최대 평수
}

export function parseAreaCondition(text: string): AreaCondition {
  const result: AreaCondition = { minArea: null, maxArea: null };

  // "20평~30평" / "20에서 30평"
  const rangeMatch = text.match(/(\d+)\s*평?\s*[~에서부터]\s*(\d+)\s*평/);
  if (rangeMatch) {
    result.minArea = parseInt(rangeMatch[1]);
    result.maxArea = parseInt(rangeMatch[2]);
    return result;
  }

  // "30평대" → 30~39
  const daeMatch = text.match(/(\d+)\s*평\s*대/);
  if (daeMatch) {
    result.minArea = parseInt(daeMatch[1]);
    result.maxArea = parseInt(daeMatch[1]) + 9;
    return result;
  }

  // "25평 내외" → ±10%
  const naewoeMatch = text.match(/(\d+)\s*평\s*내외/);
  if (naewoeMatch) {
    const p = parseInt(naewoeMatch[1]);
    result.minArea = Math.round(p * 0.9);
    result.maxArea = Math.round(p * 1.1);
    return result;
  }

  // "20평 이상" / "최소 20평" / "적어도 25평"
  const minMatch = text.match(/(?:최소|적어도)?\s*(\d+)\s*평\s*(?:이상|넘는|넘게|부터)/);
  if (minMatch) result.minArea = parseInt(minMatch[1]);
  // "최소 20평" (이상 없이)
  if (!result.minArea) {
    const minMatch2 = text.match(/(?:최소|적어도)\s*(\d+)\s*평/);
    if (minMatch2) result.minArea = parseInt(minMatch2[1]);
  }

  // "30평 이하" / "최대 30평"
  const maxMatch = text.match(/(?:최대)?\s*(\d+)\s*평\s*(?:이하|까지|미만|이내)/);
  if (maxMatch) result.maxArea = parseInt(maxMatch[1]);
  // "최대 25평" (이하 없이)
  if (!result.maxArea) {
    const maxMatch2 = text.match(/최대\s*(\d+)\s*평/);
    if (maxMatch2) result.maxArea = parseInt(maxMatch2[1]);
  }

  // "넓은 집" → 35평 이상 (중개사 관행: 대형 = 전용 85㎡ 초과 ≈ 30평대 후반~)
  if (!result.minArea && /넓은|넓고|큰\s*집|대형/.test(text)) result.minArea = 35;
  // "소형" → 20평 이하 (중개사 관행: 소형 = 전용 60㎡ 이하 ≈ 20평 이하)
  if (!result.maxArea && /소형|작은|좁은|소규모/.test(text)) result.maxArea = 20;
  // "중형" → 20~35평
  if (!result.minArea && !result.maxArea && /중형|적당한/.test(text)) {
    result.minArea = 20;
    result.maxArea = 35;
  }

  // 숫자만 ("25평") → ±5
  if (!result.minArea && !result.maxArea) {
    const bareMatch = text.match(/(\d+)\s*평/);
    if (bareMatch) {
      const p = parseInt(bareMatch[1]);
      result.minArea = Math.max(p - 5, 1);
      result.maxArea = p + 5;
    }
  }

  return result;
}

// ── 매물 가격이 손님 조건에 맞는지 체크 ──
export function isPriceMatch(
  propPrice: number,          // 매물 price_number (만원)
  condition: PriceCondition,  // 손님 조건
  tradeType: string,          // 거래유형
  propDeposit?: number,       // 매물 보증금 (월세)
  propMonthly?: number,       // 매물 월세
): boolean {
  if (tradeType === '월세') {
    // [B] 보증금: maxDeposit 명시 = × 1.001 엄격 / deposit만 있으면 × 1.15 (모호)
    const effMaxDep = condition.maxDeposit
      ? Math.round(condition.maxDeposit * 1.001)
      : (condition.deposit ? Math.round(condition.deposit * 1.15) : null);
    if (effMaxDep && propDeposit && propDeposit > effMaxDep) return false;

    // [B] 월세: maxMonthly 명시 = × 1.001 엄격 / monthly만 있으면 × 1.15 (모호)
    const effMaxMon = condition.maxMonthly
      ? Math.round(condition.maxMonthly * 1.001)
      : (condition.monthly ? Math.round(condition.monthly * 1.15) : null);
    if (effMaxMon && propMonthly && propMonthly > effMaxMon) return false;

    return true;
  }

  // 매매/전세
  if (!propPrice || propPrice <= 0) return true;

  // [B] maxPrice 명시된 경우: 0.1% 여유만 (LLM 반올림 오차 흡수)
  if (condition.maxPrice && propPrice > condition.maxPrice * 1.001) return false;

  // [B] minPrice 명시된 경우: 0.1% 여유
  if (condition.minPrice && propPrice < condition.minPrice * 0.999) return false;

  return true;
}

// ── 매물 면적이 손님 조건에 맞는지 체크 ──
export function isAreaMatch(
  propArea: string | undefined,  // 매물 면적 텍스트 ("25평" 또는 "84㎡")
  condition: AreaCondition,
): boolean {
  if (!propArea || (!condition.minArea && !condition.maxArea)) return true;

  // 평수 추출
  let pyeong = 0;
  const pyMatch = propArea.match(/(\d+\.?\d*)\s*평/);
  const sqmMatch = propArea.match(/(\d+\.?\d*)\s*㎡/);
  if (pyMatch) pyeong = parseFloat(pyMatch[1]);
  else if (sqmMatch) pyeong = Math.round(parseFloat(sqmMatch[1]) / 3.305785);
  if (!pyeong) return true;

  if (condition.maxArea && pyeong > condition.maxArea * 1.1) return false;
  if (condition.minArea && pyeong < condition.minArea * 0.9) return false;

  return true;
}
