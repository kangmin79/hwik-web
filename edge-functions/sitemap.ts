import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const BASE_URL = 'https://hwik.kr';

Deno.serve(async (req) => {
  const headers = {
    'Content-Type': 'application/xml',
    'Access-Control-Allow-Origin': 'https://hwik.kr',
    'Cache-Control': 'public, max-age=3600', // 1시간 캐시
  };

  try {
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    // XML 특수문자 이스케이프
    const escXml = (s: string) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');

    // 페이지네이션으로 전체 데이터 가져오기
    async function fetchAll(table: string, select: string, filters: any[] = []) {
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

    // 공개 매물 (손님 제외, 완료 제외)
    const cards = await fetchAll('cards', 'id, created_at', [['trade_status', '완료'], ['property->>type', '손님']]);

    // 단지 페이지 전체
    const danjiPages = await fetchAll('danji_pages', 'id, updated_at');

    let urls = '';

    // 정적 페이지
    urls += `
  <url>
    <loc>${BASE_URL}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${BASE_URL}/llms.txt</loc>
    <changefreq>weekly</changefreq>
    <priority>0.3</priority>
  </url>`;

    // 단지 페이지
    (danjiPages || []).forEach(page => {
      const lastmod = page.updated_at ? new Date(page.updated_at).toISOString().split('T')[0] : '';

      urls += `
  <url>
    <loc>${BASE_URL}/danji.html?id=${escXml(page.id)}</loc>
    ${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>`;
    });

    // 매물 페이지
    (cards || []).forEach(card => {
      const lastmod = card.created_at ? new Date(card.created_at).toISOString().split('T')[0] : '';

      urls += `
  <url>
    <loc>${BASE_URL}/property_view.html?id=${escXml(card.id)}</loc>
    ${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>`;
    });

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
