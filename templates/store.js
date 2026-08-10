/* ============================================================
   vTube — shared client store (Vue 3 global build, no bundler)

   Loaded by every page AFTER vue.global.js AND videos.js. Provides
   window.VTube: the video catalog (from window.VTubeData, defined by
   videos.js), the localStorage-backed watch-history / favorites store,
   and small singletons (ui, videos) shared across the several Vue apps
   mounted on one page (header, page content, and the standalone
   "My library" panel, both defined in base.html).

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

  /* ---------- video catalog (static; provided by videos.js as window.VTubeData) ---------- */
  const videos = { list: (global.VTubeData && global.VTubeData.videos) || [] };
  /* precomputed facets: [name, count] pairs sorted by count desc, mapped to { name, count } */
  const categories = ((global.VTubeData && global.VTubeData.categories) || []).map(c => ({ name: c[0], count: c[1] }));
  const tags = ((global.VTubeData && global.VTubeData.tags) || []).map(t => ({ name: t[0], count: t[1] }));
  /* name -> count lookups over those facets */
  const categoryCountMap = new Map(categories.map(c => [c.name, c.count]));
  const tagCountMap = new Map(tags.map(t => [t.name, t.count]));
  const categoryCount = (name) => categoryCountMap.get(name) || 0;
  const tagCount = (name) => tagCountMap.get(name) || 0;
  /* id -> video lookup, and precomputed suggestions (video id -> [suggested id, ...]) */
  const byId = new Map(videos.list.map(v => [v.id, v]));
  const getVideo = (id) => byId.get(id) || null;
  const suggestions = (global.VTubeData && global.VTubeData.suggestions) || {};
  const suggestionsFor = (id) => (suggestions[id] || []).map(sid => byId.get(sid)).filter(Boolean);

  /* one-time cleanup: drop history/favorite entries whose video is no longer in
     the catalog and persist the pruned list, so counts (e.g. "7/10") never
     include dead ids. Runs at load, before any app reads the store. */
  function pruneStoredIds(key) {
    const list = readList(key);
    const clean = list.filter(e => byId.has(e.id));
    if (clean.length !== list.length) writeList(key, clean);
  }
  pruneStoredIds(KEY_HISTORY);
  pruneStoredIds(KEY_FAVORITE);

  /* ---------- asset URL resolvers ----------
     videos.js stores relative paths plus a cdn base ({ video, image }); these
     join them into absolute URLs. thumbUrl falls back to LIST_THUMB when a
     video has no thumbnail. All are null-safe so templates can pass a
     possibly-absent nowPlaying. */
  const cdn = (global.VTubeData && global.VTubeData.cdn) || '';
  const videoSrc = (v) => v ? cdn + v.url : '';
  const posterUrl = (v) => v ? cdn + v.poster : '';
  const thumbsUrl = (v) => v ? cdn + v.thumbs : '';
  const thumbUrl = (v) => (v && v.thumb) ? cdn + v.thumb : LIST_THUMB;

  /* ---------- shared UI state (library panel open/collapsed) ---------- */
  const ui = Vue.reactive({ libraryOpen: true, historyOpen: true });

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
