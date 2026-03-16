// 휙 서비스워커 — network first 전략
// 버전 바꾸면 캐시 전체 교체됨
const CACHE_VERSION = 'hwik-v1';

const CACHE_FILES = [
  '/hwik-web/mobile-v6.html',
  '/hwik-web/config.js',
  '/hwik-web/manifest.json',
  '/hwik-web/icon-192.png',
  '/hwik-web/icon-512.png',
];

// ── 설치: 핵심 파일 캐시 ──
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_VERSION).then(cache => cache.addAll(CACHE_FILES))
  );
  // 기존 워커 기다리지 않고 즉시 활성화
  self.skipWaiting();
});

// ── 활성화: 이전 버전 캐시 삭제 ──
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k))
      )
    )
  );
  // 열려있는 모든 탭에 즉시 적용
  self.clients.claim();
});

// ── fetch: network first (항상 최신 버전 우선) ──
self.addEventListener('fetch', (e) => {
  // Supabase API, 외부 리소스는 서비스워커 통하지 않음
  const url = new URL(e.request.url);
  if (
    url.origin !== self.location.origin ||
    e.request.method !== 'GET'
  ) return;

  e.respondWith(
    fetch(e.request)
      .then(response => {
        // 네트워크 성공 → 캐시 갱신 후 반환
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_VERSION).then(cache => cache.put(e.request, clone));
        }
        return response;
      })
      .catch(() => {
        // 오프라인 → 캐시에서 반환
        return caches.match(e.request);
      })
  );
});

// ── 업데이트 감지 → 클라이언트에 알림 ──
self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});
