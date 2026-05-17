"""
Jelli Web - Song Lyrics Translator (Web Version)
-------------------------------------------------
Flask backend that serves the web app and provides search/translation APIs.

Requirements:
    pip install flask lyricsgenius deep-translator requests gunicorn

Before running locally:
    1. Set environment variable GENIUS_TOKEN (or paste it below temporarily)
    2. Run: python app.py
    3. Open http://localhost:5000 in your browser
"""

import os
from flask import Flask, render_template, request, jsonify
import re
import requests
import lyricsgenius
from deep_translator import GoogleTranslator

# ============================================================
# SETTINGS
# ============================================================
# Try to get token from environment (for deployment)
# Falls back to hardcoded value (for local testing)
GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "PASTE_YOUR_TOKEN_HERE")

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


def clean_lyrics(raw_lyrics: str) -> str:
    if not raw_lyrics:
        return ""
    lines = raw_lyrics.split("\n")
    if lines and ("Lyrics" in lines[0] or "Contributors" in lines[0]):
        lines = lines[1:]
    text = "\n".join(lines)
    text = re.sub(r"\d*Embed\s*$", "", text)
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
    """Main page."""
    return render_template("index.html", languages=LANGUAGES)


@app.route("/api/search")
def api_search():
    """Search for songs on Genius. Returns a list of suggestions."""
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
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/translate", methods=["POST"])
def api_translate():
    """Fetch lyrics for a song and translate them."""
    data = request.get_json()
    song_id = data.get("song_id")
    title = data.get("title", "")
    artist = data.get("artist", "")
    lang_code = data.get("lang_code", "en")

    if not song_id:
        return jsonify({"error": "Missing song_id"}), 400

    if GENIUS_TOKEN == "PASTE_YOUR_TOKEN_HERE" or not GENIUS_TOKEN:
        return jsonify({"error": "API token not configured"}), 500

    try:
        genius = lyricsgenius.Genius(
            GENIUS_TOKEN, timeout=15, retries=2,
            remove_section_headers=False, skip_non_songs=True,
        )
        result = genius.search_song(title, artist, song_id=song_id)
        if result is None or not result.lyrics:
            return jsonify({"error": "No lyrics found"}), 404

        lyrics = clean_lyrics(result.lyrics)
        translated = translate_in_chunks(lyrics, lang_code)

        return jsonify({
            "title": result.title,
            "artist": result.artist,
            "lyrics": lyrics,
            "translation": translated,
            "lang_name": LANGUAGES.get(lang_code, lang_code),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # host='0.0.0.0' allows connections from other devices on the same network
    # PORT env variable is used by Render; defaults to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 60)
    print("🪼 Jelli Web is starting...")
    print("=" * 60)
    print(f"📍 On this computer: http://localhost:{port}")
    print(f"📱 From your phone:  http://YOUR-PC-IP:{port}")
    print("   (replace YOUR-PC-IP with the IP shown below)")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
