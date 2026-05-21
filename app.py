"""
Jelli Web - Song Lyrics Translator (Web Version)
-------------------------------------------------
Flask backend that serves the web app and provides search/translation APIs.

Requirements:
    pip install flask deep-translator requests beautifulsoup4 gunicorn

Before running locally:
    1. Set environment variable GENIUS_TOKEN (or paste it below temporarily)
    2. Run: python app.py
    3. Open http://localhost:5000 in your browser
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

# Realistic browser headers to avoid 403 blocks from Genius
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
    "Upgrade-Insecure-Requests": "1",
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


def fetch_lyrics_from_url(url: str) -> str:
    """Fetch lyrics from a Genius URL using browser headers (bypasses 403)."""
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # Modern Genius uses divs with data-lyrics-container="true"
    containers = soup.find_all("div", {"data-lyrics-container": "true"})
    if not containers:
        # Fallback for older lyrics class
        containers = soup.find_all("div", class_=re.compile(r"Lyrics__Container"))

    lyrics_parts = []
    for container in containers:
        # Replace <br> with newlines
        for br in container.find_all("br"):
            br.replace_with("\n")
        text = container.get_text(separator="")
        lyrics_parts.append(text)

    return "\n".join(lyrics_parts).strip()


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
    """Fetch lyrics and translate them."""
    data = request.get_json()
    song_id = data.get("song_id")
    lang_code = data.get("lang_code", "en")

    if not song_id:
        return jsonify({"error": "Missing song_id"}), 400

    if GENIUS_TOKEN == "PASTE_YOUR_TOKEN_HERE" or not GENIUS_TOKEN:
        return jsonify({"error": "API token not configured"}), 500

    try:
        # Get song info & URL from Genius API
        url = f"https://api.genius.com/songs/{song_id}"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        song_data = response.json().get("response", {}).get("song", {})

        song_url = song_data.get("url")
        title = song_data.get("title", "")
        artist = song_data.get("primary_artist", {}).get("name", "")

        if not song_url:
            return jsonify({"error": "Song URL not found"}), 404

        # Fetch lyrics directly from the song page (with browser headers)
        raw_lyrics = fetch_lyrics_from_url(song_url)
        lyrics = clean_lyrics(raw_lyrics)

        if not lyrics:
            return jsonify({"error": "No lyrics found on the page"}), 404

        # Translate
        translated = translate_in_chunks(lyrics, lang_code)

        return jsonify({
            "title": title,
            "artist": artist,
            "lyrics": lyrics,
            "translation": translated,
            "lang_name": LANGUAGES.get(lang_code, lang_code),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/translate-word", methods=["POST"])
def api_translate_word():
    """Translate a single word — for click-to-translate feature."""
    data = request.get_json()
    word = (data.get("word") or "").strip()
    # Accept both 'lang_code' and 'target_lang' for flexibility
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
