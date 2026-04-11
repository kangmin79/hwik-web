// Supabase 표준 인증 — auth.getUser()로 검증
// 내부 서비스 간 호출(telegram-webhook 등)은 x-hwik-internal 시크릿 + x-agent-id 헤더로 bypass
import { createClient } from 'jsr:@supabase/supabase-js@2'

export async function getAuthUserId(req: Request): Promise<string | null> {
  // 내부 서비스 bypass: HWIK_INTERNAL_SECRET 시크릿 일치 + x-agent-id 헤더로 유저 ID 전달
  const internalSecret = Deno.env.get('HWIK_INTERNAL_SECRET') || '';
  const internalHeader = req.headers.get('x-hwik-internal') || '';
  if (internalSecret.length > 0 && internalHeader === internalSecret) {
    const agentId = req.headers.get('x-agent-id');
    if (agentId) return agentId;
  }

  const authHeader = req.headers.get('authorization') || '';
  const token = authHeader.replace('Bearer ', '');
  if (!token) return null;

  try {
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY')!;
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: `Bearer ${token}` } }
    });
    const { data: { user }, error } = await supabase.auth.getUser(token);
    if (error || !user) return null;
    return user.id;
  } catch {
    return null;
  }
}
