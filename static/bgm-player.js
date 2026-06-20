/**
 * BGM Player - Background Music for MovieMusicMatcher
 * =====================================================
 * HTML5 Audio singleton + floating player UI + settings modal
 * Per-user playlist storage via localStorage (no cross-user conflict)
 * Admin default playlist fetched from server API
 */

// ============================================================
// HTML5 AUDIO ENGINE (Singleton)
// ============================================================
const BGMAudio = (function () {
    let audio = null;
    let playlist = []; // merged (admin + personal)
    let adminPlaylist = [];
    let currentIndex = -1;
    let isPlaying = false;
    let _shuffle = false;
    let _volume = 0.5;
    let _enabled = true;
    let _gestureUnlocked = false;
    let _updateTimer = null;
    let _listeners = []; // state change listeners for UI

    function _notify() {
        const state = getState();
        _listeners.forEach(fn => { try { fn(state); } catch (e) {} });
    }

    function _saveSettings() {
        try {
            localStorage.setItem("mmw_bgm_volume", String(_volume));
            localStorage.setItem("mmw_bgm_shuffle", _shuffle ? "true" : "false");
            localStorage.setItem("mmw_bgm_enabled", _enabled ? "true" : "false");
            if (currentIndex >= 0) {
                localStorage.setItem("mmw_bgm_last_index", String(currentIndex));
            }
        } catch (e) { /* quota exceeded or private mode */ }
    }

    function _loadSettings() {
        try {
            const v = localStorage.getItem("mmw_bgm_volume");
            if (v !== null) _volume = parseFloat(v) || 0.5;
            _shuffle = localStorage.getItem("mmw_bgm_shuffle") === "true";
            _enabled = localStorage.getItem("mmw_bgm_enabled") !== "false";
        } catch (e) { /* ignore */ }
    }

    function _nextIndex() {
        if (playlist.length === 0) return -1;
        if (_shuffle) {
            const idx = Math.floor(Math.random() * playlist.length);
            // Avoid repeating same song if >1 song
            if (playlist.length > 1 && idx === currentIndex) {
                return (idx + 1) % playlist.length;
            }
            return idx;
        }
        return (currentIndex + 1) % playlist.length;
    }

    function _prevIndex() {
        if (playlist.length === 0) return -1;
        if (_shuffle) {
            return Math.floor(Math.random() * playlist.length);
        }
        return (currentIndex - 1 + playlist.length) % playlist.length;
    }

    function _onEnded() {
        next();
    }

    function _onError() {
        console.warn("[BGM] Error loading:", playlist[currentIndex]?.url);
        // Skip to next after error
        setTimeout(() => next(), 500);
    }

    function _onCanPlay() {
        _notify();
    }

    function init() {
        if (audio) return;
        _loadSettings();

        audio = new Audio();
        audio.volume = _volume;
        audio.preload = "none";
        audio.addEventListener("ended", _onEnded);
        audio.addEventListener("error", _onError);
        audio.addEventListener("canplay", _onCanPlay);
        audio.addEventListener("timeupdate", _notify);
        audio.addEventListener("play", () => { isPlaying = true; _notify(); });
        audio.addEventListener("pause", () => { isPlaying = false; _notify(); });

        // Unlock audio on first user gesture
        function unlockGesture() {
            if (!_gestureUnlocked) {
                _gestureUnlocked = true;
                document.removeEventListener("click", unlockGesture);
                document.removeEventListener("keydown", unlockGesture);
                document.removeEventListener("touchstart", unlockGesture);
                // If there's a queued play request, execute it
                if (_enabled && playlist.length > 0 && currentIndex < 0) {
                    play(0);
                }
            }
        }
        document.addEventListener("click", unlockGesture, { once: false });
        document.addEventListener("keydown", unlockGesture, { once: false });
        document.addEventListener("touchstart", unlockGesture, { once: false });
    }

    function setPlaylist(adminSongs, personalSongs) {
        adminPlaylist = adminSongs || [];
        const personal = personalSongs || loadPersonalPlaylist();
        playlist = [...adminPlaylist, ...personal];
        if (playlist.length > 0 && currentIndex < 0) {
            // Restore last index if available
            try {
                const lastIdx = parseInt(localStorage.getItem("mmw_bgm_last_index") || "-1");
                if (lastIdx >= 0 && lastIdx < playlist.length) {
                    currentIndex = lastIdx;
                }
            } catch (e) { /* ignore */ }
        }
        _notify();
    }

    function play(index) {
        if (!_gestureUnlocked) {
            // Will auto-play after first gesture via unlockGesture
            if (typeof index === "number") currentIndex = index;
            _notify();
            return;
        }
        if (playlist.length === 0) return;
        if (typeof index === "number" && index >= 0 && index < playlist.length) {
            currentIndex = index;
        }
        if (currentIndex < 0 || currentIndex >= playlist.length) {
            currentIndex = 0;
        }
        const song = playlist[currentIndex];
        if (!song || !song.url) {
            console.warn("[BGM] No valid URL for song:", song);
            next();
            return;
        }
        if (audio.src !== song.url) {
            audio.src = song.url;
        }
        audio.volume = _volume;
        const promise = audio.play();
        if (promise) {
            promise.catch(e => {
                console.warn("[BGM] Play blocked:", e.message);
                // Browser blocked autoplay; will retry on next gesture
            });
        }
        _saveSettings();
        _notify();
    }

    function pause() {
        if (audio) audio.pause();
        _saveSettings();
    }

    function toggle() {
        if (isPlaying) {
            pause();
        } else {
            play();
        }
    }

    function next() {
        const idx = _nextIndex();
        if (idx >= 0) play(idx);
    }

    function prev() {
        const idx = _prevIndex();
        if (idx >= 0) play(idx);
    }

    function setVolume(v) {
        _volume = Math.max(0, Math.min(1, v));
        if (audio) audio.volume = _volume;
        _saveSettings();
        _notify();
    }

    function toggleShuffle() {
        _shuffle = !_shuffle;
        _saveSettings();
        _notify();
    }

    function seek(seconds) {
        if (audio && audio.duration) {
            audio.currentTime = Math.max(0, Math.min(seconds, audio.duration));
        }
    }

    function setEnabled(enabled) {
        _enabled = enabled;
        if (!enabled) {
            pause();
        } else if (playlist.length > 0 && currentIndex < 0) {
            play(0);
        }
        _saveSettings();
        _notify();
    }

    function getState() {
        const song = (currentIndex >= 0 && currentIndex < playlist.length) ? playlist[currentIndex] : null;
        return {
            isPlaying,
            currentIndex,
            currentTime: audio ? audio.currentTime : 0,
            duration: (audio && audio.duration && isFinite(audio.duration)) ? audio.duration : 0,
            volume: _volume,
            shuffleMode: _shuffle,
            enabled: _enabled,
            gestureUnlocked: _gestureUnlocked,
            playlistLength: playlist.length,
            currentSong: song,
            isAdminSong: song ? adminPlaylist.includes(song) : false,
        };
    }

    function onStateChange(fn) {
        _listeners.push(fn);
    }

    function getAdminPlaylist() { return adminPlaylist; }

    return {
        init, setPlaylist, play, pause, toggle, next, prev,
        setVolume, toggleShuffle, seek, setEnabled, getState,
        onStateChange, getAdminPlaylist,
        get isPlaying() { return isPlaying; },
        get volume() { return _volume; },
        get shuffleMode() { return _shuffle; },
        get enabled() { return _enabled; },
    };
})();


// ============================================================
// LOCAL STORAGE HELPERS
// ============================================================
function loadPersonalPlaylist() {
    try {
        const raw = localStorage.getItem("mmw_bgm_personal");
        return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
}

function savePersonalPlaylist(list) {
    try {
        localStorage.setItem("mmw_bgm_personal", JSON.stringify(list));
    } catch (e) { /* quota exceeded */ }
}

function loadExternalLinks() {
    try {
        const raw = localStorage.getItem("mmw_bgm_external");
        return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
}

function saveExternalLinks(list) {
    try {
        localStorage.setItem("mmw_bgm_external", JSON.stringify(list));
    } catch (e) { /* quota exceeded */ }
}

function isAdmin() {
    return typeof adminKey !== "undefined" && !!adminKey;
}

function adminHeaders() {
    if (typeof adminKey !== "undefined" && adminKey) {
        return { "X-Admin-Key": adminKey };
    }
    return {};
}


// ============================================================
// FETCH ADMIN PLAYLIST
// ============================================================
async function fetchAdminPlaylist() {
    try {
        const resp = await fetch("/api/bgm/playlist");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        return data.playlist || [];
    } catch (e) {
        console.warn("[BGM] Failed to fetch admin playlist:", e.message);
        return [];
    }
}


// ============================================================
// UI CONTROLLER
// ============================================================
(function initBGMUI() {
    // DOM refs
    const widget = document.getElementById("bgmPlayerWidget");
    const toggleBtn = document.getElementById("bgmPlayerToggle");
    const body = document.getElementById("bgmPlayerBody");
    const titleEl = document.getElementById("bgmPlayerTitle");
    const sourceEl = document.getElementById("bgmPlayerSource");
    const progressBar = document.getElementById("bgmProgressBar");
    const progressFill = document.getElementById("bgmProgressFill");
    const playBtn = document.getElementById("bgmPlayBtn");
    const prevBtn = document.getElementById("bgmPrevBtn");
    const nextBtn = document.getElementById("bgmNextBtn");
    const shuffleBtn = document.getElementById("bgmShuffleBtn");
    const volumeSlider = document.getElementById("bgmVolumeSlider");
    const settingsBtn = document.getElementById("bgmSettingsBtn");
    const navBtn = document.getElementById("bgmNavBtn");

    // Settings modal refs
    const settingsModal = document.getElementById("bgmSettingsModal");
    const settingsClose = document.getElementById("bgmSettingsClose");
    const tabBtns = document.querySelectorAll(".bgm-tab");
    const tabPanels = document.querySelectorAll(".bgm-tab-panel");
    const adminSongList = document.getElementById("bgmAdminSongList");
    const adminEmpty = document.getElementById("bgmAdminEmpty");
    const adminForm = document.getElementById("bgmAdminForm");
    const adminAddBtn = document.getElementById("bgmAdminAddBtn");
    const personalSongList = document.getElementById("bgmPersonalSongList");
    const personalEmpty = document.getElementById("bgmPersonalEmpty");
    const personalAddBtn = document.getElementById("bgmPersonalAddBtn");
    const externalLinksList = document.getElementById("bgmExternalLinksList");
    const externalAddBtn = document.getElementById("bgmExternalAddBtn");

    // State
    let isExpanded = false;

    // ---- Expand / Collapse ----
    function expand() {
        if (!widget) return;
        widget.classList.add("expanded");
        isExpanded = true;
    }

    function collapse() {
        if (!widget) return;
        widget.classList.remove("expanded");
        isExpanded = false;
    }

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            if (isExpanded) collapse(); else expand();
        });
    }

    if (navBtn) {
        navBtn.addEventListener("click", () => {
            if (!widget || widget.style.display === "none") return;
            if (isExpanded) collapse(); else expand();
        });
    }

    // ---- Progress bar click ----
    if (progressBar) {
        progressBar.addEventListener("click", (e) => {
            if (!progressBar.clientWidth) return;
            const rect = progressBar.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            const state = BGMAudio.getState();
            if (state.duration > 0) {
                BGMAudio.seek(pct * state.duration);
            }
        });
    }

    // ---- Playback controls ----
    if (playBtn) playBtn.addEventListener("click", () => BGMAudio.toggle());
    if (prevBtn) prevBtn.addEventListener("click", () => BGMAudio.prev());
    if (nextBtn) nextBtn.addEventListener("click", () => BGMAudio.next());
    if (shuffleBtn) {
        shuffleBtn.addEventListener("click", () => BGMAudio.toggleShuffle());
    }
    if (volumeSlider) {
        volumeSlider.addEventListener("input", () => {
            BGMAudio.setVolume(parseInt(volumeSlider.value) / 100);
        });
    }

    // ---- Settings modal ----
    function openSettings() {
        if (!settingsModal) return;
        settingsModal.style.display = "flex";
        refreshAdminTab();
        refreshPersonalTab();
        refreshExternalTab();
        updateAdminFormVisibility();
        // Default to admin tab
        switchTab("admin");
    }

    function closeSettings() {
        if (!settingsModal) return;
        settingsModal.style.display = "none";
    }

    if (settingsBtn) settingsBtn.addEventListener("click", openSettings);
    if (settingsClose) settingsClose.addEventListener("click", closeSettings);
    if (settingsModal) {
        settingsModal.addEventListener("click", (e) => {
            if (e.target === settingsModal) closeSettings();
        });
    }

    // Tab switching
    function switchTab(tabName) {
        tabBtns.forEach(b => {
            b.classList.toggle("active", b.getAttribute("data-bgm-tab") === tabName);
        });
        tabPanels.forEach(p => {
            p.classList.toggle("active", p.id === "bgmPanel" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
        });
    }
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            switchTab(btn.getAttribute("data-bgm-tab"));
        });
    });

    // ---- Admin Tab ----
    function updateAdminFormVisibility() {
        if (adminForm) {
            adminForm.style.display = isAdmin() ? "block" : "none";
        }
    }

    async function refreshAdminTab() {
        const songs = await fetchAdminPlaylist();
        if (adminSongList) {
            if (songs.length === 0) {
                adminSongList.innerHTML = "";
                if (adminEmpty) adminEmpty.style.display = "block";
            } else {
                if (adminEmpty) adminEmpty.style.display = "none";
                adminSongList.innerHTML = songs.map((s, i) => renderSongItem(s, i, "admin")).join("");
            }
        }
    }

    if (adminAddBtn) {
        adminAddBtn.addEventListener("click", async () => {
            const titleEl = document.getElementById("bgmAdminTitle");
            const urlEl = document.getElementById("bgmAdminUrl");
            const title = (titleEl?.value || "").trim();
            const url = (urlEl?.value || "").trim();
            if (!title) { alert(_t("bgm.titleRequired")); return; }
            if (!url) { alert(_t("bgm.urlRequired")); return; }

            try {
                const resp = await fetch("/api/bgm/playlist", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", ...adminHeaders() },
                    body: JSON.stringify({ title, url }),
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    alert(err.error || "Failed to add song");
                    return;
                }
                if (titleEl) titleEl.value = "";
                if (urlEl) urlEl.value = "";
                await refreshAdminTab();
                // Reload playlist
                await loadAndSetPlaylist();
            } catch (e) {
                alert("Failed to add song: " + e.message);
            }
        });
    }

    // ---- Personal Tab ----
    function refreshPersonalTab() {
        const songs = loadPersonalPlaylist();
        if (personalSongList) {
            if (songs.length === 0) {
                personalSongList.innerHTML = "";
                if (personalEmpty) personalEmpty.style.display = "block";
            } else {
                if (personalEmpty) personalEmpty.style.display = "none";
                personalSongList.innerHTML = songs.map((s, i) => renderSongItem(s, i, "personal")).join("");
            }
        }
    }

    if (personalAddBtn) {
        personalAddBtn.addEventListener("click", () => {
            const titleEl = document.getElementById("bgmPersonalTitle");
            const urlEl = document.getElementById("bgmPersonalUrl");
            const title = (titleEl?.value || "").trim();
            const url = (urlEl?.value || "").trim();
            if (!title) { alert(_t("bgm.titleRequired")); return; }
            if (!url) { alert(_t("bgm.urlRequired")); return; }

            const songs = loadPersonalPlaylist();
            songs.push({
                id: "p_" + Date.now().toString(36),
                title,
                url,
                added_at: new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
            });
            savePersonalPlaylist(songs);
            if (titleEl) titleEl.value = "";
            if (urlEl) urlEl.value = "";
            refreshPersonalTab();
            loadAndSetPlaylist();
        });
    }

    // ---- External Links Tab ----
    function refreshExternalTab() {
        const links = loadExternalLinks();
        if (externalLinksList) {
            externalLinksList.innerHTML = links.map((l, i) => renderExternalLinkItem(l, i)).join("");
        }
    }

    if (externalAddBtn) {
        externalAddBtn.addEventListener("click", () => {
            const platEl = document.getElementById("bgmExternalPlatform");
            const titleEl = document.getElementById("bgmExternalTitle");
            const urlEl = document.getElementById("bgmExternalUrl");
            const platform = platEl?.value || "netease";
            const title = (titleEl?.value || "").trim();
            const url = (urlEl?.value || "").trim();
            if (!title) { alert(_t("bgm.titleRequired")); return; }
            if (!url) { alert(_t("bgm.urlRequired")); return; }

            const links = loadExternalLinks();
            links.push({ platform, title, url });
            saveExternalLinks(links);
            if (titleEl) titleEl.value = "";
            if (urlEl) urlEl.value = "";
            refreshExternalTab();
        });
    }

    // ---- Render helpers ----
    function renderSongItem(song, index, source) {
        const isAdminSong = source === "admin";
        const canDelete = (isAdminSong && isAdmin()) || (!isAdminSong);
        const deleteBtn = canDelete
            ? `<button class="btn-xs btn-delete" onclick="bgmRemoveSong('${source}', '${song.id}', ${index})" data-i18n="bgm.remove">Remove</button>`
            : "";
        const playBtnHtml = `<button class="btn-xs btn-primary" onclick="bgmPlaySong('${source}', ${index})" data-i18n="bgm.play">Play</button>`;
        const sourceLabel = isAdminSong ? _t("bgm.sourceAdmin") : _t("bgm.sourcePersonal");

        return `
            <div class="bgm-song-item" data-song-id="${escapeHTML(song.id)}">
                <span class="bgm-song-index">${index + 1}</span>
                <div class="bgm-song-info">
                    <span class="bgm-song-title">${escapeHTML(song.title)}</span>
                    <span class="bgm-song-url">${escapeHTML(song.url)} <small>[${sourceLabel}]</small></span>
                </div>
                <div class="bgm-song-actions">
                    ${playBtnHtml}
                    ${deleteBtn}
                </div>
            </div>`;
    }

    function renderExternalLinkItem(link, index) {
        const platformNames = { netease: _t("bgm.platformNetease"), qq: _t("bgm.platformQQ"), kugou: _t("bgm.platformKugou") };
        const platName = platformNames[link.platform] || link.platform;
        return `
            <div class="bgm-ext-link-item">
                <span class="bgm-ext-platform-icon" style="font-size:0.75rem;">${platName}</span>
                <span class="bgm-ext-title">${escapeHTML(link.title)}</span>
                <button class="btn-xs btn-primary" onclick="window.open('${escapeHTML(link.url)}', '_blank')">&#8599;</button>
                <button class="btn-xs btn-delete" onclick="bgmRemoveExternal(${index})" data-i18n="bgm.remove">Remove</button>
            </div>`;
    }

    // ---- Global functions for onclick handlers ----
    window.bgmPlaySong = function (source, index) {
        const songs = source === "admin" ? BGMAudio.getAdminPlaylist() : loadPersonalPlaylist();
        // Find the song in merged playlist
        const song = (source === "admin" ? BGMAudio.getAdminPlaylist() : loadPersonalPlaylist())[index];
        if (!song) return;
        const state = BGMAudio.getState();
        const mergedIdx = findSongInPlaylist(song);
        if (mergedIdx >= 0) {
            BGMAudio.play(mergedIdx);
        }
        closeSettings();
    };

    window.bgmRemoveSong = function (source, songId, index) {
        if (!confirm(_t("bgm.deleteConfirm"))) return;
        if (source === "admin") {
            // Admin delete via API
            fetch("/api/bgm/playlist/" + songId, {
                method: "DELETE",
                headers: adminHeaders(),
            }).then(r => {
                if (r.ok) {
                    refreshAdminTab();
                    loadAndSetPlaylist();
                }
            });
        } else {
            const songs = loadPersonalPlaylist();
            songs.splice(index, 1);
            savePersonalPlaylist(songs);
            refreshPersonalTab();
            loadAndSetPlaylist();
        }
    };

    window.bgmRemoveExternal = function (index) {
        if (!confirm(_t("bgm.deleteConfirm"))) return;
        const links = loadExternalLinks();
        links.splice(index, 1);
        saveExternalLinks(links);
        refreshExternalTab();
    };

    function findSongInPlaylist(song) {
        const state = BGMAudio.getState();
        // Reconstruct merged playlist
        const personal = loadPersonalPlaylist();
        const merged = [...BGMAudio.getAdminPlaylist(), ...personal];
        return merged.findIndex(s => s.id === song.id && s.url === song.url);
    }

    // ---- State-driven UI updates ----
    BGMAudio.onStateChange((state) => {
        if (!widget) return;

        // Show/hide widget
        if (state.playlistLength > 0 && state.enabled) {
            widget.style.display = "flex";
        } else if (state.playlistLength === 0) {
            widget.style.display = "none";
        }

        // Playing class for pulse animation
        widget.classList.toggle("playing", state.isPlaying);

        // Title & source
        if (state.currentSong) {
            if (titleEl) titleEl.textContent = state.currentSong.title;
            if (sourceEl) {
                sourceEl.textContent = state.isAdminSong ? _t("bgm.sourceAdmin") : _t("bgm.sourcePersonal");
            }
        } else if (state.playlistLength > 0) {
            if (titleEl) titleEl.textContent = _t("bgm.clickToStart");
            if (sourceEl) sourceEl.textContent = "";
        } else {
            if (titleEl) titleEl.textContent = _t("bgm.noSongs");
            if (sourceEl) sourceEl.textContent = "";
        }

        // Play/Pause button
        if (playBtn) {
            playBtn.innerHTML = state.isPlaying ? "&#10074;&#10074;" : "&#9654;";
        }

        // Progress bar
        if (progressFill && state.duration > 0) {
            const pct = (state.currentTime / state.duration) * 100;
            progressFill.style.width = Math.min(100, Math.max(0, pct)) + "%";
        } else if (progressFill) {
            progressFill.style.width = "0%";
        }

        // Shuffle button
        if (shuffleBtn) {
            shuffleBtn.classList.toggle("active", state.shuffleMode);
        }

        // Volume slider
        if (volumeSlider) {
            const volPct = Math.round(state.volume * 100);
            if (String(volumeSlider.value) !== String(volPct)) {
                volumeSlider.value = volPct;
            }
        }

        // Nav button active
        if (navBtn) {
            navBtn.classList.toggle("active", state.isPlaying);
        }
    });

    // ---- Initialize ----
    async function loadAndSetPlaylist() {
        const adminSongs = await fetchAdminPlaylist();
        const personalSongs = loadPersonalPlaylist();
        BGMAudio.setPlaylist(adminSongs, personalSongs);

        // Auto-start if enabled
        const state = BGMAudio.getState();
        if (state.enabled && state.playlistLength > 0 && !state.isPlaying && state.currentIndex < 0) {
            // Queue play after gesture unlock
            setTimeout(() => BGMAudio.play(0), 100);
        }
    }

    // Make loadAndSetPlaylist globally accessible for admin operations
    window.bgmReloadPlaylist = loadAndSetPlaylist;

    // Start
    BGMAudio.init();
    loadAndSetPlaylist();

    // Re-check admin form visibility when admin state might change
    // Poll for adminKey changes (suggestions login/logout)
    const _origAdminLogin = window.adminLogin;
    const _origAdminLogout = window.adminLogout;
    if (typeof window.adminLogin === "function") {
        const orig = window.adminLogin;
        window.adminLogin = function () {
            const result = orig.apply(this, arguments);
            updateAdminFormVisibility();
            refreshAdminTab();
            return result;
        };
    }
    if (typeof window.adminLogout === "function") {
        const orig = window.adminLogout;
        window.adminLogout = function () {
            const result = orig.apply(this, arguments);
            updateAdminFormVisibility();
            refreshAdminTab();
            return result;
        };
    }

    // ESC key to close settings
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && settingsModal && settingsModal.style.display === "flex") {
            closeSettings();
        }
    });

    console.log("[BGM] Player initialized. Gesture unlocked:", BGMAudio.getState().gestureUnlocked);
})();


// ============================================================
// UTILITY
// ============================================================
function escapeHTML(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function _t(key) {
    // Use the global I18N instance if available, else return key
    if (typeof I18N !== "undefined" && I18N._current) {
        return I18N._current[key] || key;
    }
    return key;
}
