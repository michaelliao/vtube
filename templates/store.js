/* ============================================================
   vTube — shared client store (Vue 3 global build, no bundler)

   Loaded by every page AFTER vue.global.js. Provides window.VTube: the
   localStorage-backed watch-history / favorites store, and the video
   catalog which is fetched at runtime by VTube.load() from the CDN
   ('remote_url' in localStorage, else a default) into window.VTubeData.
   Apps await VTube.load() before mounting so setup() sees a populated
   catalog. The ui/videos singletons are shared across the several Vue
   apps on a page (header, page content, and the "My library" panel).

   localStorage keys (client-only, never sent to the server):
     vtube_history   [{ id, at, progress }] newest first, max 10 (FIFO)
     vtube_favorite  [{ id, at }]           newest first, max 10 (add refused when full)
     vtube_player    { volume, muted }      last-used player settings (via getPlayer/setPlayer)

   Cross-tab / same-tab sync:
     The browser fires a 'storage' event in OTHER tabs whenever a key
     changes — but NOT in the tab that made the write. So writeList()
     dispatches a synthetic 'storage' event too, letting every app on
     the CURRENT tab react through the same listener. Subscribe with
     VTube.subscribe(cb) and re-read via VTube.getHistory/getFavorites.
   ============================================================ */
(function (global) {
  const Vue = global.Vue;

  const KEY_HISTORY = 'vtube_history';
  const KEY_FAVORITE = 'vtube_favorite';
  const KEY_PLAYER = 'vtube_player';
  const KEY_LIBRARY = 'vtube_library';
  const KEY_REMOTE = 'remote_url';
  const KEY_REMOTE_LIST = 'remote_url_list';
  const HISTORY_MAX = 10;
  const FAVORITES_MAX = 10;

  /* fallback thumbnail for list cards */
  const LIST_THUMB = 'about:blank';

  /* ---------- localStorage list I/O ---------- */
  function readList(key) {
    try {
      const list = JSON.parse(localStorage.getItem(key) || '[]');
      return Array.isArray(list) ? list : [];
    } catch (err) { return []; }
  }
  function writeList(key, list) {
    const newValue = JSON.stringify(list);
    try { localStorage.setItem(key, newValue); } catch (err) { }
    // The native 'storage' event never fires in the tab that wrote the
    // value, so dispatch a synthetic one to sync this tab's other apps.
    try {
      global.dispatchEvent(new StorageEvent('storage', { key: key, newValue: newValue }));
    } catch (err) {
      global.dispatchEvent(new Event('storage'));
    }
  }

  /* ---------- watch history ---------- */
  const getHistory = () => readList(KEY_HISTORY);
  function addHistory(id, progress) {
    const list = getHistory().filter(e => e.id !== id);   // re-watch moves to front
    list.unshift({ id: id, at: Date.now(), progress: progress || 0 });
    if (list.length > HISTORY_MAX) list.length = HISTORY_MAX;  // FIFO cap
    writeList(KEY_HISTORY, list);
  }
  function setProgress(id, progress) {
    const list = getHistory();
    const entry = list.find(e => e.id === id);
    if (!entry) return addHistory(id, progress);
    entry.progress = progress;
    entry.at = Date.now();
    writeList(KEY_HISTORY, list);
  }
  const clearHistory = () => writeList(KEY_HISTORY, []);

  /* ---------- favorites ---------- */
  const getFavorites = () => readList(KEY_FAVORITE);
  const isFavorite = (id) => getFavorites().some(e => e.id === id);
  function addFavorite(id) {
    const list = getFavorites();
    if (list.some(e => e.id === id)) return { ok: true, reason: 'already-favorite' };
    if (list.length >= FAVORITES_MAX) return { ok: false, reason: 'full' };
    writeList(KEY_FAVORITE, [{ id: id, at: Date.now() }].concat(list));
    return { ok: true };
  }
  function removeFavorite(id) {
    writeList(KEY_FAVORITE, getFavorites().filter(e => e.id !== id));
    return { ok: true };
  }
  function toggleFavorite(id) {
    if (isFavorite(id)) { removeFavorite(id); return { ok: true, removed: true }; }
    return addFavorite(id);
  }

  /* ---------- player preferences (volume / mute), persisted as one object ---------- */
  function getPlayer() {
    try {
      const p = JSON.parse(localStorage.getItem(KEY_PLAYER) || '{}');
      return {
        volume: typeof p.volume === 'number' ? Math.min(1, Math.max(0, p.volume)) : 1,
        muted: !!p.muted
      };
    } catch (err) { return { volume: 1, muted: false }; }
  }
  function setPlayer(prefs) {
    try {
      localStorage.setItem(KEY_PLAYER, JSON.stringify({ volume: prefs.volume, muted: prefs.muted }));
    } catch (err) { }
  }

  /* ---------- change subscription (this tab's writes + other tabs) ---------- */
  function subscribe(cb) {
    const handler = (e) => {
      if (!e.key || e.key === KEY_HISTORY || e.key === KEY_FAVORITE) cb(e.key);
    };
    global.addEventListener('storage', handler);
    return () => global.removeEventListener('storage', handler);
  }

  /* ---------- video catalog (fetched from the CDN at runtime by load()) ----------
     Not available until load() resolves, so apps mount only after S.load().
     videos/categories/tags are exported by reference and mutated in place;
     the Maps/cdn are closed over by the helpers below and reassigned on load. */
  const videos = { list: [] };
  const categories = [];   // { name, count }, sorted by count desc
  const tags = [];         // { name, count }, sorted by count desc
  let cdn = '';
  let byId = new Map();
  let suggestions = {};     // video id -> [suggested id, ...]
  let categoryCountMap = new Map();
  let tagCountMap = new Map();

  const categoryCount = (name) => categoryCountMap.get(name) || 0;
  const tagCount = (name) => tagCountMap.get(name) || 0;
  const getVideo = (id) => byId.get(id) || null;
  const suggestionsFor = (id) => (suggestions[id] || []).map(sid => byId.get(sid)).filter(Boolean);

  /* asset URL resolvers: join the cdn base with a video's relative path;
     thumbUrl falls back to LIST_THUMB. All null-safe (a template may pass a
     possibly-absent video). */
  const videoSrc = (v) => v ? cdn + v.url : '';
  const posterUrl = (v) => v ? cdn + v.poster : '';
  const thumbsUrl = (v) => v ? cdn + v.thumbs : '';
  const thumbUrl = (v) => (v && v.thumb) ? cdn + v.thumb : LIST_THUMB;

  /* drop history/favorite entries whose video is no longer in the catalog and
     persist the pruned list, so counts (e.g. "7/10") never include dead ids. */
  function pruneStoredIds(key) {
    const list = readList(key);
    const clean = list.filter(e => byId.has(e.id));
    if (clean.length !== list.length) writeList(key, clean);
  }

  /* populate the catalog state from a fetched videos.json. `base` (the
     remote_url) is used as the asset cdn when the payload omits an absolute one. */
  function applyData(data, base) {
    cdn = data.cdn || base;
    videos.list = data.videos || [];
    categories.splice(0, categories.length, ...((data.categories || []).map(c => ({ name: c[0], count: c[1] }))));
    tags.splice(0, tags.length, ...((data.tags || []).map(t => ({ name: t[0], count: t[1] }))));
    categoryCountMap = new Map(categories.map(c => [c.name, c.count]));
    tagCountMap = new Map(tags.map(t => [t.name, t.count]));
    byId = new Map(videos.list.map(v => [v.id, v]));
    suggestions = data.suggestions || {};
    pruneStoredIds(KEY_HISTORY);
    pruneStoredIds(KEY_FAVORITE);
  }

  /* fetch the catalog once (memoized). The CDN base is the 'remote_url'
     localStorage key, else a default test CDN. Apps await this before mount. */
  const DEFAULT_REMOTE = 'https://cdn.vtube.puppylab.org/featured-videos/';
  /* the effective CDN base: the 'remote_url' localStorage override, else the default */
  function getRemoteUrl() {
    try { return localStorage.getItem(KEY_REMOTE) || DEFAULT_REMOTE; } catch (err) { return DEFAULT_REMOTE; }
  }
  /* the known remote_url list (history). When nothing is stored yet, seed it
     with [DEFAULT] AND persist it, so the default survives a later setRemoteUrl. */
  function getRemoteUrlList() {
    try {
      const list = JSON.parse(localStorage.getItem(KEY_REMOTE_LIST) || '[]');
      if (Array.isArray(list) && list.length) return list;
    } catch (err) { }
    setRemoteUrlList([DEFAULT_REMOTE]);
    return [DEFAULT_REMOTE];
  }
  /* persist the list, keeping items unique (first occurrence wins) */
  function setRemoteUrlList(list) {
    const uniq = [];
    (list || []).forEach(u => { if (u && uniq.indexOf(u) === -1) uniq.push(u); });
    try { localStorage.setItem(KEY_REMOTE_LIST, JSON.stringify(uniq)); } catch (err) { }
  }
  function setRemoteUrl(url) {
    try { localStorage.setItem(KEY_REMOTE, url); } catch (err) { }
    setRemoteUrlList([url].concat(getRemoteUrlList()));   // record in history (front, unique)
  }
  /* reveal the plain (non-Vue) #error-app banner in base.html on load failure */
  function showLoadError(url) {
    const box = global.document && global.document.getElementById('error-app');
    if (!box) return;
    const msg = box.querySelector('.error-message');
    if (msg) msg.textContent = 'Failed load video source from ' + url;
    box.style.display = '';
  }
  let loadPromise = null;
  function load() {
    if (!loadPromise) {
      const remoteUrl = getRemoteUrl();
      loadPromise = (async () => {
        console.log('vTube: loading catalog from remote_url =', remoteUrl);
        const res = await fetch(remoteUrl + 'videos.json');
        if (!res.ok) throw new Error('vTube: HTTP ' + res.status + ' fetching ' + remoteUrl + 'videos.json');
        const data = await res.json();
        global.VTubeData = data;
        applyData(data, remoteUrl);
        return data;
      })().catch((err) => {
        showLoadError(remoteUrl);   // show the error banner
        throw err;                  // keep the promise rejected so apps skip mounting
      });
    }
    return loadPromise;
  }

  /* ---------- shared UI state (library panel open/collapsed) ----------
     libraryOpen is persisted (defaults to open on first visit); libraryReady
     flips true once the (async-mounted) library app is up, so the header's
     Library button can stay hidden until the panel actually exists. */
  function readLibraryOpen() {
    try {
      const v = localStorage.getItem(KEY_LIBRARY);
      return v === null ? true : v === 'true';
    } catch (err) { return true; }
  }
  const ui = Vue.reactive({ libraryOpen: readLibraryOpen(), historyOpen: true, libraryReady: false });
  Vue.watch(() => ui.libraryOpen, (open) => {
    try { localStorage.setItem(KEY_LIBRARY, open ? 'true' : 'false'); } catch (err) { }
  });

  /* ---------- formatting helpers ---------- */
  function fmt(sec) {
    const s = Math.max(0, Math.round(sec || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(ss).padStart(2, '0');
  }
  function relative(ts) {
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return mins + ' min ago';
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
    const days = Math.round(hrs / 24);
    return days === 1 ? 'Yesterday' : days + ' days ago';
  }

  global.VTube = {
    KEY_HISTORY: KEY_HISTORY, KEY_FAVORITE: KEY_FAVORITE,
    HISTORY_MAX: HISTORY_MAX, FAVORITES_MAX: FAVORITES_MAX,
    load: load, getRemoteUrl: getRemoteUrl, setRemoteUrl: setRemoteUrl,
    getRemoteUrlList: getRemoteUrlList, setRemoteUrlList: setRemoteUrlList,
    videos: videos, categories: categories, tags: tags, ui: ui,
    categoryCount: categoryCount, tagCount: tagCount,
    getVideo: getVideo, suggestionsFor: suggestionsFor,
    videoSrc: videoSrc, posterUrl: posterUrl, thumbsUrl: thumbsUrl, thumbUrl: thumbUrl,
    getHistory: getHistory, addHistory: addHistory, setProgress: setProgress, clearHistory: clearHistory,
    getFavorites: getFavorites, isFavorite: isFavorite,
    addFavorite: addFavorite, removeFavorite: removeFavorite, toggleFavorite: toggleFavorite,
    getPlayer: getPlayer, setPlayer: setPlayer,
    subscribe: subscribe, fmt: fmt, relative: relative
  };
})(window);
