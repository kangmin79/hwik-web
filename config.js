/**
 * 휙(Hwik) 공통 설정
 * - Supabase, Kakao 자격증명을 한 곳에서 관리
 * - 키 재생성 시 이 파일만 수정하면 됩니다
 */
const HWIK_CONFIG = {
    SUPABASE_URL: 'https://api.hwik.kr',
    SUPABASE_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxYXhlamd6a2NoeGJmemd6eXppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2MzI3NTIsImV4cCI6MjA4MjIwODc1Mn0.-njNdAKVA7Me60H98AYaf-Z3oi45SfUmeoBNvuRJugE',
    KAKAO_JS_KEY: '124cd68b3419bde24e03efa4f1ca2830',
    KAKAO_REST_KEY: '8b7ecadf67aaed392e75605093efb2c4'
};

/**
 * XSS 방지: HTML 이스케이프 헬퍼
 * - 모든 페이지에서 동일하게 사용
 */
function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * 부동산 종류 분류 (통합)
 * - 반환값: '아파트','오피스텔','원투룸','상가','사무실','기타'
 * - room 필드 → rawText → 가격 → 면적+층 순으로 추론
 */
const _categoryCache = {};
const _aptBrands = ['아파트','자이','래미안','힐스테이트','푸르지오','더샵','롯데캐슬',
    'e편한세상','아이파크','sk뷰','sk view','엘스','리센츠','트리지움','헬리오시티',
    '올림픽파크','아크로','반포자이','은마','주공','현대아파트','삼성아파트','대림아파트',
    '동아아파트','미도아파트','우성아파트','경남아파트','한신아파트','쌍용아파트',
    '서초아이파크','잠실엘스','잠실리센츠','잠실트리지움','레이크팰리스','파크리오',
    '청담자이','도곡렉슬','타워팰리스','갤러리아팰리스','목동아이파크','목동신시가지',
    '신반포','반포한양','반포주공','개포주공','개포자이','일원현대','대치아이파크',
    '대치은마','대치미도','역삼자이','역삼래미안','서초래미안','잠원한신','압구정현대',
    '압구정로데오','성수자이','용산파크타워','마포래미안','공덕자이','광장현대',
    '하이페리온','센트럴파크','베라체','센트레빌','자이더스타','포레나','우미린',
    '중흥s클래스','금호어울림','두산위브','한화포레나','대방노블랜드','신동아파밀리에',
    '벽산블루밍','한진한화','두산','위브','어울림','파밀리에','블루밍'];

function categorizeProperty(text, roomField, area, floor) {
    const cacheKey = `${text||''}|${roomField||''}|${area||''}|${floor||''}`;
    if (_categoryCache[cacheKey]) return _categoryCache[cacheKey];

    const result = _categorizePropertyInner(text, roomField, area, floor);
    _categoryCache[cacheKey] = result;
    return result;
}

function _categorizePropertyInner(text, roomField, area, floor) {
    // 1. AI가 파싱한 room 필드 우선 사용
    const r = (roomField || '').toLowerCase();
    if (r.includes('아파트') || r.includes('apt')) return '아파트';
    if (r.includes('오피스텔') || r.includes('officetel')) return '오피스텔';
    if (r.includes('상가') || r.includes('점포')) return '상가';
    if (r.includes('사무실') || r.includes('오피스')) return '사무실';
    if (r.includes('원룸') || r.includes('투룸') || r.includes('빌라') || r.includes('주택')) return '원투룸';

    // 2. rawText 텍스트 추론
    const t = (text || '').toLowerCase();
    if (t.includes('상가') || t.includes('점포') || t.includes('매장')) return '상가';
    if (t.includes('사무실') || t.includes('업무용')) return '사무실';
    if (t.includes('오피스텔')) return '오피스텔';

    if (_aptBrands.some(b => t.includes(b))) return '아파트';
    if (t.includes('원룸') || t.includes('투룸') || t.includes('빌라') || t.includes('연립') || t.includes('주택')) return '원투룸';

    // 3. 월세 금액으로 추론
    if (text && text.includes('/')) {
        const parts = text.match(/([\d,]+)\s*\/\s*([\d,]+)/);
        if (parts) {
            const deposit = parseInt(parts[1].replace(/,/g, ''));
            const monthly = parseInt(parts[2].replace(/,/g, ''));
            if (deposit <= 5000 && monthly <= 150) return '원투룸';
        }
    }

    // 4. 평수 + 층수로 추론
    const areaNum = parseInt((area || '').replace(/[^0-9]/g, '')) || 0;
    const floorNum = parseInt((floor || '').replace(/[^0-9]/g, '')) || 0;
    if (areaNum >= 20 && floorNum >= 5) return '아파트';
    if (areaNum >= 30) return '아파트';

    return '원투룸';
}

/**
 * 가격 포맷: 만원 단위 숫자 → "X억 Y천" 형태
 */
function formatPrice(m) {
    if (!m) return '-';
    const u = Math.floor(m / 10000), r = m % 10000;
    if (u > 0 && r > 0) { const c = Math.floor(r / 1000); return c > 0 ? u + '억 ' + c + '천' : u + '억 ' + r; }
    if (u > 0) return u + '억';
    return m.toLocaleString() + '만';
}

/**
 * 영문 카테고리 → 한글 매핑
 * - card_generator 등에서 서버가 반환한 영문 category를 한글로 변환할 때 사용
 */
const CATEGORY_KO = {
    'apartment': '아파트',
    'officetel': '오피스텔',
    'room': '원투룸',
    'commercial': '상가',
    'office': '사무실'
};

/**
 * 한글 카테고리 → 영문 매핑
 */
const CATEGORY_EN = {
    '아파트': 'apartment',
    '오피스텔': 'officetel',
    '원투룸': 'room',
    '상가': 'commercial',
    '사무실': 'office',
    '기타': 'room'
};

/**
 * SEO: Organization + WebSite 구조화 데이터 (모든 페이지 공통)
 */
(function() {
    const ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "name": "휙 (Hwik)",
                "url": "https://hwik.kr",
                "logo": "https://hwik.kr/og-image.png",
                "description": "중개사가 손님에게 매물을 '휙' 보내는 부동산 플랫폼. AI 매칭으로 조건에 맞는 매물을 자동 추천합니다.",
                "foundingDate": "2026",
                "areaServed": {
                    "@type": "Country",
                    "name": "대한민국"
                },
                "knowsAbout": ["부동산", "아파트 실거래가", "전세 시세", "부동산 중개"]
            },
            {
                "@type": "WebSite",
                "name": "휙",
                "url": "https://hwik.kr",
                "description": "서울 아파트 실거래가, 전세가, 시세 추이를 한눈에. 6,000개 단지 데이터 매일 업데이트."
                // SearchAction 제거 (2026-04-17): Google 이 2024-11 부터 sitelinks searchbox 지원 중단.
                // 효과 없이 /gu/{search_term_string} literal URL 이 크롤러에 의해 404 로 잡히기만 함.
            }
        ]
    };
    const s = document.createElement('script');
    s.type = 'application/ld+json';
    s.textContent = JSON.stringify(ld);
    document.head.appendChild(s);
})();
