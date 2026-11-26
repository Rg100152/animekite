# Software Design Document (SDD)

**Project:** AnimeKite — Open-Source Anime Discovery & Legal Hindi-Dub Hub
**Version:** 2.0.0 (Python Flask Migration)
**Author:** Raj Gautam (Open Source Lover)
**Repository:** github.com/Rg100152/animekite
**License:** MIT License

---

## 1. Introduction & Architecture Shift

### 1.1 Purpose

AnimeKite is a lightweight, open-source web portal for discovering top anime and watching legally available free Hindi-dubbed episodes from authorized distributors such as Muse India and the official CN/Nick India Naruto channel.

### 1.2 Why Python (Flask)?

Migrating from Ruby to Python (Flask + `requests`) provides native compatibility with Linux desktops such as Pop!_OS, reliable JSON parsing, and a built-in curated catalog that is rendered immediately. Anime cards are never empty, even when Jikan times out or is rate-limited: the server ships a verified offline catalog and generates local SVG posters for every curated entry.

## 2. System Architecture & Data Flow

```
+--------------------+        HTTP / JSON        +-------------------------+
|   Web Browser      | <-----------------------> |   Python Flask Server   |
| (Jinja2 / CSS / JS)|                           |   (app.py - Port 5000)  |
+--------------------+                           +-------------------------+
         |                                                  |
         |-- localStorage (My Watchlist)                    |-- 15-Min Memory TTL Cache
         |-- youtube-nocookie.com (Official Player)         |-- Jikan v4 REST API (Keyless)
         |-- Curated offline catalog + local SVG posters    |-- Built-in Hindi Dub Fallback
```

### 2.1 Technology Stack

- **Backend:** Python 3.8+, Flask (routing and Jinja2 templates), `requests` (HTTP client), `threading` locks for cache/rate limiting.
- **Frontend:** Semantic HTML5, zero-animation flat dark CSS3, vanilla ES6 JavaScript.
- **Data sources (100% free and keyless):**
  1. **Jikan REST API v4** (`https://api.jikan.moe/v4`) for live airing anime, movies, scores, synopses and trailers.
  2. **Built-in curated Hindi dub catalog** (`data/hindi_dubs.json` plus explicit discovery entries in `app.py`) with verified official `youtube-nocookie.com` embeds.
- **Persistence:** Browser `localStorage` for the watchlist; no database.

## 3. Directory Structure

```
animekite/
├── app.py                        # Flask backend, Jikan client, TTL cache, SVG posters
├── requirements.txt              # flask, requests
├── DESIGN.md                     # This document
├── LICENSE                       # MIT License (Copyright 2026 Raj Gautam)
├── README.md                     # GitHub documentation with banner & setup
├── data/
│   └── hindi_dubs.json           # Curated official free Hindi-dubbed embeds
├── static/
│   ├── css/
│   │   └── style.css             # Flat dark OTT stylesheet
│   ├── js/
│   │   └── app.js                # Search, filters, theater modal, watchlist
│   └── images/
│       ├── animekite_logo.svg    # Custom vector logo
│       ├── animekite_banner.svg  # Promotional & GitHub README banner
│       └── poster_placeholder.svg
└── templates/
    └── index.html                # Main responsive web interface
```

## 4. UI, Color & Performance Specifications (4 GB RAM Optimized)

| Role | Color |
| --- | --- |
| Background | `#0d0f14` (Deep Slate Dark) |
| Cards / modal | `#161b26` (Charcoal) |
| Primary accent / HINDI DUB badge | `#ff5722` (Saffron Orange) |
| Secondary accent | `#00d2ff` (Electric Cyan) |
| Ratings | `#ffcc00` (Golden Yellow) |
| Text / muted | `#f8fafc` / `#94a3b8` |

- **Zero heavy animations:** no CSS keyframes, no GPU blur filters — minimal CPU and fan usage.
- **Lazy loading:** every poster image uses `loading="lazy"`; curated posters are local SVGs generated on demand and cached in RAM.
- **Caching:** Jikan responses are cached for 900 seconds (15 minutes); fallback responses are retried after 60 seconds. Repeated loads are effectively instant.
- **Rate limiting:** outbound Jikan calls are serialized with a 350 ms minimum gap (within the public 3 req/s limit) and a 4 second timeout.

## 5. Functional Components

1. **Top Bar:** Logo, instant debounced search, watchlist toggle with count, GitHub link.
2. **Hero Banner:** `animekite_banner.svg` (1200×360) with category quick filters.
3. **Filter Tabs:** All Anime, Hindi Dubbed (Official Free), Top Airing, Popular Movies, My Watchlist.
4. **Poster Grid:** CSS Grid `minmax(180px, 1fr)`, saffron HINDI DUB badge, partner badge for subscription-only Hindi dubs, golden score badge.
5. **Theater Modal:** privacy-enhanced `youtube-nocookie.com` player for official streams/trailers, synopsis, episode count, studio, licence note, watchlist toggle, official platform link.
6. **Local Watchlist:** stored entirely in `localStorage` with the key `animekite.watchlist.v1`.

## 6. Backend Endpoints (`app.py`)

| Endpoint | Behavior |
| --- | --- |
| `GET /` | Renders `templates/index.html` with the built-in curated catalog so cards appear immediately. |
| `GET /api/anime?category=hindi\|airing\|movies\|all` | Returns the curated catalog or a Jikan ranking; falls back to the catalog on failure. |
| `GET /api/anime?q=<text>` | Jikan title search (SFW); falls back to local title filtering. |
| `GET /api/metadata?q=<title>` | Cached single-title lookup to add posters/scores in the modal. |
| `GET /poster/<id>.svg` | Locally generated, cached SVG poster for a curated title. |

## 7. Legal & Privacy Notes

- No unauthorized streaming APIs, scraping, or re-uploaded episodes are used.
- Jujutsu Kaisen, Demon Slayer, Frieren and Solo Leveling are discovery entries with links to their licensed platform (Crunchyroll); no unofficial YouTube embed is attached to them.
- One-Punch Man and Naruto are included only through verified official Hindi-dub playlists.
- Player requests use `youtube-nocookie.com`, which avoids YouTube cookies until the user interacts with the player.
- Original SVG artwork belongs to this project; anime posters remain the property of their rights holders and are only shown as metadata thumbnails when provided by Jikan.

## 8. Verification

```
python3 -m py_compile app.py
pip install -r requirements.txt
python3 app.py              # http://127.0.0.1:5000
curl http://127.0.0.1:5000/api/anime?category=hindi
```
