import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const BASE_URL = 'https://hwik.kr';

// 슬러그 생성 (slug_utils.py의 make_danji_slug과 동기화)
function makeSlug(name: string, location: string, id: string, address: string): string {
  const METRO: Record<string, string> = {
    '서울특별시':'서울','인천광역시':'인천','부산광역시':'부산',
    '대구광역시':'대구','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산',
  };
  const PROVINCE: Record<string, string> = {'경기도':'경기','충청남도':'충남','충청북도':'충북','전라남도':'전남','전라북도':'전북','경상남도':'경남','경상북도':'경북','강원특별자치도':'강원','제주특별자치도':'제주'};

  let region = '', gu = '', dong = '';
  const locParts = location.split(' ');
  if (locParts.length >= 1) gu = locParts[0];
  if (locParts.length >= 2) dong = locParts.slice(1).join(' ');

  // address에서 region 추출
  const addrParts = (address || '').split(' ');
  const rawRegion = addrParts[0] || '';
  if (METRO[rawRegion]) {
    region = METRO[rawRegion];
  } else if (PROVINCE[rawRegion]) {
    region = PROVINCE[rawRegion];
  } else {
    // location 기반 추정
    if (['종로구','중구','용산구','성동구','광진구','동대문구','중랑구','성북구','강북구','도봉구','노원구','은평구','서대문구','마포구','양천구','강서구','구로구','금천구','영등포구','동작구','관악구','서초구','강남구','송파구','강동구'].includes(gu)) {
      region = '서울';
    } else if (['중구','동구','미추홀구','연수구','남동구','부평구','계양구','서구','강화군','옹진군'].includes(gu)) {
      region = '인천';
    } else {
      region = '경기';
    }
  }

  const clean = (s: string) => s.replace(/[^A-Za-z0-9_\uAC00-\uD7A3]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  const idPrefix = id.startsWith('offi-') || id.startsWith('apt-') ? '' : 'a';
  const slug = `${clean(region)}-${clean(gu)}-${clean(dong)}-${clean(name)}-${idPrefix}${clean(id)}`;
  return slug.replace(/-+/g, '-').replace(/^-|-$/g, '');
}

function makeDongSlug(gu: string, dong: string, address: string): string {
  const METRO: Record<string, string> = {
    '서울특별시':'서울','인천광역시':'인천','부산광역시':'부산',
    '대구광역시':'대구','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산',
  };
  const PROVINCE: Record<string, string> = {'경기도':'경기','충청남도':'충남','충청북도':'충북','전라남도':'전남','전라북도':'전북','경상남도':'경남','경상북도':'경북','강원특별자치도':'강원','제주특별자치도':'제주'};

  const addrParts = (address || '').split(' ');
  const rawRegion = addrParts[0] || '';
  let region = '';
  if (METRO[rawRegion]) {
    region = METRO[rawRegion];
  } else if (PROVINCE[rawRegion]) {
    region = PROVINCE[rawRegion];
  } else {
    if (['종로구','중구','용산구','성동구','광진구','동대문구','중랑구','성북구','강북구','도봉구','노원구','은평구','서대문구','마포구','양천구','강서구','구로구','금천구','영등포구','동작구','관악구','서초구','강남구','송파구','강동구'].includes(gu)) {
      region = '서울';
    } else if (['중구','동구','미추홀구','연수구','남동구','부평구','계양구','서구','강화군','옹진군'].includes(gu)) {
      region = '인천';
    } else {
      region = '경기';
    }
  }

  let guClean = gu;
  if (region === '경기') {
    const addrGu = addrParts[1] || '';
    if (addrGu.endsWith('시') || addrGu.endsWith('군')) {
      guClean = addrGu;
      if (guClean !== gu) guClean = gu;
    }
  }

  const clean = (s: string) => s.replace(/[^A-Za-z0-9_\uAC00-\uD7A3]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  const slug = `${clean(region)}-${clean(guClean)}-${clean(dong)}`;
  return slug.replace(/-+/g, '-').replace(/^-|-$/g, '');
}

Deno.serve(async (req) => {
  const headers = {
    'Content-Type': 'application/xml',
    'Access-Control-Allow-Origin': 'https://hwik.kr',
    'Cache-Control': 'public, max-age=3600',
  };

  try {
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    const escXml = (s: string) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');

    async function fetchAll(table: string, select: string, filters: [string, string][] = []) {
      const all: any[] = [];
      let offset = 0;
      const limit = 1000;
      while (true) {
        let q = supabase.from(table).select(select).order('id' as any, { ascending: true }).range(offset, offset + limit - 1);
        for (const f of filters) q = q.neq(f[0], f[1]);
        const { data } = await q;
        if (!data || data.length === 0) break;
        all.push(...data);
        offset += limit;
        if (data.length < limit) break;
      }
      return all;
    }

    // 단지 페이지 (slug URL)
    const danjiPages = await fetchAll('danji_pages', 'id, complex_name, location, address, updated_at, categories, recent_trade');

    let urls = '';

    // 정적 페이지
    urls += `
  <url>
    <loc>${BASE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${BASE_URL}/gu.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>${BASE_URL}/ranking.html</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>`;

    // 단지 페이지 — slug URL + priority/changefreq
    const dongTradeCount: Record<string, number> = {};
    const dongAddrCache: Record<string, string> = {};

    (danjiPages || []).forEach(page => {
      const id = page.id || '';
      if (!id) return;
      const rt = page.recent_trade || {};
      const cats = page.categories || [];
      const hasTrade = cats.some((c: string) => rt[c]);
      if (!hasTrade) return;

      const slug = makeSlug(page.complex_name || '', page.location || '', id, page.address || '');
      const lastmod = page.updated_at ? new Date(page.updated_at).toISOString().split('T')[0] : '';

      urls += `
  <url>
    <loc>${BASE_URL}/danji/${encodeURIComponent(slug)}</loc>
    ${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>`;

      // dong 집계
      const locParts = (page.location || '').split(' ', 2);
      if (locParts.length >= 2) {
        const key = `${locParts[0]}|${locParts[1]}`;
        dongTradeCount[key] = (dongTradeCount[key] || 0) + 1;
        if (!dongAddrCache[key]) dongAddrCache[key] = page.address || '';
      }
    });

    // 동 페이지 — slug URL
    for (const [key, cnt] of Object.entries(dongTradeCount)) {
      if (cnt < 3) continue;
      const [gu, dong] = key.split('|');
      const addr = dongAddrCache[key] || '';
      const dongSlug = makeDongSlug(gu, dong, addr);
      urls += `
  <url>
    <loc>${BASE_URL}/dong/${encodeURIComponent(dongSlug)}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>`;
    }

    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>`;

    return new Response(xml, { headers });
  } catch (error: any) {
    console.error('Sitemap error:', error.message);
    return new Response(`<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>${BASE_URL}/</loc><priority>1.0</priority></url>
</urlset>`, { headers });
  }
});
