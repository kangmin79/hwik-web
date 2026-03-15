/**
 * 휙(Hwik) 공통 설정
 * - Supabase, Kakao 자격증명을 한 곳에서 관리
 * - 키 재생성 시 이 파일만 수정하면 됩니다
 */
const HWIK_CONFIG = {
    SUPABASE_URL: 'https://api.hwik.kr',
    SUPABASE_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxYXhlamd6a2NoeGJmemd6eXppIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2MzI3NTIsImV4cCI6MjA4MjIwODc1Mn0.-njNdAKVA7Me60H98AYaf-Z3oi45SfUmeoBNvuRJugE',
    KAKAO_JS_KEY: '124cd68b3419bde24e03efa4f1ca2830'
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
