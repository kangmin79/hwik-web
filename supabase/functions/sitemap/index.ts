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

    // 공개 매물만 조회 (trade_status가 '완료'가 아닌 것)
    const { data: cards, error } = await supabase
      .from('cards')
      .select('id, created_at, trade_status')
      .neq('trade_status', '완료')
      .neq('property->>type', '손님')
      .order('created_at', { ascending: false })
      .limit(5000);

    if (error) throw error;

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

    // 매물 페이지
    (cards || []).forEach(card => {
      const lastmod = card.created_at ? new Date(card.created_at).toISOString().split('T')[0] : '';

      urls += `
  <url>
    <loc>${BASE_URL}/property_view.html?id=${card.id}</loc>
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
