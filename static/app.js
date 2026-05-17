// ===== JELLI WEB - FRONTEND LOGIC =====

const welcomeScreen = document.getElementById("welcomeScreen");
const translationScreen = document.getElementById("translationScreen");
const searchInput = document.getElementById("searchInput");
const langSelect = document.getElementById("langSelect");
const suggestionsWrapper = document.getElementById("suggestionsWrapper");
const suggestionsList = document.getElementById("suggestionsList");
const welcomeStatus = document.getElementById("welcomeStatus");
const backBtn = document.getElementById("backBtn");
const songInfo = document.getElementById("songInfo");
const originalLyrics = document.getElementById("originalLyrics");
const translatedLyrics = document.getElementById("translatedLyrics");
const transStatus = document.getElementById("transStatus");
const logoImg = document.getElementById("logoImg");

let searchTimeout = null;
let currentSearchQuery = "";

// ===== SCREEN NAVIGATION =====
function showWelcomeScreen() {
    translationScreen.classList.remove("active");
    welcomeScreen.classList.add("active");
}

function showTranslationScreen() {
    welcomeScreen.classList.remove("active");
    translationScreen.classList.add("active");
}

backBtn.addEventListener("click", showWelcomeScreen);

// ===== SEARCH =====
searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim();

    // Clear previous timeout
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }

    // Hide suggestions if too short
    if (query.length < 1) {
        hideSuggestions();
        return;
    }

    // Debounce: wait 300ms after the user stops typing
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

        // Make sure the query is still current (user might have typed more)
        if (currentSearchQuery !== query) return;

        if (data.error) {
            welcomeStatus.textContent = `Error: ${data.error}`;
            hideSuggestions();
            return;
        }

        displaySuggestions(data.results || []);
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
            <div class="suggestion-title">${escapeHTML(song.title)}</div>
            <div class="suggestion-artist">${escapeHTML(song.artist)}</div>
        `;
        li.addEventListener("click", () => selectSong(song));
        suggestionsList.appendChild(li);
    });

    suggestionsWrapper.classList.add("visible");
    welcomeStatus.textContent = `Found ${results.length} results. Tap one to translate.`;
}

function hideSuggestions() {
    suggestionsWrapper.classList.remove("visible");
    suggestionsList.innerHTML = "";
    welcomeStatus.textContent = "";
}

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ===== TRANSLATION =====
async function selectSong(song) {
    const langCode = langSelect.value;

    // Switch screens immediately with loading state
    songInfo.textContent = `${song.title} — ${song.artist}`;
    originalLyrics.innerHTML = '<div class="loader">Fetching lyrics...</div>';
    translatedLyrics.innerHTML = '<div class="loader">Waiting...</div>';
    transStatus.textContent = "";
    showTranslationScreen();

    try {
        const response = await fetch("/api/translate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                song_id: song.id,
                title: song.title,
                artist: song.artist,
                lang_code: langCode,
            }),
        });

        const data = await response.json();

        if (data.error) {
            originalLyrics.innerHTML = `<div class="loader">Error: ${escapeHTML(data.error)}</div>`;
            translatedLyrics.innerHTML = "";
            return;
        }

        songInfo.textContent = `${data.title} — ${data.artist}`;
        originalLyrics.textContent = data.lyrics;
        translatedLyrics.textContent = data.translation;
        transStatus.textContent = `✓ Translated to ${data.lang_name}`;
    } catch (err) {
        originalLyrics.innerHTML = '<div class="loader">Network error</div>';
        translatedLyrics.innerHTML = "";
    }
}

// ===== HIDE SUGGESTIONS ON OUTSIDE CLICK =====
document.addEventListener("click", (e) => {
    if (!suggestionsWrapper.contains(e.target) && e.target !== searchInput) {
        // Don't hide if input has content
        if (!searchInput.value.trim()) {
            hideSuggestions();
        }
    }
});
