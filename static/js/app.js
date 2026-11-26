/* AnimeKite — vanilla ES6 UI: instant catalog, search, filters, modal, watchlist. */
(() => {
  'use strict';

  const STORAGE_KEY = 'animekite.watchlist.v1';
  const initial = JSON.parse(document.getElementById('initial-data').textContent || '{}');

  const grid = document.getElementById('grid');
  const statusEl = document.getElementById('status');
  const searchEl = document.getElementById('search');
  const watchlistToggle = document.getElementById('watchlist-toggle');
  const watchlistCount = document.getElementById('watchlist-count');
  const modal = document.getElementById('modal');
  const player = document.getElementById('modal-player');
  const playerNote = document.getElementById('player-note');
  const modalTitle = document.getElementById('modal-title');
  const modalMeta = document.getElementById('modal-meta');
  const modalSynopsis = document.getElementById('modal-synopsis');
  const modalLicence = document.getElementById('modal-licence');
  const modalWatchlist = document.getElementById('modal-watchlist');
  const officialLink = document.getElementById('official-link');
  const detailsLink = document.getElementById('details-link');

  const state = {
    category: 'all',
    query: '',
    items: [],
    current: null,
    requestId: 0,
    watchlist: loadWatchlist()
  };

  function loadWatchlist() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      return saved && typeof saved === 'object' ? saved : {};
    } catch (_) {
      return {};
    }
  }

  function saveWatchlist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.watchlist));
    } catch (_) {
      /* Private browsing may block storage; session use still works. */
    }
  }

  function watchKey(item) {
    return item.id ? `id:${item.id}` : `title:${item.title.toLowerCase()}`;
  }

  function isSaved(item) {
    return Object.prototype.hasOwnProperty.call(state.watchlist, watchKey(item));
  }

  function updateWatchlistUI() {
    watchlistCount.textContent = String(Object.keys(state.watchlist).length);
    watchlistToggle.setAttribute('aria-pressed', String(state.category === 'watchlist'));
    if (state.current) {
      modalWatchlist.textContent = isSaved(state.current) ? 'Remove from Watchlist' : 'Add to Watchlist';
    }
  }

  function normalise(raw) {
    const studios = raw.studios || (raw.studio ? [raw.studio] : []);
    return {
      id: raw.id || null,
      title: raw.title || 'Untitled',
      image: raw.image || '/static/images/poster_placeholder.svg',
      poster_source: raw.poster_source || 'local',
      score: raw.score || null,
      episodes: raw.episodes || null,
      synopsis: raw.synopsis || '',
      studios: studios,
      year: raw.year || '',
      type: raw.type || '',
      url: raw.url || '',
      trailer_id: raw.trailer_id || '',
      jikan_query: raw.jikan_query || raw.title || '',
      badge: raw.badge || '',
      hindi_dub: Boolean(raw.hindi_dub),
      embed_url: raw.embed_url || '',
      official_url: raw.official_url || '',
      channel: raw.channel || '',
      licence_note: raw.licence_note || ''
    };
  }

  function shortMeta(item) {
    return [item.year, item.episodes ? `${item.episodes} eps` : '', item.studios[0]]
      .filter(Boolean).join(' • ');
  }

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function makeCard(item) {
    const card = document.createElement('article');
    card.className = 'card';
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `Open details for ${item.title}`);

    const posterWrap = document.createElement('div');
    posterWrap.className = 'poster-wrap';
    const img = document.createElement('img');
    img.className = 'poster';
    img.src = item.image;
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.dataset.role = 'poster';
    posterWrap.appendChild(img);

    if (item.badge || item.hindi_dub) {
      const badge = document.createElement('span');
      badge.className = 'badge' + (item.hindi_dub ? '' : ' partner');
      badge.textContent = item.badge || 'HINDI DUB';
      posterWrap.appendChild(badge);
    }

    if (item.score) {
      const score = document.createElement('span');
      score.className = 'score';
      score.textContent = `★ ${Number(item.score).toFixed(1)}`;
      score.dataset.role = 'score';
      posterWrap.appendChild(score);
    }

    const body = document.createElement('div');
    body.className = 'card-body';
    const title = document.createElement('h3');
    title.className = 'card-title';
    title.textContent = item.title;
    const meta = document.createElement('p');
    meta.className = 'card-meta';
    meta.textContent = shortMeta(item) || 'Anime';
    body.append(title, meta);
    card.append(posterWrap, body);

    card.addEventListener('click', () => openModal(item));
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openModal(item);
      }
    });
    return card;
  }

  function render(items) {
    state.items = items;
    grid.replaceChildren(...items.map(makeCard));
  }

  function applyMetadata(data) {
    const item = state.current;
    if (!item || !data) return;
    item.image = data.image || item.image;
    item.score = data.score || item.score;
    item.synopsis = item.synopsis || data.synopsis || '';
    item.studios = item.studios.length ? item.studios : (data.studios || []);
    item.year = item.year || data.year || '';
    item.trailer_id = item.trailer_id || data.trailer_id || '';
    item.url = item.url || data.url || '';
    item.id = item.id || data.id || null;
    showDetails(item);
  }

  function enrichCurrent() {
    const item = state.current;
    if (!item || item.score || item.poster_source === 'jikan') return;
    fetch(`/api/metadata?q=${encodeURIComponent(item.jikan_query || item.title)}`)
      .then((response) => (response.ok ? response.json() : { data: null }))
      .then((payload) => applyMetadata(payload && payload.data))
      .catch(() => { /* Offline: local poster and synopsis are already shown. */ });
  }

  async function load() {
    const requestId = ++state.requestId;
    const query = state.query;
    const category = state.category;
    const url = query
      ? `/api/anime?q=${encodeURIComponent(query)}`
      : `/api/anime?category=${encodeURIComponent(category)}`;

    setStatus('Loading collection...');
    try {
      const response = await fetch(url, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (requestId !== state.requestId) return;
      let rows = Array.isArray(payload.data) ? payload.data : [];
      if (category === 'watchlist' && !query) {
        rows = Object.keys(state.watchlist).map((key) => state.watchlist[key]).filter(Boolean);
      }
      render(rows.map(normalise));
      setStatus(query
        ? `${rows.length} result${rows.length === 1 ? '' : 's'} for “${query}”`
        : `${rows.length} title${rows.length === 1 ? '' : 's'} loaded`);
    } catch (_) {
      if (requestId !== state.requestId) return;
      const cached = (initial.curated || []).map(normalise);
      const rows = query
        ? cached.filter((item) => item.title.toLowerCase().includes(query.toLowerCase()))
        : cached;
      render(rows);
      setStatus('Jikan unavailable — showing the built-in legal catalog.');
    }
  }

  function playerSource(item) {
    if (item.embed_url && item.embed_url.startsWith('https://www.youtube-nocookie.com/embed/')) {
      return { src: item.embed_url, note: 'Official stream embedded from the distributor’s YouTube channel.' };
    }
    if (item.trailer_id) {
      return {
        src: `https://www.youtube-nocookie.com/embed/${encodeURIComponent(item.trailer_id)}?rel=0`,
        note: 'Official trailer. Visit the official platform for the full episode.'
      };
    }
    return null;
  }

  function showDetails(item) {
    modalTitle.textContent = item.title;
    modalMeta.textContent = shortMeta(item) || (item.hindi_dub ? 'Free official Hindi dub' : '');
    modalSynopsis.textContent = item.synopsis || 'Synopsis not available right now.';
    modalLicence.textContent = item.licence_note || '';

    const source = playerSource(item);
    if (source) {
      const frame = document.createElement('iframe');
      frame.src = source.src;
      frame.title = `Official video for ${item.title}`;
      frame.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture';
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.allowFullscreen = true;
      player.replaceChildren(frame);
      playerNote.textContent = source.note;
    } else {
      const message = document.createElement('p');
      message.textContent = 'No embeddable official video is available for this title. Use the links below.';
      player.replaceChildren(message);
      playerNote.textContent = '';
    }

    const official = item.official_url || item.url || '#';
    officialLink.href = official;
    officialLink.hidden = official === '#';
    detailsLink.href = item.id ? `https://myanimelist.net/anime/${item.id}` : 'https://jikan.moe';
    updateWatchlistUI();
  }

  function openModal(item) {
    state.current = item;
    showDetails(item);
    modal.hidden = false;
    document.body.classList.add('modal-open');
    modal.querySelector('.modal-close').focus();
    enrichCurrent();
  }

  function closeModal() {
    modal.hidden = true;
    player.replaceChildren();
    state.current = null;
    document.body.classList.remove('modal-open');
  }

  function debounce(fn, delay) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  searchEl.addEventListener('input', debounce((event) => {
    state.query = event.target.value.trim();
    load();
  }, 300));

  document.querySelectorAll('.filter').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.filter').forEach((other) => {
        const active = other === button;
        other.classList.toggle('is-active', active);
        other.setAttribute('aria-pressed', String(active));
      });
      state.category = button.dataset.category;
      state.query = '';
      searchEl.value = '';
      load();
    });
  });

  watchlistToggle.addEventListener('click', () => {
    state.category = state.category === 'watchlist' ? 'all' : 'watchlist';
    const target = document.querySelector(`.filter[data-category="${state.category}"]`);
    if (target) target.click();
  });

  modalWatchlist.addEventListener('click', () => {
    if (!state.current) return;
    const key = watchKey(state.current);
    if (isSaved(state.current)) delete state.watchlist[key];
    else state.watchlist[key] = JSON.parse(JSON.stringify(state.current));
    saveWatchlist();
    updateWatchlistUI();
    if (state.category === 'watchlist' && !state.query) load();
  });

  modal.querySelectorAll('[data-close]').forEach((element) => {
    element.addEventListener('click', closeModal);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.hidden) closeModal();
  });

  updateWatchlistUI();
  render((initial.curated || []).map(normalise)); // instant, never an empty screen
  load();
})();
