"""
Jelli Web - Song Lyrics Translator (Web Version)
-------------------------------------------------
Flask backend that serves the web app and provides search/translation APIs.

Uses:
  - Genius API for song search (suggestions)
  - LRCLIB for fetching lyrics (free, reliable, no API key needed)
  - Genius scraping as fallback if LRCLIB doesn't have the song

Requirements:
    pip install flask deep-translator requests beautifulsoup4 gunicorn
"""

import os
import re
import requests
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ============================================================
# SETTINGS
# ============================================================
GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "PASTE_YOUR_TOKEN_HERE")

# Realistic browser headers for scraping (fallback)
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# LRCLIB doesn't require an API key, just a user agent
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
# LYRIC FETCHING
# ============================================================
def fetch_from_lrclib(title: str, artist: str) -> str:
    """
    Fetch lyrics from LRCLIB. Returns plain lyrics (no time stamps) or empty string.
    LRCLIB is free, requires no API key, and is reliable from cloud servers.
    """
    try:
        # LRCLIB has a /api/get endpoint that needs exact track + artist
        url = "https://lrclib.net/api/get"
        params = {
            "track_name": title,
            "artist_name": artist,
        }
        response = requests.get(url, params=params, headers=LRCLIB_HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Prefer plain lyrics; fall back to syncedLyrics with timestamps stripped
            plain = data.get("plainLyrics")
            if plain:
                return plain.strip()
            synced = data.get("syncedLyrics")
            if synced:
                # Strip timestamps like [00:12.34]
                stripped = re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced)
                return stripped.strip()
    except Exception as e:
        print(f"LRCLIB error: {e}")

    # Try the search endpoint as a second attempt (fuzzy match)
    try:
        url = "https://lrclib.net/api/search"
        params = {"q": f"{title} {artist}"}
        response = requests.get(url, params=params, headers=LRCLIB_HEADERS, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                # Take the first result
                first = results[0]
                plain = first.get("plainLyrics")
                if plain:
                    return plain.strip()
                synced = first.get("syncedLyrics")
                if synced:
                    stripped = re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced)
                    return stripped.strip()
    except Exception as e:
        print(f"LRCLIB search error: {e}")

    return ""


def fetch_from_genius_scrape(url: str) -> str:
    """
    Fallback: scrape lyrics from a Genius URL.
    May fail with 403 on some cloud servers, but worth trying.
    """
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
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

        return "\n".join(lyrics_parts).strip()
    except Exception as e:
        print(f"Genius scrape error: {e}")
        return ""


def clean_lyrics(raw_lyrics: str) -> str:
    if not raw_lyrics:
        return ""
    text = re.sub(r"\d*Embed\s*$", "", raw_lyrics)
    text = re.sub(r"You might also like", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    """Search for songs on Genius."""
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
    """Fetch lyrics (LRCLIB first, Genius fallback) and translate them."""
    data = request.get_json()
    song_id = data.get("song_id")
    lang_code = data.get("lang_code", "en")

    if not song_id:
        return jsonify({"error": "Missing song_id"}), 400

    if GENIUS_TOKEN == "PASTE_YOUR_TOKEN_HERE" or not GENIUS_TOKEN:
        return jsonify({"error": "API token not configured"}), 500

    try:
        # 1) Get song metadata from Genius API
        url = f"https://api.genius.com/songs/{song_id}"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        song_data = response.json().get("response", {}).get("song", {})

        title = song_data.get("title", "")
        artist = song_data.get("primary_artist", {}).get("name", "")
        song_url = song_data.get("url", "")

        # 2) Try LRCLIB first (free, reliable)
        raw_lyrics = fetch_from_lrclib(title, artist)
        source = "lrclib"

        # 3) Fallback to Genius scraping
        if not raw_lyrics and song_url:
            raw_lyrics = fetch_from_genius_scrape(song_url)
            source = "genius"

        if not raw_lyrics:
            return jsonify({
                "error": (
                    "Lyrics not found. The song may not be in our database, "
                    "or it might be too new/obscure. Try another song."
                )
            }), 404

        lyrics = clean_lyrics(raw_lyrics)

        # 4) Translate
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
    """Translate a single word — for click-to-translate feature."""
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
    print("🪼 Jelli Web is starting...")
    print("=" * 60)
    print(f"📍 On this computer: http://localhost:{port}")
    print(f"📱 From your phone:  http://YOUR-PC-IP:{port}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
