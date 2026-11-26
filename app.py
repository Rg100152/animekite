"""AnimeKite — lightweight Flask backend.

Only legal data sources are used: the keyless Jikan v4 API for metadata and
privacy-enhanced YouTube embeds from official distributor channels.
"""

from __future__ import annotations

import html
import json
import os
import textwrap
import threading
import time
import zlib
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Flask, Response, abort, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "hindi_dubs.json"
JIKAN_BASE = "https://api.jikan.moe/v4"
CACHE_TTL = 900          # 15 minutes
FALLBACK_TTL = 60        # retry the live API sooner after an outage
HTTP_TIMEOUT = 4
MIN_REQUEST_GAP = 0.35   # Jikan allows 3 requests/second

app = Flask(__name__)

_cache_lock = threading.Lock()
_http_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
_last_request = [0.0]


def _load_curated() -> list[dict]:
    """Read the verified, offline-safe catalog shipped with the repository."""
    entries = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    items = []
    for entry in entries:
        items.append({
            "id": entry["id"],
            "title": entry["title"],
            "jikan_query": entry.get("jikan_query") or entry["title"],
            "score": None,
            "episodes": entry.get("episodes"),
            "studio": entry.get("studio") or "",
            "synopsis": entry.get("synopsis") or "",
            "image": f"/poster/{entry['id']}.svg",
            "poster_source": "local",
            "type": "TV",
            "year": "",
            "url": "",
            "trailer_id": "",
            "hindi_dub": bool(entry.get("hindi_dub")),
            "badge": "FREE HINDI DUB" if entry.get("hindi_dub") else "",
            "embed_url": entry.get("embed_url") or "",
            "official_url": entry.get("official_url") or "",
            "channel": entry.get("channel") or "",
            "licence_note": "Official free stream on YouTube.",
        })

    # Requested discovery titles. Where no free official upload exists, the
    # entry links to the licensed platform instead of embedding an unauthorized
    # re-upload. One-Punch Man is already present in the verified catalog above.
    extras = [
        {
            "id": "jujutsu-kaisen",
            "title": "Jujutsu Kaisen",
            "jikan_query": "Jujutsu Kaisen",
            "episodes": 59,
            "studio": "MAPPA",
            "synopsis": "Yuji Itadori swallows a cursed finger and joins the Jujutsu Headquarters to fight curses.",
            "hindi_dub": False,
            "badge": "HINDI ON CRUNCHYROLL",
            "embed_url": "",
            "official_url": "https://www.crunchyroll.com/search?q=Jujutsu%20Kaisen",
            "channel": "",
            "licence_note": "Hindi dub is licensed to Crunchyroll (subscription); no free official embed.",
        },
        {
            "id": "demon-slayer",
            "title": "Demon Slayer: Kimetsu no Yaiba",
            "jikan_query": "Kimetsu no Yaiba",
            "episodes": 63,
            "studio": "Ufotable",
            "synopsis": "Tanjiro Kamado joins the Demon Slayer Corps after his sister is turned into a demon.",
            "hindi_dub": False,
            "badge": "HINDI ON CRUNCHYROLL",
            "embed_url": "",
            "official_url": "https://www.crunchyroll.com/search?q=Demon%20Slayer",
            "channel": "",
            "licence_note": "Hindi dub is licensed to Crunchyroll (subscription); no free official embed.",
        },
        {
            "id": "naruto-official-hindi",
            "title": "Naruto (Official Hindi Dub)",
            "jikan_query": "Naruto",
            "episodes": 220,
            "studio": "Pierrot",
            "synopsis": "Naruto Uzumaki dreams of becoming Hokage while mastering the Nine-Tails sealed inside him.",
            "hindi_dub": True,
            "badge": "FREE HINDI DUB",
            "embed_url": (
                "https://www.youtube-nocookie.com/embed/videoseries"
                "?list=PLqthdhi8pW12U4acXlc7QUnruzJS4FCCA&rel=0"
            ),
            "official_url": "https://www.youtube.com/playlist?list=PLqthdhi8pW12U4acXlc7QUnruzJS4FCCA",
            "channel": "Cartoon Network India / Nickelodeon India",
            "licence_note": "Official Hindi dub published by the broadcast rights holders.",
        },
        {
            "id": "frieren",
            "title": "Frieren: Beyond Journey's End",
            "jikan_query": "Sousou no Frieren",
            "episodes": 28,
            "studio": "Madhouse",
            "synopsis": "After the hero party defeats the Demon King, the elf mage Frieren begins a long journey of reflection.",
            "hindi_dub": False,
            "badge": "HINDI ON CRUNCHYROLL",
            "embed_url": "",
            "official_url": "https://www.crunchyroll.com/search?q=Frieren",
            "channel": "",
            "licence_note": "Hindi dub is licensed to Crunchyroll (subscription); no free official embed.",
        },
        {
            "id": "solo-leveling",
            "title": "Solo Leveling",
            "jikan_query": "Solo Leveling",
            "episodes": 25,
            "studio": "A-1 Pictures",
            "synopsis": "An E-rank hunter gains a mysterious ability to level up after surviving a deadly dungeon.",
            "hindi_dub": False,
            "badge": "HINDI ON CRUNCHYROLL",
            "embed_url": "",
            "official_url": "https://www.crunchyroll.com/search?q=Solo%20Leveling",
            "channel": "",
            "licence_note": "Hindi dub is licensed to Crunchyroll (subscription); no free official embed.",
        },
    ]

    known = {item["title"].lower() for item in items}
    for extra in extras:
        if extra["title"].lower() in known:
            continue
        base = {
            "score": None,
            "image": f"/poster/{extra['id']}.svg",
            "poster_source": "local",
            "type": "TV",
            "year": "",
            "url": "",
            "trailer_id": "",
        }
        base.update(extra)
        items.append(base)
    return items


CURATED_HINDI_ANIME = _load_curated()


def _cached(key: str, producer, ttl: int = CACHE_TTL):
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and now - entry[0] < ttl:
            return entry[1]
    value = producer()
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


def _jikan_get(path: str):
    with _http_lock:
        gap = MIN_REQUEST_GAP - (time.monotonic() - _last_request[0])
        if gap > 0:
            time.sleep(gap)
        _last_request[0] = time.monotonic()
    try:
        response = requests.get(
            JIKAN_BASE + path,
            timeout=HTTP_TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": "AnimeKite/2.0 (+https://github.com/Rg100152/animekite)",
            },
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        app.logger.warning("Jikan request failed: %s", exc)
        return None


def _simplify(item: dict) -> dict:
    jpg = (item.get("images") or {}).get("jpg") or {}
    studios = [s["name"] for s in (item.get("studios") or []) if s.get("name")]
    return {
        "id": item.get("mal_id"),
        "title": item.get("title") or item.get("title_english") or "Untitled",
        "jikan_query": item.get("title") or "",
        "image": jpg.get("large_image_url") or jpg.get("image_url") or "",
        "poster_source": "jikan" if jpg else "local",
        "score": item.get("score"),
        "episodes": item.get("episodes"),
        "studio": ", ".join(studios),
        "studios": studios,
        "synopsis": item.get("synopsis") or "",
        "type": item.get("type") or "",
        "year": (item.get("aired") or {}).get("from", "")[:4],
        "url": item.get("url") or "",
        "trailer_id": (item.get("trailer") or {}).get("youtube_id") or "",
        "hindi_dub": False,
        "badge": "",
        "embed_url": "",
        "official_url": item.get("url") or "",
        "channel": "",
        "licence_note": "Official trailer from Jikan metadata.",
    }


def _fallback() -> list[dict]:
    return [dict(item) for item in CURATED_HINDI_ANIME]


def _collection(key: str, path: str) -> list[dict]:
    def producer():
        payload = _jikan_get(path)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            return _fallback()
        return [_simplify(row) for row in rows]

    # Cache a live response for 15 minutes, but retry quickly after an outage.
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get("collection:" + key)
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]
    value = producer()
    ttl = CACHE_TTL if value and value[0].get("poster_source") == "jikan" else FALLBACK_TTL
    with _cache_lock:
        _cache["collection:" + key] = (time.monotonic(), value)
    return value


def _search(query: str, limit: int = 24) -> list[dict]:
    key = "search:" + query.lower()
    return _cached(key, lambda: _do_search(query, limit))


def _do_search(query: str, limit: int) -> list[dict]:
    path = "/anime?" + urlencode({"q": query, "limit": limit, "sfw": True})
    payload = _jikan_get(path)
    rows = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(rows, list) and rows:
        return [_simplify(row) for row in rows]
    needle = query.lower()
    return [dict(item) for item in CURATED_HINDI_ANIME if needle in item["title"].lower()]


@app.get("/")
def index():
    # The verified catalog is rendered immediately; live categories are loaded
    # by JavaScript afterwards, so the screen is never empty.
    return render_template(
        "index.html",
        curated=CURATED_HINDI_ANIME,
        airing=[],
        repository="https://github.com/Rg100152/animekite",
    )


@app.get("/api/anime")
def api_anime():
    query = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "all").strip().lower()

    if query:
        return jsonify(data=_search(query), source="jikan-or-cached", query=query)

    if category in {"hindi", "hindi_dubbed"}:
        return jsonify(data=_fallback(), source="curated")
    if category == "airing":
        return jsonify(data=_collection("airing", "/top/anime?filter=airing&limit=24"), source="jikan-or-cached")
    if category == "movies":
        return jsonify(data=_collection("movies", "/top/anime?filter=movies&limit=24"), source="jikan-or-cached")
    if category == "watchlist":
        return jsonify(data=[], source="local")
    return jsonify(data=_collection("all", "/seasons/now?limit=24&sfw=true"), source="jikan-or-cached")


@app.get("/api/metadata")
def api_metadata():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(error="Missing query"), 400
    key = "metadata:" + query.lower()

    def producer():
        results = _do_search(query, 1)
        return results[0] if results else None

    return jsonify(data=_cached(key, producer))


@app.get("/poster/<slug>.svg")
def poster(slug: str):
    title = next((item["title"] for item in CURATED_HINDI_ANIME if item["id"] == slug), None)
    if not title:
        abort(404)
    key = "poster:" + slug

    def producer():
        first, second = (("#ff5722", "#00d2ff"), ("#00d2ff", "#ff5722"),
                         ("#ffcc00", "#ff5722"))[zlib.crc32(slug.encode()) % 3]
        lines = textwrap.wrap(title, 18)[:3] or [title]
        text = "".join(
            f'<tspan x="150" dy="{42 if i == 0 else 30}" fill="#f8fafc">{html.escape(line)}</tspan>'
            for i, line in enumerate(lines)
        )
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 450" width="300" height="450" role="img">'
            '<rect width="300" height="450" fill="#161b26"/>'
            f'<path d="M150 96 L232 178 L150 260 L68 178 Z" fill="{first}"/>'
            f'<path d="M150 96 L232 178 L150 178 Z" fill="{second}"/>'
            '<path d="M132 152 L132 204 L184 178 Z" fill="#0d0f14"/>'
            f'<text x="150" y="330" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" '
            f'font-size="19" font-weight="700">{text}</text>'
            '<text x="150" y="418" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" '
            'font-size="13" fill="#94a3b8">AnimeKite</text></svg>'
        )

    svg = _cached(key, producer)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.errorhandler(404)
def not_found(_error):
    return jsonify(error="Not found"), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify(error="Server error", message=str(error)), 500


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False, threaded=True)
