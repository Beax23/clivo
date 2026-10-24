{% load static %}
/* =============================================================
   Clivo — Service Worker
   Cache offline-first para o shell do PWA.
   NÃO intercepta chamadas de API (/api/*).
   ============================================================= */

const CACHE_NAME = 'clivo-portal-v1';

// Assets estáticos que podem ser cacheados com segurança.
const PRECACHE_URLS = [
    '{% static "manifest.json" %}',
    '{% static "icons/icon-192.png" %}',
    '{% static "icons/icon-512.png" %}',
];

// =============================================================
// INSTALL — pré-carrega o que for seguro
// =============================================================
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                return Promise.all(
                    PRECACHE_URLS.map((url) =>
                        cache.add(url).catch((err) => {
                            console.warn('[sw] Falha ao cachear:', url, err);
                        })
                    )
                );
            })
            .then(() => self.skipWaiting())
            .catch((err) => {
                console.warn('[sw] Falha no precache:', err);
            })
    );
});

// =============================================================
// ACTIVATE — limpa caches antigos
// =============================================================
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) =>
                Promise.all(
                    keys
                        .filter((k) => k !== CACHE_NAME)
                        .map((k) => caches.delete(k))
                )
            )
            .then(() => self.clients.claim())
    );
});

// =============================================================
// FETCH — estratégias por tipo
// - /api/*    → NUNCA cacheia. Direto pra rede.
// - /static/* → cache-first (atualiza em background)
// - navigate  → network-first (fallback pro cache)
// =============================================================
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    if (url.origin !== self.location.origin) return;
    if (request.method !== 'GET') return;

    // 1) APIs → só rede
    if (url.pathname.startsWith('/api/')) {
        return;
    }

    // 2) Assets estáticos → cache-first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) {
                    fetch(request)
                        .then((fresh) => {
                            if (fresh && fresh.status === 200) {
                                caches.open(CACHE_NAME).then((cache) => {
                                    cache.put(request, fresh.clone()).catch(() => {});
                                });
                            }
                        })
                        .catch(() => {});
                    return cached;
                }
                return fetch(request).then((fresh) => {
                    if (fresh && fresh.status === 200) {
                        const copy = fresh.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, copy).catch(() => {});
                        });
                    }
                    return fresh;
                });
            })
        );
        return;
    }

    // 3) Navegação (HTML) → network-first
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    if (response && response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, copy).catch(() => {});
                        });
                    }
                    return response;
                })
                .catch(() => {
                    return caches.match(request).then((cached) => {
                        if (cached) return cached;

                        return new Response(
                            '<!DOCTYPE html><html lang="pt-BR"><head>' +
                            '<meta charset="UTF-8">' +
                            '<meta name="viewport" content="width=device-width, initial-scale=1">' +
                            '<title>Offline · Clivo</title>' +
                            '<style>' +
                            'body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;' +
                            'display:flex;align-items:center;justify-content:center;' +
                            'min-height:100vh;margin:0;background:#0A0A0A;color:#F5F5F5;' +
                            'text-align:center;padding:24px}' +
                            'h1{font-size:20px;font-weight:700;margin:0 0 8px}' +
                            'p{color:#9797A1;font-size:14px;margin:0}' +
                            '</style></head><body><div>' +
                            '<h1>Você está offline</h1>' +
                            '<p>Verifique sua conexão e tente novamente.</p>' +
                            '</div></body></html>',
                            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                        );
                    });
                })
        );
        return;
    }
});

// =============================================================
// MESSAGE — permite forçar skipWaiting
// =============================================================
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});