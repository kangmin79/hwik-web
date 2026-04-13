// 휙 서비스워커 — cache first (앱 셸) + network first (API)
const CACHE_VERSION = 'hwik-v4';

const CACHE_FILES = [
  'mobile.html',
  'manifest.json',
  'icon-192.png',
  'icon-512.png',
  'icon-180.png',
  'icon-152.png',
  'icon-120.png',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js',
  'https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap',
];

// ── 설치: 핵심 파일 캐시 ──
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_VERSION).then(cache =>
      cache.addAll(CACHE_FILES.map(url => new Request(url, { cache: 'reload' })))
        .catch(() => cache.addAll(['mobile.html', 'manifest.json']))
    )
  );
  self.skipWaiting();
});

// ── 활성화: 이전 버전 캐시 삭제 ──
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── fetch 전략 ──
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Supabase API, POST 요청 → 서비스워커 통하지 않음
  if (e.request.method !== 'GET') return;
  if (url.hostname.includes('supabase.co')) return;
  if (url.hostname.includes('api.telegram.org')) return;
  if (url.hostname.includes('dapi.kakao.com')) return;

  // 앱 셸 (mobile.html, 아이콘, manifest) → cache first + 백그라운드 갱신
  const isShell = url.origin === self.location.origin || url.hostname.includes('jsdelivr.net');

  if (isShell) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        const networkFetch = fetch(e.request).then(response => {
          if (response && response.status === 200) {
            caches.open(CACHE_VERSION).then(cache => cache.put(e.request, response.clone()));
          }
          return response;
        }).catch(() => null);

        // 캐시 있으면 즉시 반환 (stale-while-revalidate)
        return cached || networkFetch;
      })
    );
    return;
  }

  // 나머지 → network first
  e.respondWith(
    fetch(e.request)
      .then(response => {
        if (response && response.status === 200) {
          caches.open(CACHE_VERSION).then(cache => cache.put(e.request, response.clone()));
        }
        return response;
      })
      .catch(() => caches.match(e.request))
  );
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});
