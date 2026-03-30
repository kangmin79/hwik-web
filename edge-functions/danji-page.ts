import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

/**
 * 단지 페이지 SSR — 구글봇/AI 검색 최적화
 *
 * 호출: /functions/v1/danji-page?id=raemian-mapo-riverwell
 * 또는 hwik.kr에서 Cloudflare/Vercel rewrite로 연결
 *
 * 구글봇 → 이 Edge Function → 완성된 HTML (SEO 콘텐츠 포함)
 * 일반 사용자 → danji.html → CSR (빠른 인터랙션)
 */

const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
const SUPABASE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY') || '';
const BASE_URL = 'https://hwik.kr';

function esc(s: string | null | undefined): string {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function formatPrice(manwon: number | null): string {
  if (!manwon) return '-';
  const uk = Math.floor(manwon / 10000);
  const rest = manwon % 10000;
  if (uk > 0 && rest > 0) {
    const cheon = Math.floor(rest / 1000);
    return cheon > 0 ? `${uk}억 ${cheon}천` : `${uk}억 ${rest}`;
  }
  if (uk > 0) return `${uk}억`;
  return `${manwon.toLocaleString()}만`;
}

function walkMin(m: number): string {
  if (!m) return '';
  return Math.round(m / 67) + '분';
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const id = url.searchParams.get('id');

  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': 'public, max-age=3600, s-maxage=86400',
  };

  if (!id) {
    return new Response('<html><body>단지 ID가 필요합니다</body></html>', { status: 400, headers });
  }

  try {
    const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
    const { data, error } = await supabase.from('danji_pages').select('*').eq('id', id).single();

    if (error || !data) {
      return new Response('<html><body>단지 정보를 찾을 수 없습니다</body></html>', { status: 404, headers });
    }

    const d = data;
    const cats = d.categories || [];
    const recent = d.recent_trade || {};
    const high = d.all_time_high || {};
    const subway = d.nearby_subway || [];
    const school = d.nearby_school || [];
    const nearby = d.nearby_complex || [];
    const listings = d.active_listings || [];

    // 첫 번째 평형 기준 지표
    const firstCat = cats[0] || '';
    const recentData = recent[firstCat];
    const highData = high[firstCat];
    const jeonseData = recent[firstCat + '_jeonse'];

    const recentPrice = recentData?.price || null;
    const highPrice = highData?.price || null;
    let jeonseRate = d.jeonse_rate;
    if (jeonseData && recentData && recentData.price > 0) {
      jeonseRate = Math.round(jeonseData.price / recentData.price * 1000) / 10;
    }

    const title = `${d.complex_name} 실거래가 시세 - 휙`;
    const desc = `${d.complex_name} ${d.location} ${d.total_units || ''}세대 ${d.build_year || ''}년 아파트 실거래가, 전세가, 시세 추이`;
    const canonicalUrl = `${BASE_URL}/danji.html?id=${id}`;

    // 지하철/학교 태그
    const tagHtml = [
      ...subway.map((s: any) => `<span>${esc(s.name)} ${walkMin(s.distance)}</span>`),
      ...school.slice(0, 2).map((s: any) => `<span>${esc(s.name)} ${walkMin(s.distance)}</span>`)
    ].join(' · ');

    // 평형별 가격 요약
    const priceRows = cats.map((c: string) => {
      const py = Math.round(parseInt(c) / 3.3058);
      const r = recent[c];
      const h = high[c];
      const j = recent[c + '_jeonse'];
      return `<tr>
        <td>${py > 0 ? py + '평' : c} (${c}㎡)</td>
        <td>${r ? formatPrice(r.price) : '-'}</td>
        <td>${h ? formatPrice(h.price) : '-'}</td>
        <td>${j ? formatPrice(j.price) : '-'}</td>
      </tr>`;
    }).join('');

    // 매매 거래 목록
    const saleItems: any[] = [];
    for (const [key, val] of Object.entries(recent)) {
      if (!key.includes('_')) saleItems.push(val);
    }
    saleItems.sort((a: any, b: any) => (b.date || '').localeCompare(a.date || ''));
    const tradeHtml = saleItems.slice(0, 5).map((t: any) =>
      `<li>${formatPrice(t.price)} (${t.floor ? t.floor + '층' : ''} ${t.date || ''})</li>`
    ).join('');

    // 주변 단지
    const nearbyHtml = nearby.map((n: any) =>
      `<li><a href="${BASE_URL}/danji.html?id=${esc(n.id)}">${esc(n.name)}</a> - ${esc(n.location)} ${n.price_84 ? '84㎡ ' + formatPrice(n.price_84) : ''}</li>`
    ).join('');

    // Breadcrumb
    const locationParts = (d.location || '').split(' ');
    const gu = locationParts[0] || '';
    const dong = locationParts[1] || locationParts[0] || '';

    // FAQ — 데이터가 확실한 항목만
    const faqItems: {q:string, a:string}[] = [];
    if (recentPrice) faqItems.push({ q: `${d.complex_name} 최근 실거래가는?`, a: `${d.complex_name} 최근 매매 실거래가는 ${formatPrice(recentPrice)}입니다.${recentData?.date ? ` (${recentData.date} 기준)` : ''}` });
    if (jeonseRate) faqItems.push({ q: `${d.complex_name} 전세가율은?`, a: `${d.complex_name}의 전세가율은 ${jeonseRate}%입니다.` });
    if (subway.length > 0) faqItems.push({ q: `${d.complex_name} 근처 지하철역은?`, a: subway.map((s: any) => `${s.name}(${s.line || ''}) 도보 ${walkMin(s.distance)}`).join(', ') });
    if (highPrice) faqItems.push({ q: `${d.complex_name} 역대 최고가는?`, a: `역대 최고가는 ${formatPrice(highPrice)}입니다.${highData?.date ? ` (${highData.date})` : ''}` });

    // JSON-LD: Residence + BreadcrumbList + FAQPage
    const jsonLd = JSON.stringify({
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "Residence",
          "name": d.complex_name,
          "address": { "@type": "PostalAddress", "addressLocality": d.location, "streetAddress": d.address, "addressRegion": "서울특별시", "addressCountry": "KR" },
          "geo": { "@type": "GeoCoordinates", "latitude": d.lat, "longitude": d.lng },
          "description": desc,
          "numberOfRooms": d.total_units,
          "yearBuilt": d.build_year,
        },
        {
          "@type": "BreadcrumbList",
          "itemListElement": [
            { "@type": "ListItem", "position": 1, "name": "휙", "item": BASE_URL },
            { "@type": "ListItem", "position": 2, "name": `서울 ${gu}`, "item": `${BASE_URL}/danji.html?gu=${encodeURIComponent(gu)}` },
            { "@type": "ListItem", "position": 3, "name": d.complex_name, "item": canonicalUrl },
          ]
        },
        {
          "@type": "FAQPage",
          "mainEntity": faqItems.map(f => ({
            "@type": "Question",
            "name": f.q,
            "acceptedAnswer": { "@type": "Answer", "text": f.a }
          }))
        }
      ]
    });

    const html = `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${canonicalUrl}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="휙">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:image" content="${BASE_URL}/og-image.png">
<meta property="og:url" content="${canonicalUrl}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${esc(desc)}">
<script type="application/ld+json">${jsonLd}</script>
<style>
body{font-family:-apple-system,'Noto Sans KR',sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#1a1a2e;line-height:1.7}
h1{font-size:22px;margin-bottom:4px}
.sub{color:#6b7280;font-size:14px;margin-bottom:16px}
.tags{color:#6b7280;font-size:13px;margin-bottom:20px}
table{width:100%;border-collapse:collapse;margin:12px 0 20px}
th,td{padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:13px}
th{background:#f3f4f6;font-weight:500}
h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid #e5e7eb;padding-bottom:6px}
ul{padding-left:20px}li{margin:4px 0;font-size:13px}
a{color:#1a6dd4;text-decoration:none}a:hover{text-decoration:underline}
.seo{font-size:12px;color:#9ca3af;line-height:1.8;margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb}
.faq dt{font-weight:500;font-size:14px;margin-top:12px}
.faq dd{font-size:13px;color:#4b5563;margin:4px 0 0 0}
.cta{display:inline-block;background:#f5c842;color:#1a1a2e;padding:12px 24px;border-radius:8px;font-weight:500;margin:16px 0}
.source{font-size:11px;color:#9ca3af;margin-top:8px}
nav.breadcrumb{font-size:12px;color:#9ca3af;margin-bottom:12px}
nav.breadcrumb a{color:#6b7280}
</style>
</head>
<body>

<nav class="breadcrumb" aria-label="breadcrumb">
  <a href="${BASE_URL}">휙</a> &gt; <a href="${BASE_URL}/danji.html?gu=${encodeURIComponent(gu)}">서울 ${esc(gu)}</a> &gt; ${esc(d.complex_name)}
</nav>

<h1>${esc(d.complex_name)}</h1>
<div class="sub">${esc(d.location)} · ${d.total_units ? d.total_units.toLocaleString() + '세대' : ''} · ${d.build_year || ''}년 준공</div>
<div class="tags">${tagHtml}</div>

<h2>평형별 시세</h2>
<table>
  <thead><tr><th>평형</th><th>최근 매매</th><th>역대 최고</th><th>전세</th></tr></thead>
  <tbody>${priceRows}</tbody>
</table>
${jeonseRate ? `<p>전세가율: <strong>${jeonseRate}%</strong></p>` : ''}

${tradeHtml ? `<h2>최근 매매 거래</h2><ul>${tradeHtml}</ul>` : ''}

${listings.length > 0 ? `<h2>휙 등록 매물</h2><p>현재 ${listings.length}건의 매물이 등록되어 있습니다.</p><a href="${BASE_URL}/danji.html?id=${id}" class="cta">매물 상세 보기</a>` : `<h2>매물 보기</h2><a href="${BASE_URL}/danji.html?id=${id}" class="cta">이 단지 시세 상세보기</a>`}

${nearbyHtml ? `<h2>${esc(dong)} 주변 단지</h2><ul>${nearbyHtml}</ul>` : ''}

<h2>자주 묻는 질문</h2>
<dl class="faq">
${faqItems.map(f => `  <dt>${esc(f.q)}</dt>\n  <dd>${esc(f.a)}</dd>`).join('\n')}
</dl>

<div class="seo"><p>${esc(d.complex_name)}은(는) ${d.address ? esc(d.address) + '에 위치한 ' : ''}${d.build_year ? d.build_year + '년 준공 ' : ''}아파트입니다.${d.total_units ? ' 총 ' + d.total_units.toLocaleString() + '세대 규모입니다.' : ''}${cats.length > 0 ? ' ' + cats.map((c: string) => { const p = Math.round(parseInt(c)/3.3058); return p > 0 ? p+'평('+c+'㎡)' : c+'㎡'; }).join(', ') + ' 평형이 있습니다.' : ''}${subway.length > 0 ? ' 인근 지하철: ' + subway.map((s:any) => esc(s.name) + (s.line ? '('+esc(s.line)+')' : '') + ' 도보 ' + walkMin(s.distance)).join(', ') + '.' : ''}${recentPrice ? ' 최근 매매 실거래가는 ' + formatPrice(recentPrice) + (recentData?.date ? ' (' + recentData.date + ' 기준)' : '') + '입니다.' : ''}</p></div>
<div class="source">실거래가 출처: 국토교통부 실거래가 공개시스템 · 매일 업데이트 · ${new Date().toISOString().split('T')[0]} 기준</div>

</body>
</html>`;

    return new Response(html, { headers });

  } catch (err: any) {
    console.error('danji-page error:', err.message);
    return new Response(`<html><body>오류가 발생했습니다</body></html>`, { status: 500, headers });
  }
});
