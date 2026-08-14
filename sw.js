/* v4.1: index.html と mobile_data.json は network-first（更新が即届く）。
   それ以外（アイコン等）は cache-first。オフライン時は常にキャッシュへフォールバック。
   ※旧v4-0は全部cache-firstで、更新が届かず「アプリを1〜2回開き直す」必要があった。 */
const CACHE = "ht-v4-1";
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icon.svg", "./mobile_data.json"];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      // 個別にadd＝mobile_data.jsonが未公開(404)でもインストールを失敗させない
      .then(c => Promise.all(ASSETS.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isFresh(req) {
  if (req.mode === "navigate") return true;                 // ページ本体
  const p = new URL(req.url).pathname;
  return p.endsWith("/") || p.endsWith("index.html") || p.endsWith("mobile_data.json");
}

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  // 公開データはネット優先＋キャッシュ鍵を正規化（アプリ側が ?t=... を付けるため）
  if (new URL(e.request.url).pathname.endsWith("mobile_data.json")) {
    e.respondWith(
      fetch(e.request).then(resp => {
        const cp = resp.clone();
        caches.open(CACHE).then(c => c.put("./mobile_data.json", cp));
        return resp;
      }).catch(() => caches.match("./mobile_data.json"))
    );
    return;
  }
  if (isFresh(e.request)) {
    // network-first：取れたらキャッシュ更新、ダメならキャッシュ（最後はindex.html）
    e.respondWith(
      fetch(e.request).then(resp => {
        const cp = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, cp));
        return resp;
      }).catch(() => caches.match(e.request).then(r => r || caches.match("./index.html")))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      const cp = resp.clone();
      caches.open(CACHE).then(c => c.put(e.request, cp));
      return resp;
    }).catch(() => caches.match("./index.html")))
  );
});
