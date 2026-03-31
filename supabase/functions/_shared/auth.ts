// JWT에서 인증된 user_id 추출
// Supabase Edge Function에서 사용
export function getAuthUserId(req: Request): string | null {
  const authHeader = req.headers.get('authorization') || '';
  const token = authHeader.replace('Bearer ', '');
  if (!token) return null;
  try {
    // JWT payload 디코딩 (Base64)
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload.sub || null;
  } catch {
    return null;
  }
}
