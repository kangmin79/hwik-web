// Supabase 인증 — Auth API 직접 호출 (ES256 JWT 호환)
// 내부 서비스 bypass: x-hwik-internal + x-agent-id 헤더

export async function getAuthUserId(req: Request): Promise<string | null> {
  const internalSecret = Deno.env.get('HWIK_INTERNAL_SECRET') || '';
  const internalHeader = req.headers.get('x-hwik-internal') || '';
  if (internalSecret.length > 0 && internalHeader === internalSecret) {
    const agentId = req.headers.get('x-agent-id');
    if (agentId) return agentId;
  }

  const authHeader = req.headers.get('authorization') || req.headers.get('Authorization') || '';
  const token = authHeader.replace('Bearer ', '');
  if (!token) return null;

  try {
    // ★ supabase-js getUser() ES256 검증 실패 우회 → Auth API 직접 호출
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY') || Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
      headers: { 'Authorization': `Bearer ${token}`, 'apikey': SUPABASE_ANON_KEY },
    });
    if (!r.ok) return null;
    const user = await r.json();
    return user?.id || null;
  } catch {
    return null;
  }
}
