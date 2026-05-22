"""
Jelli Web - Song Lyrics Translator (Web Version)
-------------------------------------------------
Multi-source lyrics with smart fallback strategies.

Sources tried (in order based on language detection):
  1. LRCLIB         - Free, no API key
  2. Lyrics.ovh     - Free fallback API
  3. stixoi.info    - Greek lyrics
  4. Genius scrape  - Final fallback with rotating UAs

Smart strategies:
  - Tries multiple title/artist variations
  - Strips parentheticals like "(feat. X)" or "(Remix)"
  - Tries transliteration if title is Greek/non-Latin

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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_browser_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
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
# HELPERS FOR TITLE/ARTIST CLEANING
# ============================================================
def strip_parentheticals(text: str) -> str:
    """Remove (feat. X), (Remix), [Live], etc."""
    text = re.sub(r"\s*[\(\[\{][^)\]\}]*[\)\]\}]\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_transliteration(title: str) -> str:
    """
    For titles like "Όταν Σ' Είχα Πρωτοδεί (Otan S' Eixa Prwtodei)",
    extract the Latin part inside parentheses.
    """
    match = re.search(r"\(([A-Za-z][^)]*)\)", title)
    return match.group(1).strip() if match else ""


def is_greek(text: str) -> bool:
    return bool(re.search(r"[\u0370-\u03FF\u1F00-\u1FFF]", text))


def title_variations(title: str) -> list:
    """Return a list of title variations to try."""
    variations = [title]
    # Without parentheticals
    cleaned = strip_parentheticals(title)
    if cleaned and cleaned != title:
        variations.append(cleaned)
    # Just the part before any dash (e.g. "Song Name - Live" -> "Song Name")
    if " - " in title:
        variations.append(title.split(" - ")[0].strip())
    # Transliteration if exists
    translit = extract_transliteration(title)
    if translit:
        variations.append(translit)
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for v in variations:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            unique.append(v)
    return unique


# ============================================================
# LYRIC SOURCES
# ============================================================
def fetch_from_azlyrics(title: str, artist: str) -> str:
    """Source 5: AZLyrics - large database, especially for English songs."""
    try:
        # AZLyrics URL format: azlyrics.com/lyrics/[artist]/[title].html
        # Both need to be lowercase, no spaces, no special chars
        def clean_for_url(s: str) -> str:
            # Remove "The " prefix
            s = re.sub(r"^the\s+", "", s, flags=re.IGNORECASE)
            # Keep only alphanumeric
            s = re.sub(r"[^a-zA-Z0-9]", "", s)
            return s.lower()

        artist_clean = clean_for_url(artist)
        title_clean = clean_for_url(title)
        if not artist_clean or not title_clean:
            return ""

        url = f"https://www.azlyrics.com/lyrics/{artist_clean}/{title_clean}.html"
        headers = get_browser_headers()
        # AZLyrics specifically requires a referrer to avoid blocks
        headers["Referer"] = "https://www.azlyrics.com/"
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return ""

        # AZLyrics puts lyrics in a div with no id/class, between specific comments
        # Look for "<!-- Usage of azlyrics.com content..." comment
        html = response.text
        # Find the lyrics block - between two specific HTML comments
        match = re.search(
            r"<!-- Usage of azlyrics\.com content.*?-->\s*(.*?)\s*</div>",
            html,
            re.DOTALL,
        )
        if match:
            raw = match.group(1)
            # Remove HTML tags but keep <br> as newlines
            raw = re.sub(r"<br\s*/?>", "\n", raw)
            raw = re.sub(r"<[^>]+>", "", raw)
            # Decode HTML entities
            raw = raw.replace("&quot;", '"').replace("&amp;", "&")
            raw = raw.replace("&#39;", "'").replace("&apos;", "'")
            text = raw.strip()
            if text and len(text) > 30:
                return text
    except Exception as e:
        print(f"AZLyrics error: {e}")
    return ""


def fetch_from_lrclib(title: str, artist: str) -> str:
    """LRCLIB - tries exact match then fuzzy search with multiple variations."""
    titles_to_try = title_variations(title)

    for t in titles_to_try:
        # Exact match
        try:
            response = requests.get(
                "https://lrclib.net/api/get",
                params={"track_name": t, "artist_name": artist},
                headers=LRCLIB_HEADERS, timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                plain = data.get("plainLyrics")
                if plain:
                    return plain.strip()
                synced = data.get("syncedLyrics")
                if synced:
                    return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced).strip()
        except Exception:
            pass

    # Fuzzy search with full query
    for t in titles_to_try:
        try:
            response = requests.get(
                "https://lrclib.net/api/search",
                params={"q": f"{t} {artist}"},
                headers=LRCLIB_HEADERS, timeout=10,
            )
            if response.status_code == 200:
                results = response.json()
                if results:
                    first = results[0]
                    plain = first.get("plainLyrics")
                    if plain:
                        return plain.strip()
                    synced = first.get("syncedLyrics")
                    if synced:
                        return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced).strip()
        except Exception:
            pass

    # Last attempt: search by title only
    for t in titles_to_try:
        try:
            response = requests.get(
                "https://lrclib.net/api/search",
                params={"q": t},
                headers=LRCLIB_HEADERS, timeout=10,
            )
            if response.status_code == 200:
                results = response.json()
                # Try to find result with matching artist name
                for result in results[:5]:
                    result_artist = (result.get("artistName") or "").lower()
                    if artist.lower() in result_artist or result_artist in artist.lower():
                        plain = result.get("plainLyrics")
                        if plain:
                            return plain.strip()
                        synced = result.get("syncedLyrics")
                        if synced:
                            return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", synced).strip()
        except Exception:
            pass

    return ""


def fetch_from_lyrics_ovh(title: str, artist: str) -> str:
    """Lyrics.ovh - free API with title variations."""
    titles_to_try = title_variations(title)
    for t in titles_to_try:
        try:
            url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(t)}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                lyrics = data.get("lyrics", "")
                if lyrics and len(lyrics.strip()) > 30:
                    return lyrics.replace("\r\n", "\n").strip()
        except Exception:
            pass
    return ""


def fetch_from_stixoi(title: str, artist: str) -> str:
    """stixoi.info - Greek lyrics with multiple search strategies."""
    titles_to_try = title_variations(title)
    queries = []
    for t in titles_to_try:
        queries.append(f"{artist} {t}")
        queries.append(t)  # title only as fallback

    for query in queries:
        try:
            search_url = "https://www.stixoi.info/stixoi.php"
            params = {"info": "Lyrics", "act": "find", "search": query}
            response = requests.get(
                search_url, params=params, headers=get_browser_headers(), timeout=12
            )
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r"info=Lyrics.*act=details"))
            if not links:
                continue

            # Try the first 3 results
            for link in links[:3]:
                song_url = "https://www.stixoi.info/" + link["href"]
                time.sleep(0.3)
                try:
                    song_response = requests.get(
                        song_url, headers=get_browser_headers(), timeout=12
                    )
                    if song_response.status_code != 200:
                        continue
                    song_soup = BeautifulSoup(song_response.text, "html.parser")
                    lyrics_div = (
                        song_soup.find("div", class_="lyrics") or
                        song_soup.find("td", class_="lyrics") or
                        song_soup.find("div", id="lyrics")
                    )
                    if lyrics_div:
                        for br in lyrics_div.find_all("br"):
                            br.replace_with("\n")
                        text = lyrics_div.get_text(separator="").strip()
                        if text and len(text) > 30:
                            return text
                except Exception:
                    continue
        except Exception:
            continue
    return ""


def fetch_from_genius_scrape(url: str) -> str:
    """Genius scraping with rotating headers + retries."""
    if not url:
        return ""

    for attempt in range(3):
        try:
            headers = get_browser_headers()
            if attempt > 0:
                time.sleep(0.5 + random.random())
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 403:
                continue
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            containers = soup.find_all("div", {"data-lyrics-container": "true"})
            if not containers:
                containers = soup.find_all("div", class_=re.compile(r"Lyrics__Container"))

            lyrics_parts = []
            for container in containers:
                for br in container.find_all("br"):
                    br.replace_with("\n")
                lyrics_parts.append(container.get_text(separator=""))

            if lyrics_parts:
                return "\n".join(lyrics_parts).strip()
        except Exception:
            continue
    return ""


def clean_lyrics(raw_lyrics: str) -> str:
    if not raw_lyrics:
        return ""
    text = re.sub(r"\d*Embed\s*$", "", raw_lyrics)
    text = re.sub(r"You might also like", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_lyrics_multi_source(title: str, artist: str, song_url: str = "") -> tuple:
    """Try all sources. For Greek songs, prioritize stixoi.info."""
    looks_greek = is_greek(title) or is_greek(artist)

    if looks_greek:
        sources = [
            ("stixoi.info", lambda: fetch_from_stixoi(title, artist)),
            ("LRCLIB", lambda: fetch_from_lrclib(title, artist)),
            ("AZLyrics", lambda: fetch_from_azlyrics(title, artist)),
            ("Genius", lambda: fetch_from_genius_scrape(song_url)),
            ("Lyrics.ovh", lambda: fetch_from_lyrics_ovh(title, artist)),
        ]
    else:
        sources = [
            ("LRCLIB", lambda: fetch_from_lrclib(title, artist)),
            ("Lyrics.ovh", lambda: fetch_from_lyrics_ovh(title, artist)),
            ("AZLyrics", lambda: fetch_from_azlyrics(title, artist)),
            ("Genius", lambda: fetch_from_genius_scrape(song_url)),
            ("stixoi.info", lambda: fetch_from_stixoi(title, artist)),
        ]

    for source_name, fetch_fn in sources:
        try:
            lyrics = fetch_fn()
            if lyrics and len(lyrics.strip()) > 30:
                return lyrics, source_name
        except Exception:
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
        url = f"https://api.genius.com/songs/{song_id}"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        song_data = response.json().get("response", {}).get("song", {})

        title = song_data.get("title", "")
        artist = song_data.get("primary_artist", {}).get("name", "")
        song_url = song_data.get("url", "")

        raw_lyrics, source = get_lyrics_multi_source(title, artist, song_url)

        if not raw_lyrics:
            return jsonify({
                "error": (
                    "Lyrics not found in any source. The song may be too new, "
                    "obscure, or have a misspelled title."
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
    print("🪼 Jelli Web is starting...")
    print("=" * 60)
    print(f"📍 On this computer: http://localhost:{port}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
