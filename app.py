"""
Jelli Web - Song Lyrics Translator (Web Version)
-------------------------------------------------
Flask backend with multiple lyric sources for maximum coverage:
  1. LRCLIB         - Free, no API key, reliable from cloud
  2. Lyrics.ovh     - Free fallback API
  3. stixoi.info    - For Greek songs
  4. Genius scrape  - Final fallback (may fail with 403 on cloud)

Requirements:
    pip install flask deep-translator requests beautifulsoup4 gunicorn
"""

import os
import re
import time
import random
import urllib.parse
import requests
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ============================================================
# SETTINGS
# ============================================================
GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "PASTE_YOUR_TOKEN_HERE")

# Multiple User-Agents to rotate (helps avoid 403 blocks)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_browser_headers():
    """Return a randomized set of browser-like headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


LRCLIB_HEADERS = {
    "User-Agent": "Jelli/1.0 (https://jelli-rl6f.onrender.com)",
}

LANGUAGES = {
    "en": "English", "el": "Greek", "es": "Spanish", "fr": "French",
    "de": "German", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "tr": "Turkish", "ja": "Japanese", "ko": "Korean",
    "zh-CN": "Chinese (Simplified)", "ar": "Arabic", "nl": "Dutch",
    "sv": "Swedish", "pl": "Polish", "ro": "Romanian", "bg": "Bulgarian",
    "hi": "Hindi", "id": "Indonesian", "vi": "Vietnamese", "th": "Thai",
    "cs": "Czech", "da": "Danish", "fi": "Finnish", "no": "Norwegian",
    "hu": "Hungarian", "uk": "Ukrainian",
}

app = Flask(__name__)


# ============================================================
# LYRIC SOURCES (try in order)
# ============================================================
def fetch_from_lrclib(title: str, artist: str) -> str:
    """Source 1: LRCLIB - free, no key, reliable."""
    # Try exact match first
    try:
        url = "https://lrclib.net/api/get"
        params = {"track_name": title, "artist_name": artist}
        response = requests.get(url, params=params, headers=LRCLIB_HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            plain = data.get("plainLyrics")
            if plain:
                return plain.strip()
            synced = data.get("syncedLyrics")
            if synced:
                return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced).strip()
    except Exception as e:
        print(f"LRCLIB exact match error: {e}")

    # Try search endpoint (fuzzy match)
    try:
        url = "https://lrclib.net/api/search"
        params = {"q": f"{title} {artist}"}
        response = requests.get(url, params=params, headers=LRCLIB_HEADERS, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                first = results[0]
                plain = first.get("plainLyrics")
                if plain:
                    return plain.strip()
                synced = first.get("syncedLyrics")
                if synced:
                    return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced).strip()
    except Exception as e:
        print(f"LRCLIB search error: {e}")

    return ""


def fetch_from_lyrics_ovh(title: str, artist: str) -> str:
    """Source 2: Lyrics.ovh - free API, no key required."""
    try:
        url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get("lyrics", "")
            if lyrics:
                # Lyrics.ovh sometimes returns lyrics with \r\n - normalize
                return lyrics.replace("\r\n", "\n").strip()
    except Exception as e:
        print(f"Lyrics.ovh error: {e}")
    return ""


def fetch_from_stixoi(title: str, artist: str) -> str:
    """Source 3: stixoi.info - Greek lyrics site."""
    try:
        # Search using their search URL
        query = f"{artist} {title}"
        search_url = "https://www.stixoi.info/stixoi.php"
        params = {
            "info": "Lyrics",
            "act": "find",
            "search": query,
        }
        headers = get_browser_headers()
        response = requests.get(search_url, params=params, headers=headers, timeout=12)
        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        # Find first result link to a song page
        links = soup.find_all("a", href=re.compile(r"info=Lyrics.*act=details"))
        if not links:
            return ""

        # Get the song page
        song_url = "https://www.stixoi.info/" + links[0]["href"]
        time.sleep(0.3)  # tiny delay
        song_response = requests.get(song_url, headers=get_browser_headers(), timeout=12)
        if song_response.status_code != 200:
            return ""

        song_soup = BeautifulSoup(song_response.text, "html.parser")
        # Lyrics are usually in a <div> or <td> with class "lyrics" or in a font tag
        # Try multiple selectors
        lyrics_div = (
            song_soup.find("div", class_="lyrics") or
            song_soup.find("td", class_="lyrics") or
            song_soup.find("div", id="lyrics")
        )
        if lyrics_div:
            for br in lyrics_div.find_all("br"):
                br.replace_with("\n")
            text = lyrics_div.get_text(separator="").strip()
            if text and len(text) > 30:  # avoid empty/error pages
                return text
    except Exception as e:
        print(f"Stixoi error: {e}")
    return ""


def fetch_from_genius_scrape(url: str) -> str:
    """Source 4: Genius scraping with rotating headers + retries."""
    if not url:
        return ""

    # Try up to 3 times with different headers
    for attempt in range(3):
        try:
            headers = get_browser_headers()
            if attempt > 0:
                time.sleep(0.5 + random.random())  # small randomized delay
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 403:
                continue  # try with different headers
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            containers = soup.find_all("div", {"data-lyrics-container": "true"})
            if not containers:
                containers = soup.find_all("div", class_=re.compile(r"Lyrics__Container"))

            lyrics_parts = []
            for container in containers:
                for br in container.find_all("br"):
                    br.replace_with("\n")
                text = container.get_text(separator="")
                lyrics_parts.append(text)

            if lyrics_parts:
                return "\n".join(lyrics_parts).strip()
        except Exception as e:
            print(f"Genius scrape attempt {attempt + 1} error: {e}")
            continue

    return ""


def clean_lyrics(raw_lyrics: str) -> str:
    if not raw_lyrics:
        return ""
    text = re.sub(r"\d*Embed\s*$", "", raw_lyrics)
    text = re.sub(r"You might also like", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_greek(text: str) -> bool:
    """Quick check if text contains Greek characters."""
    return bool(re.search(r"[\u0370-\u03FF\u1F00-\u1FFF]", text))


def get_lyrics_multi_source(title: str, artist: str, song_url: str = "") -> tuple:
    """
    Try multiple sources in order. Returns (lyrics, source_name).
    If artist or title look Greek, prioritize stixoi.info.
    """
    looks_greek = is_greek(title) or is_greek(artist)

    sources = []
    if looks_greek:
        # For Greek songs: stixoi first, then LRCLIB, then others
        sources = [
            ("stixoi.info", lambda: fetch_from_stixoi(title, artist)),
            ("LRCLIB", lambda: fetch_from_lrclib(title, artist)),
            ("Lyrics.ovh", lambda: fetch_from_lyrics_ovh(title, artist)),
            ("Genius", lambda: fetch_from_genius_scrape(song_url)),
        ]
    else:
        # For other songs: LRCLIB first, then Lyrics.ovh, then Genius
        sources = [
            ("LRCLIB", lambda: fetch_from_lrclib(title, artist)),
            ("Lyrics.ovh", lambda: fetch_from_lyrics_ovh(title, artist)),
            ("Genius", lambda: fetch_from_genius_scrape(song_url)),
            ("stixoi.info", lambda: fetch_from_stixoi(title, artist)),
        ]

    for source_name, fetch_fn in sources:
        try:
            lyrics = fetch_fn()
            if lyrics and len(lyrics.strip()) > 30:
                return lyrics, source_name
        except Exception as e:
            print(f"{source_name} unexpected error: {e}")
            continue

    return "", ""


def translate_in_chunks(text: str, target_lang: str) -> str:
    translator = GoogleTranslator(source="auto", target=target_lang)
    max_len = 4500
    if len(text) <= max_len:
        return translator.translate(text)
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = (current + "\n" + line) if current else line
    if current:
        chunks.append(current)
    return "\n".join(translator.translate(chunk) for chunk in chunks)


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template("index.html", languages=LANGUAGES)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})

    if GENIUS_TOKEN == "PASTE_YOUR_TOKEN_HERE" or not GENIUS_TOKEN:
        return jsonify({"error": "API token not configured"}), 500

    try:
        url = "https://api.genius.com/search"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        params = {"q": query, "per_page": 10}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for hit in data.get("response", {}).get("hits", []):
            result = hit.get("result", {})
            results.append({
                "id": result.get("id"),
                "title": result.get("title", ""),
                "artist": result.get("primary_artist", {}).get("name", ""),
                "url": result.get("url", ""),
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json()
    song_id = data.get("song_id")
    lang_code = data.get("lang_code", "en")

    if not song_id:
        return jsonify({"error": "Missing song_id"}), 400

    if GENIUS_TOKEN == "PASTE_YOUR_TOKEN_HERE" or not GENIUS_TOKEN:
        return jsonify({"error": "API token not configured"}), 500

    try:
        # Get song metadata from Genius API
        url = f"https://api.genius.com/songs/{song_id}"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        song_data = response.json().get("response", {}).get("song", {})

        title = song_data.get("title", "")
        artist = song_data.get("primary_artist", {}).get("name", "")
        song_url = song_data.get("url", "")

        # Try multiple sources
        raw_lyrics, source = get_lyrics_multi_source(title, artist, song_url)

        if not raw_lyrics:
            return jsonify({
                "error": (
                    "Lyrics not available right now. Try searching with a simpler title "
                    "(e.g. just the song name without 'feat.' or remix info)."
                )
            }), 404

        lyrics = clean_lyrics(raw_lyrics)
        translated = translate_in_chunks(lyrics, lang_code)

        return jsonify({
            "title": title,
            "artist": artist,
            "lyrics": lyrics,
            "translation": translated,
            "lang_name": LANGUAGES.get(lang_code, lang_code),
            "source": source,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/translate-word", methods=["POST"])
def api_translate_word():
    data = request.get_json()
    word = (data.get("word") or "").strip()
    lang_code = data.get("lang_code") or data.get("target_lang") or "en"

    if not word:
        return jsonify({"error": "No word provided"}), 400

    try:
        translation = GoogleTranslator(source="auto", target=lang_code).translate(word)
        return jsonify({"word": word, "translation": translation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 60)
    print("🪼 Jelli Web is starting (multi-source mode)...")
    print("=" * 60)
    print(f"📍 On this computer: http://localhost:{port}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
