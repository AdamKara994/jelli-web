// ===== JELLI WEB - FRONTEND LOGIC =====

document.addEventListener("DOMContentLoaded", () => {
    initJelli();
});

function initJelli() {
    // ===== ELEMENT REFERENCES =====
    const welcomeScreen = document.getElementById("welcomeScreen");
    const translationScreen = document.getElementById("translationScreen");
    const historyScreen = document.getElementById("historyScreen");
    const searchInput = document.getElementById("searchInput");
    const suggestionsWrapper = document.getElementById("suggestionsWrapper");
    const suggestionsList = document.getElementById("suggestionsList");
    const welcomeStatus = document.getElementById("welcomeStatus");
    const backBtn = document.getElementById("backBtn");
    const backFromHistoryBtn = document.getElementById("backFromHistoryBtn");
    const clearHistoryBtn = document.getElementById("clearHistoryBtn");
    const songInfo = document.getElementById("songInfo");
    const originalLyrics = document.getElementById("originalLyrics");
    const translatedLyrics = document.getElementById("translatedLyrics");
    const transStatus = document.getElementById("transStatus");
    const logoWrapper = document.getElementById("logoWrapper");
    const historyList = document.getElementById("historyList");
    const historyEmpty = document.getElementById("historyEmpty");
    const languageModal = document.getElementById("languageModal");
    const modalClose = document.getElementById("modalClose");
    const modalSongInfo = document.getElementById("modalSongInfo");

    let searchTimeout = null;
    let currentSearchQuery = "";
    let pendingSong = null;
    let lastSearchResults = []; // Cache last search results to restore them

    // Last used language - we save this to localStorage so the user's preference persists
    const LAST_LANG_KEY = "jelli_last_lang";
    function getLastUsedLang() {
        try {
            return localStorage.getItem(LAST_LANG_KEY) || "en";
        } catch (e) {
            return "en";
        }
    }
    function setLastUsedLang(lang) {
        try {
            localStorage.setItem(LAST_LANG_KEY, lang);
        } catch (e) {}
    }

    // ===== HISTORY =====
    const HISTORY_KEY = "jelli_history";
    const MAX_HISTORY = 50;
    const LANGUAGE_NAMES = {
        "en": "English", "el": "Greek", "es": "Spanish", "fr": "French",
        "de": "German", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
        "tr": "Turkish", "ja": "Japanese", "ko": "Korean",
        "zh-CN": "Chinese (Simplified)", "ar": "Arabic", "nl": "Dutch",
        "sv": "Swedish", "pl": "Polish", "ro": "Romanian", "bg": "Bulgarian",
        "hi": "Hindi", "id": "Indonesian", "vi": "Vietnamese", "th": "Thai",
        "cs": "Czech", "da": "Danish", "fi": "Finnish", "no": "Norwegian",
        "hu": "Hungarian", "uk": "Ukrainian",
    };

    function loadHistory() {
        try {
            const raw = localStorage.getItem(HISTORY_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    function saveToHistory(song, langCode) {
        let history = loadHistory();
        history = history.filter((e) => e.id !== song.id);
        const entry = {
            id: song.id,
            title: song.title,
            artist: song.artist,
            lang_code: langCode,
            timestamp: new Date().toLocaleString("en-GB", {
                day: "2-digit", month: "2-digit", year: "numeric",
                hour: "2-digit", minute: "2-digit",
            }),
        };
        history.unshift(entry);
        if (history.length > MAX_HISTORY) {
            history = history.slice(0, MAX_HISTORY);
        }
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {}
    }

    function clearHistory() {
        if (!confirm("Are you sure you want to clear all history?")) return;
        localStorage.removeItem(HISTORY_KEY);
        renderHistory();
    }

    function renderHistory() {
        const history = loadHistory();
        historyList.innerHTML = "";

        if (history.length === 0) {
            historyEmpty.classList.add("visible");
            return;
        }

        historyEmpty.classList.remove("visible");

        history.forEach((entry) => {
            const li = document.createElement("li");
            li.className = "history-item";
            const langName = LANGUAGE_NAMES[entry.lang_code] || entry.lang_code;
            li.innerHTML = `
                <div class="history-title"></div>
                <div class="history-artist"></div>
                <div class="history-meta">
                    <span class="history-lang"></span>
                    <span class="history-time"></span>
                </div>
            `;
            li.querySelector(".history-title").textContent = entry.title;
            li.querySelector(".history-artist").textContent = entry.artist;
            li.querySelector(".history-lang").textContent = langName;
            li.querySelector(".history-time").textContent = entry.timestamp;

            li.addEventListener("click", () => {
                doTranslation(
                    { id: entry.id, title: entry.title, artist: entry.artist },
                    entry.lang_code
                );
            });
            historyList.appendChild(li);
        });
    }

    // ===== SCREEN NAVIGATION =====
    function showWelcomeScreen() {
        closePopup();
        hideLanguageModal();
        translationScreen.classList.remove("active");
        historyScreen.classList.remove("active");
        welcomeScreen.classList.add("active");
        // Clear search input and suggestions when returning home
        searchInput.value = "";
        lastSearchResults = [];
        hideSuggestions();
    }

    function showTranslationScreen() {
        closePopup();
        welcomeScreen.classList.remove("active");
        historyScreen.classList.remove("active");
        translationScreen.classList.add("active");
    }

    function showHistoryScreen() {
        closePopup();
        hideLanguageModal();
        welcomeScreen.classList.remove("active");
        translationScreen.classList.remove("active");
        renderHistory();
        historyScreen.classList.add("active");
    }

    backBtn.addEventListener("click", showWelcomeScreen);
    backFromHistoryBtn.addEventListener("click", showWelcomeScreen);
    logoWrapper.addEventListener("click", (e) => {
        e.stopPropagation();
        showHistoryScreen();
    });
    clearHistoryBtn.addEventListener("click", clearHistory);

    // ===== SEARCH =====
    searchInput.addEventListener("input", () => {
        const query = searchInput.value.trim();
        if (searchTimeout) clearTimeout(searchTimeout);
        if (query.length < 1) {
            hideSuggestions();
            lastSearchResults = [];
            return;
        }
        searchTimeout = setTimeout(() => performSearch(query), 300);
    });

    searchInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            const query = searchInput.value.trim();
            if (query.length >= 1) {
                if (searchTimeout) clearTimeout(searchTimeout);
                performSearch(query);
            }
        }
    });

    async function performSearch(query) {
        currentSearchQuery = query;
        welcomeStatus.textContent = `Searching for "${query}"...`;

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            if (currentSearchQuery !== query) return;

            if (data.error) {
                welcomeStatus.textContent = `Error: ${data.error}`;
                hideSuggestions();
                return;
            }

            lastSearchResults = data.results || [];
            displaySuggestions(lastSearchResults);
        } catch (err) {
            welcomeStatus.textContent = `Network error. Try again.`;
            hideSuggestions();
        }
    }

    function displaySuggestions(results) {
        suggestionsList.innerHTML = "";

        if (results.length === 0) {
            suggestionsList.innerHTML = '<li class="no-results">No results found</li>';
            suggestionsWrapper.classList.add("visible");
            welcomeStatus.textContent = "";
            return;
        }

        results.forEach((song) => {
            const li = document.createElement("li");
            li.className = "suggestion-item";
            li.innerHTML = `
                <div class="suggestion-title"></div>
                <div class="suggestion-artist"></div>
            `;
            li.querySelector(".suggestion-title").textContent = song.title;
            li.querySelector(".suggestion-artist").textContent = song.artist;
            li.addEventListener("click", () => onSongSelected(song));
            suggestionsList.appendChild(li);
        });

        suggestionsWrapper.classList.add("visible");
        welcomeStatus.textContent = `Found ${results.length} results. Tap one.`;
    }

    function hideSuggestions() {
        suggestionsWrapper.classList.remove("visible");
        suggestionsList.innerHTML = "";
        welcomeStatus.textContent = "";
    }

    // ===== SONG SELECTED → SHOW LANGUAGE MODAL =====
    function onSongSelected(song) {
        pendingSong = song;
        modalSongInfo.textContent = `${song.title} — ${song.artist}`;
        // Highlight the user's last used language as a hint
        const lastLang = getLastUsedLang();
        document.querySelectorAll(".modal-lang-btn").forEach((btn) => {
            btn.classList.remove("default-selected");
            if (btn.dataset.lang === lastLang) {
                btn.classList.add("default-selected");
            }
        });
        showLanguageModal();
    }

    function showLanguageModal() {
        languageModal.classList.add("visible");
    }

    function hideLanguageModal() {
        languageModal.classList.remove("visible");
        pendingSong = null;
    }

    modalClose.addEventListener("click", hideLanguageModal);
    languageModal.addEventListener("click", (e) => {
        if (e.target === languageModal) hideLanguageModal();
    });

    // Wire up language buttons in the modal
    document.querySelectorAll(".modal-lang-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const langCode = btn.dataset.lang;
            if (!pendingSong) return;
            const song = pendingSong;
            setLastUsedLang(langCode);  // remember choice
            hideLanguageModal();
            doTranslation(song, langCode);
        });
    });

    // ===== TRANSLATION =====
    async function doTranslation(song, langCode) {
        songInfo.textContent = `${song.title} — ${song.artist}`;
        originalLyrics.innerHTML = '<div class="loader">Fetching lyrics...</div>';
        translatedLyrics.innerHTML = '<div class="loader">Waiting...</div>';
        transStatus.textContent = "";
        closePopup();
        showTranslationScreen();

        try {
            const response = await fetch("/api/translate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    song_id: song.id,
                    lang_code: langCode,
                }),
            });

            const data = await response.json();

            if (data.error) {
                originalLyrics.innerHTML = "";
                const errDiv = document.createElement("div");
                errDiv.className = "loader";
                errDiv.textContent = `Error: ${data.error}`;
                originalLyrics.appendChild(errDiv);
                translatedLyrics.innerHTML = "";
                return;
            }

            songInfo.textContent = `${data.title} — ${data.artist}`;
            renderClickableLyrics(originalLyrics, data.lyrics, langCode);
            renderClickableLyrics(translatedLyrics, data.translation, "en");
            transStatus.textContent = `✓ Translated to ${data.lang_name}  •  Tap any word`;

            saveToHistory(
                { id: song.id, title: data.title, artist: data.artist },
                langCode
            );
        } catch (err) {
            originalLyrics.innerHTML = '<div class="loader">Network error</div>';
            translatedLyrics.innerHTML = "";
        }
    }

    // ===== CLICKABLE WORDS =====
    function renderClickableLyrics(container, text, targetLang) {
        container.innerHTML = "";
        container.dataset.targetLang = targetLang;
        if (!text) return;

        const lines = text.split("\n");
        lines.forEach((line, lineIdx) => {
            if (line.trim() === "") {
                container.appendChild(document.createTextNode("\n"));
                return;
            }

            const tokens = line.split(/(\s+)/);
            tokens.forEach((token) => {
                if (/^\s+$/.test(token)) {
                    container.appendChild(document.createTextNode(token));
                } else if (token) {
                    const span = document.createElement("span");
                    span.className = "lyrics-word";
                    span.textContent = token;
                    span.addEventListener("click", (e) => handleWordClick(e, span));
                    container.appendChild(span);
                }
            });

            if (lineIdx < lines.length - 1) {
                container.appendChild(document.createTextNode("\n"));
            }
        });
    }

    function cleanWord(word) {
        return word.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, "").trim();
    }

    let currentPopup = null;
    let currentSelectedWord = null;

    async function handleWordClick(event, wordSpan) {
        event.stopPropagation();

        const rawWord = wordSpan.textContent;
        const clean = cleanWord(rawWord);
        if (!clean) return;

        if (currentSelectedWord) {
            currentSelectedWord.classList.remove("selected");
        }
        wordSpan.classList.add("selected");
        currentSelectedWord = wordSpan;

        const container = wordSpan.parentElement;
        const targetLang = container.dataset.targetLang || "en";

        closePopup();
        const popup = createPopup(wordSpan, clean);
        currentPopup = popup;

        try {
            const response = await fetch("/api/translate-word", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ word: clean, lang_code: targetLang }),
            });
            const data = await response.json();

            if (!document.body.contains(popup)) return;

            const translationEl = popup.querySelector(".popup-translation");
            if (data.error) {
                translationEl.textContent = "(translation failed)";
            } else {
                translationEl.textContent = data.translation || "(no result)";
            }
            translationEl.classList.remove("popup-loading");

            setTimeout(() => {
                if (currentPopup === popup) closePopup();
            }, 5000);
        } catch (err) {
            const translationEl = popup.querySelector(".popup-translation");
            if (translationEl) {
                translationEl.textContent = "(network error)";
                translationEl.classList.remove("popup-loading");
            }
        }
    }

    function createPopup(anchor, word) {
        const popup = document.createElement("div");
        popup.className = "word-popup";
        popup.innerHTML = `
            <span class="popup-close">✕</span>
            <div class="popup-original"></div>
            <div class="popup-translation popup-loading">Translating...</div>
        `;
        popup.querySelector(".popup-original").textContent = word;
        document.body.appendChild(popup);
        positionPopup(popup, anchor);

        popup.querySelector(".popup-close").addEventListener("click", (e) => {
            e.stopPropagation();
            closePopup();
        });

        return popup;
    }

    function positionPopup(popup, anchor) {
        const rect = anchor.getBoundingClientRect();
        const popupRect = popup.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        let left = rect.left + (rect.width / 2) - (popupRect.width / 2);
        let top = rect.bottom + 8;

        if (left < 8) left = 8;
        if (left + popupRect.width > vw - 8) {
            left = vw - popupRect.width - 8;
        }
        if (top + popupRect.height > vh - 8) {
            top = rect.top - popupRect.height - 8;
        }
        if (top < 8) top = 8;

        popup.style.left = `${left}px`;
        popup.style.top = `${top}px`;
    }

    function closePopup() {
        if (currentPopup && document.body.contains(currentPopup)) {
            currentPopup.remove();
        }
        currentPopup = null;
        if (currentSelectedWord) {
            currentSelectedWord.classList.remove("selected");
            currentSelectedWord = null;
        }
    }

    document.addEventListener("click", (e) => {
        if (currentPopup &&
            !currentPopup.contains(e.target) &&
            !e.target.classList.contains("lyrics-word")) {
            closePopup();
        }
    });

    [originalLyrics, translatedLyrics].forEach((box) => {
        if (box) box.addEventListener("scroll", closePopup);
    });

    document.addEventListener("click", (e) => {
        if (!suggestionsWrapper.contains(e.target) && e.target !== searchInput) {
            if (!searchInput.value.trim()) {
                hideSuggestions();
            }
        }
    });
}
