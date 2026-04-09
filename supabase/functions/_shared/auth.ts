// JWT에서 인증된 user_id 추출 + 서명 검증
// Supabase Edge Function에서 사용
function base64UrlDecode(str: string): Uint8Array {
  const b64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const pad = b64.length % 4 === 0 ? '' : '='.repeat(4 - (b64.length % 4));
  const bin = atob(b64 + pad);
  return Uint8Array.from(bin, c => c.charCodeAt(0));
}

export async function getAuthUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get('authorization') || '';
  const token = authHeader.replace('Bearer ', '');
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;

    // JWT 서명 검증 (HMAC-SHA256)
    const jwtSecret = Deno.env.get('JWT_SECRET');
    if (jwtSecret) {
      const encoder = new TextEncoder();
      const key = await crypto.subtle.importKey(
        'raw', encoder.encode(jwtSecret),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
      );
      const signature = base64UrlDecode(parts[2]);
      const data = encoder.encode(`${parts[0]}.${parts[1]}`);
      const valid = await crypto.subtle.verify('HMAC', key, signature, data);
      if (!valid) {
        console.warn('JWT 서명 검증 실패');
        return null;
      }
    }

    // payload 디코딩
    const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));

    // 만료 체크
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      console.warn('JWT 만료됨');
      return null;
    }

    return payload.sub || null;
  } catch {
    return null;
  }
}
