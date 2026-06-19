/**
 * Movie Music Matcher - 前端交互逻辑
 */

// ============================================
// 🌐 国际化 (i18n) 引擎
// ============================================

const I18N = {
    _locale: null,
    _fallbackLocale: null,
    _currentLang: "zh-CN",

    /** 初始化：加载语言包，从 localStorage 读取偏好 */
    async init() {
        // 从 localStorage 读取语言偏好
        const saved = localStorage.getItem("mmw_lang");
        if (saved === "en" || saved === "en-US") {
            this._currentLang = "en-US";
        } else {
            this._currentLang = "zh-CN";
        }

        // 加载语言包
        try {
            const resp = await fetch(`/static/locales/${this._currentLang}.json`);
            this._locale = await resp.json();
        } catch (err) {
            console.warn("加载语言包失败，使用回退:", err.message);
            this._locale = null;
        }

        // 加载回退语言包（用于键不存在时）
        try {
            if (this._currentLang === "en-US") {
                const resp = await fetch("/static/locales/zh-CN.json");
                this._fallbackLocale = await resp.json();
            } else {
                const resp = await fetch("/static/locales/en-US.json");
                this._fallbackLocale = await resp.json();
            }
        } catch (err) {
            this._fallbackLocale = null;
        }

        this._applyToDOM();
        this._updateLangToggle();
        this._updateHTML();
    },

    /** 切换语言 */
    async switchLanguage() {
        const newLang = this._currentLang === "zh-CN" ? "en-US" : "zh-CN";

        // 加载新语言包
        try {
            const resp = await fetch(`/static/locales/${newLang}.json`);
            this._locale = await resp.json();
        } catch (err) {
            console.warn("加载语言包失败:", err.message);
            return;
        }

        this._currentLang = newLang;
        localStorage.setItem("mmw_lang", newLang === "en-US" ? "en" : "zh");

        this._applyToDOM();
        this._updateLangToggle();
        this._updateHTML();
    },

    /** 获取翻译文本 */
    t(key) {
        if (this._locale) {
            const val = this._getNested(this._locale, key);
            if (val !== undefined) return val;
        }
        if (this._fallbackLocale) {
            const val = this._getNested(this._fallbackLocale, key);
            if (val !== undefined) return val;
        }
        // 返回 key 本身作为兜底
        const parts = key.split(".");
        return parts[parts.length - 1];
    },

    /** 获取嵌套对象值 */
    _getNested(obj, path) {
        const parts = path.split(".");
        let current = obj;
        for (const part of parts) {
            if (current == null || typeof current !== "object") return undefined;
            current = current[part];
        }
        return current;
    },

    /** 将翻译应用到 DOM */
    _applyToDOM() {
        // data-i18n: 设置 textContent
        document.querySelectorAll("[data-i18n]").forEach(el => {
            const key = el.getAttribute("data-i18n");
            if (key) {
                el.textContent = this.t(key);
            }
        });

        // data-i18n-placeholder: 设置 placeholder
        document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
            const key = el.getAttribute("data-i18n-placeholder");
            if (key) {
                el.placeholder = this.t(key);
            }
        });

        // data-i18n-title: 设置 title
        document.querySelectorAll("[data-i18n-title]").forEach(el => {
            const key = el.getAttribute("data-i18n-title");
            if (key) {
                el.title = this.t(key);
            }
        });
    },

    /** 更新语言切换按钮 */
    _updateLangToggle() {
        const label = document.getElementById("langToggleLabel");
        if (label) {
            label.textContent = this._currentLang === "zh-CN" ? "EN" : "中";
        }
        const btn = document.getElementById("langToggleBtn");
        if (btn) {
            btn.title = this._currentLang === "zh-CN"
                ? "Switch to English"
                : "切换到中文";
        }
    },

    /** 更新 HTML 根元素 */
    _updateHTML() {
        document.documentElement.lang = this._currentLang;
    }
};

// 便捷 t() 函数
function t(key) {
    return I18N.t(key);
}

// ============================================

// ---- DOM 元素 ----
const videoUploadBox = document.getElementById("videoUploadBox");
const audioUploadBox = document.getElementById("audioUploadBox");
const videoInput = document.getElementById("videoInput");
const audioInput = document.getElementById("audioInput");
const videoFileInfo = document.getElementById("videoFileInfo");
const audioFileInfo = document.getElementById("audioFileInfo");
const startBtn = document.getElementById("startBtn");
const progressSection = document.getElementById("progressSection");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const progressPercent = document.getElementById("progressPercent");
const resultSection = document.getElementById("resultSection");
const errorBox = document.getElementById("errorBox");
const steps = document.querySelectorAll(".step");

// ---- 教程弹窗 ----
const tutorialBtn = document.getElementById("tutorialBtn");
const tutorialModal = document.getElementById("tutorialModal");
const tutorialClose = document.getElementById("tutorialClose");
const tutorialContent = document.getElementById("tutorialContent");
let tutorialLoaded = false;

async function loadTutorial() {
    if (tutorialLoaded) return;
    try {
        const resp = await fetch("/api/tutorial");
        const data = await resp.json();
        tutorialContent.innerHTML = data.html;
        tutorialLoaded = true;
    } catch (err) {
        tutorialContent.innerHTML =
            `<p style="color:var(--error)">${t("tutorial.loadFailed")}: ${err.message}</p>`;
    }
}

tutorialBtn.addEventListener("click", () => {
    tutorialModal.style.display = "flex";
    loadTutorial();
});
tutorialClose.addEventListener("click", () => {
    tutorialModal.style.display = "none";
});
tutorialModal.addEventListener("click", (e) => {
    if (e.target === tutorialModal) {
        tutorialModal.style.display = "none";
    }
});
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && tutorialModal.style.display === "flex") {
        tutorialModal.style.display = "none";
    }
});

let videoFile = null;
let audioFiles = [];
let editingMode = "video_first";
let customExportPath = "";

// ---- 剪辑模式选择 (V2) ----
document.querySelectorAll("#editingModeSection .mode-card").forEach(card => {
    card.addEventListener("click", () => {
        document.querySelectorAll("#editingModeSection .mode-card")
            .forEach(c => c.classList.remove("active"));
        card.classList.add("active");
        editingMode = card.dataset.mode;
        console.log("[Mode] Switched to:", editingMode);
    });
});

// ---- 导出路径设置 ----
const exportPathToggle = document.getElementById("exportPathToggle");
const exportPathBody = document.getElementById("exportPathBody");
const exportPathArrow = document.getElementById("exportPathArrow");
const exportPathInput = document.getElementById("exportPathInput");
const exportPathHint = document.getElementById("exportPathHint");
const resetExportPathBtn = document.getElementById("resetExportPathBtn");
const pickExportPathBtn = document.getElementById("pickExportPathBtn");
const exportPathSuggestions = document.getElementById("exportPathSuggestions");

let commonPaths = [];
let defaultPath = "";

// 从后端加载默认导出路径
async function loadDefaultExportPath() {
    try {
        const resp = await fetch("/api/default-export-path");
        const data = await resp.json();
        defaultPath = data.default_path || "";
        commonPaths = data.common_paths || [];
        exportPathInput.placeholder = defaultPath;
        exportPathHint.textContent = "Default: " + defaultPath;
        // 构建路径建议列表
        buildExportPathSuggestions(commonPaths, exportPathSuggestions, exportPathInput);
    } catch (err) {
        console.warn("加载默认导出路径失败:", err.message);
    }
}
loadDefaultExportPath();

// 构建路径建议列表
function buildExportPathSuggestions(paths, container, inputEl) {
    if (!container) return;  // 容器不存在则静默跳过
    if (!paths.length) {
        container.style.display = "none";
        return;
    }
    let html = '<div class="path-suggestions-title">📂 Common paths (click to select):</div>';
    paths.forEach(p => {
        const icon = p.exists ? "📁" : "📁";
        html += `<div class="path-suggestion-item" data-path="${escapeHtml(p.path)}" title="${escapeHtml(p.path)}">
            <span>${icon}</span>
            <span>${escapeHtml(p.label)}</span>
            <span class="path-suggestion-detail">${escapeHtml(p.path)}</span>
        </div>`;
    });
    container.innerHTML = html;
    container.style.display = "block";

    // 点击建议路径
    container.querySelectorAll(".path-suggestion-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            const path = item.dataset.path;
            inputEl.value = path;
            if (inputEl === exportPathInput) {
                customExportPath = path;
            } else {
                v3CustomExportPath = path;
            }
        });
    });
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// 文件夹浏览（使用 File System Access API）
async function pickFolder(inputEl, suggestionsEl) {
    // 检查浏览器是否支持
    if (window.showDirectoryPicker) {
        try {
            const dirHandle = await window.showDirectoryPicker({
                mode: "readwrite",
                startIn: "desktop",
            });
            inputEl.value = dirHandle.name;
            // 尝试获取完整路径（部分浏览器支持）
            try {
                const root = await navigator.storage.getDirectory();
                // resolve 可能返回路径信息
                const info = await root.resolve(dirHandle);
            } catch (_) {}
            // 如果浏览器支持 getFileHandle 的路径解析
            if (dirHandle.name) {
                // 更新为系统路径格式
                const resolved = await resolveDirectoryPath(dirHandle);
                if (resolved) {
                    inputEl.value = resolved;
                }
            }
            if (inputEl === exportPathInput) {
                customExportPath = inputEl.value;
            } else {
                v3CustomExportPath = inputEl.value;
            }
            return;
        } catch (err) {
            if (err.name === "AbortError") return; // 用户取消
            console.warn("Folder picker failed:", err.message);
        }
    }
    // 回退：显示路径建议
    if (suggestionsEl.style.display === "none") {
        suggestionsEl.style.display = "block";
    } else {
        suggestionsEl.style.display = "none";
    }
}

// 尝试解析目录完整路径
async function resolveDirectoryPath(dirHandle) {
    try {
        // Chrome/Edge 中，可以通过 requestPermission + 特定方法获取
        // 但 File System Access API 不直接暴露完整路径（出于安全考虑）
        // 返回名称供用户参考
        const name = dirHandle.name;
        // 尝试匹配常见路径模式
        for (const p of commonPaths) {
            if (p.label === name || p.path.endsWith(name)) {
                return p.path;
            }
        }
        // 如果选择了桌面等，尝试匹配
        const homeGuess = defaultPath ? defaultPath.split("\\").slice(0, -2).join("\\") : "";
        if (homeGuess) {
            return homeGuess + "\\" + name;
        }
        return name; // 仅返回文件夹名
    } catch (_) {
        return dirHandle.name;
    }
}

// 文件夹选择按钮
pickExportPathBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    pickFolder(exportPathInput, exportPathSuggestions);
});

// 折叠/展开导出路径设置（默认展开）
let exportPathExpanded = true;
exportPathToggle.addEventListener("click", () => {
    exportPathExpanded = !exportPathExpanded;
    if (exportPathExpanded) {
        exportPathBody.style.display = "block";
        exportPathArrow.textContent = "▼";
    } else {
        exportPathBody.style.display = "none";
        exportPathArrow.textContent = "▶";
    }
});

// 重置为默认路径
resetExportPathBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    exportPathInput.value = "";
    customExportPath = "";
});

// ---- 上传框点击事件 ----
videoUploadBox.addEventListener("click", () => videoInput.click());
audioUploadBox.addEventListener("click", () => audioInput.click());

// ---- 拖拽支持 ----
[videoUploadBox, audioUploadBox].forEach((box) => {
    box.addEventListener("dragover", (e) => {
        e.preventDefault();
        box.style.borderColor = "var(--primary)";
    });
    box.addEventListener("dragleave", () => {
        box.style.borderColor = "var(--border)";
    });
    box.addEventListener("drop", (e) => {
        e.preventDefault();
        box.style.borderColor = "var(--border)";
        const files = e.dataTransfer.files;
        if (box === videoUploadBox && files.length > 0) {
            handleVideoFile(files[0]);
        } else if (box === audioUploadBox) {
            handleAudioFiles(Array.from(files));
        }
    });
});

// ---- 视频文件选择 ----
videoInput.addEventListener("change", () => {
    if (videoInput.files.length > 0) {
        handleVideoFile(videoInput.files[0]);
    }
});

function handleVideoFile(file) {
    videoFile = file;
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    videoFileInfo.textContent = `✅ ${file.name} (${sizeMB} MB)`;
    videoUploadBox.classList.add("has-file");
    checkReady();
}

// ---- 音频文件选择 ----
audioInput.addEventListener("change", () => {
    handleAudioFiles(Array.from(audioInput.files));
});

function handleAudioFiles(files) {
    audioFiles = files;
    if (files.length === 0) return;

    const names = files.map((f) => {
        const sizeMB = (f.size / (1024 * 1024)).toFixed(1);
        return `${f.name} (${sizeMB} MB)`;
    });
    audioFileInfo.innerHTML = "✅ " + names.join("<br>");
    audioUploadBox.classList.add("has-file");
    checkReady();
}

// ---- 检查是否可开始 ----
function checkReady() {
    if (videoFile && audioFiles.length > 0) {
        startBtn.disabled = false;
    }
}

// ============================================
// 🌐 Ctrl+V 粘贴上传 & URL 下载
// ============================================

// ---- 全局粘贴监听 ----
document.addEventListener("paste", (e) => {
    const clipboardItems = e.clipboardData?.items;
    if (!clipboardItems) return;

    const isV3Active = document.getElementById("v3Content")?.style.display !== "none";

    // 优先处理文件粘贴（如从文件管理器复制文件后粘贴）
    for (const item of clipboardItems) {
        if (item.kind === "file") {
            e.preventDefault();
            const file = item.getAsFile();
            if (!file) continue;
            const mime = file.type || "";
            if (mime.startsWith("video/")) {
                showPasteToast(t("toast.pastedVideo") + ": " + file.name);
                if (isV3Active) {
                    v3VideoFile = file;
                    document.getElementById("v3VideoFileInfo").textContent =
                        "✅ " + file.name + " (" + (file.size / 1024 / 1024).toFixed(1) + " MB)";
                    document.getElementById("v3VideoUploadBox").classList.add("has-file");
                    if (typeof checkV3Ready === "function") checkV3Ready();
                } else {
                    handleVideoFile(file);
                }
                return;
            } else if (mime.startsWith("audio/")) {
                showPasteToast(t("toast.pastedAudio") + ": " + file.name);
                if (isV3Active) {
                    v3AudioFiles = [file];
                    document.getElementById("v3AudioFileInfo").innerHTML =
                        "✅ " + file.name + " (" + (file.size / 1024 / 1024).toFixed(1) + " MB)";
                    document.getElementById("v3AudioUploadBox").classList.add("has-file");
                    if (typeof checkV3Ready === "function") checkV3Ready();
                } else {
                    handleAudioFiles([file]);
                }
                return;
            }
        }
    }

    // 如果没有文件，检查是否有 URL 文本
    const text = e.clipboardData.getData("text/plain").trim();
    if (text && (text.startsWith("http://") || text.startsWith("https://"))) {
        e.preventDefault();
        // 判断是视频还是音频链接
        const lower = text.toLowerCase();
        const isVideo = /\.(mp4|mov|avi|mkv|webm)(\?|$)/.test(lower);
        const isAudio = /\.(mp3|wav|flac|aac|m4a|ogg)(\?|$)/.test(lower);

        if (isVideo) {
            showPasteToast(t("toast.detectedVideoLink"));
            if (isV3Active) { v3DownloadFromUrl(text, "video"); }
            else { downloadFromUrl(text, "video"); }
        } else if (isAudio) {
            showPasteToast(t("toast.detectedMusicLink"));
            if (isV3Active) { v3DownloadFromUrl(text, "audio"); }
            else { downloadFromUrl(text, "audio"); }
        } else {
            showPasteToast(t("toast.detectedLink"));
        }
    }
});

// ---- Toast 提示 ----
let pasteToastTimer = null;
function showPasteToast(msg) {
    const toast = document.getElementById("pasteToast");
    const toastMsg = document.getElementById("pasteToastMsg");
    if (!toast || !toastMsg) return;
    toastMsg.textContent = msg;
    toast.style.display = "flex";
    clearTimeout(pasteToastTimer);
    pasteToastTimer = setTimeout(() => {
        toast.style.display = "none";
    }, 3000);
}

// ---- URL 按钮：切换 URL 输入行 ----
function setupUrlToggle(btnId, rowId) {
    const btn = document.getElementById(btnId);
    const row = document.getElementById(rowId);
    if (!btn || !row) return;
    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        row.style.display = row.style.display === "none" ? "flex" : "none";
        const input = row.querySelector(".url-input");
        if (input && row.style.display === "flex") {
            input.focus();
            // 尝试读取剪贴板中的 URL
            navigator.clipboard?.readText?.().then(text => {
                if (text && (text.startsWith("http://") || text.startsWith("https://"))) {
                    input.value = text;
                    showPasteToast(t("toast.clipboardFilled"));
                }
            }).catch(() => {});
        }
    });
}

// ---- URL 下载处理 ----
function setupUrlGo(btnId, inputId, type) {
    const btn = document.getElementById(btnId);
    const input = document.getElementById(inputId);
    if (!btn || !input) return;
    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const url = input.value.trim();
        if (!url) return;
        downloadFromUrl(url, type);
    });
    // Enter 键也可触发
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            const url = input.value.trim();
            if (url) downloadFromUrl(url, type);
        }
    });
}

// ---- 执行 URL 下载 ----
async function downloadFromUrl(url, type) {
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        alert(t("toast.httpOnly"));
        return;
    }

    showPasteToast(t("toast.downloading"));

    try {
        const resp = await fetch("/api/upload/url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, type }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            alert(t("toast.downloadFailed") + ": " + (data.error || t("errors.unknownError")));
            showPasteToast("❌ " + t("toast.downloadFailed") + ": " + (data.error || t("errors.unknownError")));
            return;
        }

        // 创建 File 对象表示已下载的文件
        const platform = data.platform || "URL";
        showPasteToast(t("toast.downloadComplete") + " [" + platform + "]: " + data.filename + " (" + data.size_mb + "MB)");

        // 触发文件处理
        if (type === "video" && typeof handleVideoFile === "function") {
            // 用已保存的路径通知用户
            videoFile = new File([], data.filename, { type: "video/mp4" });
            videoFile._serverPath = data.file_path;
            videoFile._downloaded = true;
            const sizeMB = data.size_mb;
            document.getElementById("videoFileInfo").textContent =
                `✅ ${data.filename} (${sizeMB} MB) [${t("uploadStates.fromPlatform")} ${platform}]`;
            document.getElementById("videoUploadBox").classList.add("has-file");
            checkReady();
        } else if (type === "audio" && typeof handleAudioFiles === "function") {
            const f = new File([], data.filename, { type: "audio/mpeg" });
            f._serverPath = data.file_path;
            f._downloaded = true;
            audioFiles = [f];
            document.getElementById("audioFileInfo").innerHTML =
                `✅ ${data.filename} (${data.size_mb} MB) [${t("uploadStates.fromPlatform")} ${platform}]`;
            document.getElementById("audioUploadBox").classList.add("has-file");
            checkReady();
        }
    } catch (err) {
        alert(t("errors.downloadRequestFailed") + ": " + err.message);
        showPasteToast("❌ " + t("errors.downloadRequestFailed"));
    }
}

// ---- V3 URL 下载 (同上，但使用 V3 的变量) ----
async function v3DownloadFromUrl(url, type) {
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        alert(t("toast.httpOnly"));
        return;
    }

    const toast = document.getElementById("pasteToast");
    const toastMsg = document.getElementById("pasteToastMsg");
    if (toast && toastMsg) {
        toastMsg.textContent = t("toast.downloading");
        toast.style.display = "flex";
        clearTimeout(pasteToastTimer);
        pasteToastTimer = setTimeout(() => { toast.style.display = "none"; }, 3000);
    }

    try {
        const resp = await fetch("/api/upload/url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, type }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            alert("下载失败: " + (data.error || "未知错误"));
            return;
        }

        const platform = data.platform || "URL";
        if (toast && toastMsg) {
            toastMsg.textContent = t("toast.downloadComplete") + " [" + platform + "]: " + data.filename + " (" + data.size_mb + "MB)";
            toast.style.display = "flex";
            clearTimeout(pasteToastTimer);
            pasteToastTimer = setTimeout(() => { toast.style.display = "none"; }, 3000);
        }

        if (type === "video") {
            v3VideoFile = new File([], data.filename, { type: "video/mp4" });
            v3VideoFile._serverPath = data.file_path;
            v3VideoFile._downloaded = true;
            document.getElementById("v3VideoFileInfo").textContent =
                `✅ ${data.filename} (${data.size_mb} MB) [${t("uploadStates.fromPlatform")} ${platform}]`;
            document.getElementById("v3VideoUploadBox").classList.add("has-file");
            checkV3Ready();
        } else if (type === "audio") {
            const f = new File([], data.filename, { type: "audio/mpeg" });
            f._serverPath = data.file_path;
            f._downloaded = true;
            v3AudioFiles = [f];
            document.getElementById("v3AudioFileInfo").innerHTML =
                `✅ ${data.filename} (${data.size_mb} MB) [${t("uploadStates.fromPlatform")} ${platform}]`;
            document.getElementById("v3AudioUploadBox").classList.add("has-file");
            checkV3Ready();
        }
    } catch (err) {
        alert("下载请求失败: " + err.message);
    }
}

// ---- 初始化 URL 上传功能 ----
function initUrlUpload() {
    // V2
    setupUrlToggle("videoPasteBtn", "videoUrlRow");
    setupUrlToggle("videoUrlBtn", "videoUrlRow");
    setupUrlGo("videoUrlGo", "videoUrlInput", "video");
    setupUrlToggle("audioPasteBtn", "audioUrlRow");
    setupUrlToggle("audioUrlBtn", "audioUrlRow");
    setupUrlGo("audioUrlGo", "audioUrlInput", "audio");

    // V3
    setupUrlToggle("v3VideoPasteBtn", "v3VideoUrlRow");
    setupUrlToggle("v3VideoUrlBtn", "v3VideoUrlRow");
    setupUrlGo("v3VideoUrlGo", "v3VideoUrlInput", "video");
    setupUrlToggle("v3AudioPasteBtn", "v3AudioUrlRow");
    setupUrlToggle("v3AudioUrlBtn", "v3AudioUrlRow");
    setupUrlGo("v3AudioUrlGo", "v3AudioUrlInput", "audio");
}

// 页面加载时初始化
document.addEventListener("DOMContentLoaded", async () => {
    // 先初始化 i18n（必须在其他操作之前）
    await I18N.init();
    initUrlUpload();
    // 重新应用 i18n（覆盖 URL 上传中可能动态生成的文本）
    I18N._applyToDOM();
});

// ---- 开始分析 ----
startBtn.addEventListener("click", async () => {
    if (!videoFile || audioFiles.length === 0) return;

    // 隐藏之前的结果
    resultSection.style.display = "none";
    errorBox.style.display = "none";

    // 显示进度
    startBtn.disabled = true;
    progressSection.style.display = "block";
    updateSteps(2);

    // 构建 FormData
    const formData = new FormData();
    if (videoFile._serverPath) {
        // 从 URL 下载的文件，已在服务器上
        formData.append("video_server_path", videoFile._serverPath);
        formData.append("video_filename", videoFile.name);
        // 仍然 append 一个空 Blob 以通过基本验证
        formData.append("video", new Blob([""], { type: "video/mp4" }), videoFile.name);
    } else {
        formData.append("video", videoFile);
    }
    formData.append("mode", "manual");
    formData.append("editing_mode", editingMode);
    // 读取自定义导出路径
    customExportPath = exportPathInput.value.trim();
    if (customExportPath) {
        formData.append("custom_export_path", customExportPath);
    }
    audioFiles.forEach((f) => {
        if (f._serverPath) {
            formData.append("audio_server_paths", f._serverPath);
            formData.append("audio_filenames_list", f.name);
            formData.append("audio", new Blob([""], { type: "audio/mpeg" }), f.name);
        } else {
            formData.append("audio", f);
        }
    });

    try {
        // 上传
        progressText.textContent = t("progress.uploading");
        progressPercent.textContent = "";
        progressBar.style.width = "5%";

        const uploadResp = await fetch("/upload", {
            method: "POST",
            body: formData,
        });

        if (!uploadResp.ok) {
            const err = await uploadResp.json();
            throw new Error(err.error || "上传失败");
        }

        const { task_id } = await uploadResp.json();

        // 轮询任务状态
        await pollTaskStatus(task_id);
    } catch (err) {
        showError(err.message);
        startBtn.disabled = false;
    }
});

// ---- 轮询任务状态 ----
async function pollTaskStatus(taskId) {
    const maxAttempts = 300; // 最多 5 分钟
    let attempts = 0;

    while (attempts < maxAttempts) {
        await sleep(1000); // 每秒查询一次
        attempts++;

        try {
            const resp = await fetch(`/status/${taskId}`);
            const data = await resp.json();

            // 更新进度条和文字
            progressBar.style.width = data.progress + "%";
            progressPercent.textContent = data.progress + "%";
            progressText.textContent = data.message;

            // 更新步骤状态
            if (data.progress >= 25) updateSteps(2);
            if (data.progress >= 50) updateSteps(3);
            if (data.progress >= 85) updateSteps(4);

            if (data.status === "completed") {
                // 显示结果
                updateSteps(4);
                markAllStepsDone();
                showResults(data);
                startBtn.disabled = false;
                return;
            }

            if (data.status === "error") {
                throw new Error(data.message);
            }
        } catch (err) {
            if (err.message.includes("处理出错") || err.message.includes("❌")) {
                throw err;
            }
            // 网络错误，继续重试
            console.warn("查询状态失败，重试中...", err.message);
        }
    }

    throw new Error(t("errors.processingTimeout"));
}

// ---- 显示结果 ----
function showResults(data) {
    resultSection.style.display = "block";
    progressSection.style.display = "none";

    // 电影风格分析
    const style = data.style_analysis;
    const styleContent = document.getElementById("styleContent");

    if (style && !style.parse_error) {
        styleContent.innerHTML = `
            <div class="result-grid">
                <div class="result-item">
                    <span class="result-label">${t("results.genre")}</span>
                    <span class="result-value">${style.genre || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.mood")}</span>
                    <span class="result-value">${style.mood || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.colorPalette")}</span>
                    <span class="result-value">${style.color_palette || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.pacing")}</span>
                    <span class="result-value">${style.pacing || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.visualStyle")}</span>
                    <span class="result-value">${style.visual_style || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.recommendedGenre")}</span>
                    <span class="result-value">${style.recommended_music?.genre || "—"}</span>
                </div>
            </div>
            <div style="margin-top:12px;">
                <span class="result-label">${t("results.coreThemes")}</span>
                <div class="themes-list" style="margin-top:6px;">
                    ${(style.themes || []).map(t => `<span class="theme-tag">${t}</span>`).join("")}
                </div>
            </div>
        `;
    } else {
        styleContent.innerHTML = `<p style="color:var(--text-secondary)">${t("results.styleParsing")}</p>`;
    }

    // 音乐匹配结果
    const matches = data.match_results || [];
    const matchContent = document.getElementById("matchContent");

    if (matches.length > 0) {
        matchContent.innerHTML = matches
            .map((m, i) => {
                const match = m.match || {};
                const score = match.match_score || 0;
                const scoreClass = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
                const name = m.file_path ? m.file_path.split(/[/\\]/).pop() : `Music ${i + 1}`;
                const isBest = i === 0 ? " 🏆" : "";

                return `
                <div class="match-item">
                    <div class="match-item-header">
                        <span class="match-item-name">${name}${isBest}</span>
                        <span class="match-item-score ${scoreClass}">${score} ${t("results.score")}</span>
                    </div>
                    <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:6px;">
                        ${match.analysis || ""}
                    </p>
                    <div style="font-size:0.8rem;color:var(--text-secondary);">
                        BPM: ${m.tempo_bpm || "?"} | Key: ${m.estimated_key || "?"} | Duration: ${m.duration_seconds || "?"}s
                    </div>
                    ${match.editing_suggestion ? `
                    <div style="margin-top:8px;padding:8px;background:rgba(108,99,255,0.08);border-radius:6px;font-size:0.85rem;">
                        💡 ${match.editing_suggestion}
                    </div>` : ""}
                </div>
                `;
            })
            .join("");
    } else {
        matchContent.innerHTML = `<p style="color:var(--text-secondary)">${t("results.noMatch")}</p>`;
    }

    // 智能剪辑信息
    if (data.smart_segments_info) {
        const ssi = data.smart_segments_info;
        const smartCard = document.createElement("div");
        smartCard.className = "result-card";
        const modeLabel = data.editing_mode === "video_first" ? t("results.videoFirstLabel") : t("results.musicFirstLabel");
        smartCard.innerHTML = `
            <h3>✂️ ${t("results.smartEdit")}</h3>
            <div class="result-grid">
                <div class="result-item">
                    <span class="result-label">${t("results.editModeLabel")}</span>
                    <span class="result-value">${modeLabel}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.detectedScenes")}</span>
                    <span class="result-value">${ssi.scene_count || "?"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">${t("results.generatedSegments")}</span>
                    <span class="result-value">${ssi.segment_count || "?"}</span>
                </div>
            </div>
        `;
        document.getElementById("resultSection").appendChild(smartCard);
    }

    // 电影识别信息
    if (data.movie_identity && data.movie_identity.identified) {
        const mi = data.movie_identity;
        const movieCard = document.createElement("div");
        movieCard.className = "result-card";
        const knowledge = mi.ai_knowledge || {};
        movieCard.innerHTML = `
            <h3>🎬 ${t("results.identifiedMovie")}</h3>
            <p><strong>${mi.movie_name}</strong> (${mi.year || ""}) — Confidence: ${mi.confidence || "?"}</p>
            ${knowledge.plot_summary ? `<p style="font-size:0.85rem;color:var(--text-secondary);margin-top:6px;">${knowledge.plot_summary}</p>` : ""}
            ${knowledge.themes && knowledge.themes.length ? `<div class="themes-list" style="margin-top:8px;">${knowledge.themes.map(t => `<span class="theme-tag">${t}</span>`).join("")}</div>` : ""}
        `;
        document.getElementById("resultSection").appendChild(movieCard);
    }

    // 音乐结构信息
    if (data.music_structure && data.music_structure.structure) {
        const ms = data.music_structure;
        const structCard = document.createElement("div");
        structCard.className = "result-card";
        structCard.innerHTML = `
            <h3>🎵 ${t("results.musicStructure")}</h3>
            <div class="music-structure-viz" style="display:flex;height:24px;border-radius:6px;overflow:hidden;margin-bottom:8px;">
                ${ms.structure.map(s => {
                    const colors = {intro:"#4a90d9", verse:"#67c23a", pre_chorus:"#e6a23c", chorus:"#f56c6c", drop:"#ff3b3b", bridge:"#909399", buildup:"#e6a23c", outro:"#4a90d9", breakdown:"#909399", interlude:"#b0c4de", final_chorus:"#ff3b3b", climax:"#ff3b3b"};
                    const color = colors[s.section] || "#909399";
                    const pct = (s.duration / ms.duration * 100).toFixed(1);
                    return `<div title="${s.section}: ${s.start_time.toFixed(0)}s-${s.end_time.toFixed(0)}s" style="width:${pct}%;background:${color};min-width:2px;"></div>`;
                }).join("")}
            </div>
            <p style="font-size:0.8rem;color:var(--text-secondary);">${ms.overall_structure || ""}</p>
        `;
        document.getElementById("resultSection").appendChild(structCard);
    }

    // 草稿信息
    if (data.draft_info) {
        const draft = data.draft_info;
        const exportPath = data.export_path || "";
        const draftCard = document.createElement("div");
        draftCard.className = "result-card";
        draftCard.innerHTML = `
            <h3>✂️ ${t("results.draftGenerated")}</h3>
            <p style="margin-bottom:8px;">${t("results.draftName")}: <strong>${draft.draft_name}</strong></p>
            <p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">📁 ${t("results.exportLocation")}: <code style="font-size:0.78rem;">${exportPath}</code></p>
            ${draft.capcut_draft_path
                ? `<p style="color:var(--success);">✅ ${t("results.draftSynced")}</p>`
                : `<p style="color:var(--text-secondary);">📂 ${t("results.draftManual")}: ${draft.draft_folder}</p>
                   <p style="color:var(--warning);">⚠️ ${t("results.draftManualHint")}</p>`
            }
            ${draft.editing_hint ? `<p style="margin-top:8px;color:var(--text-secondary);">💡 ${draft.editing_hint}</p>` : ""}
        `;
        document.getElementById("resultSection").appendChild(draftCard);
    }
}

// ---- 工具函数 ----
function updateSteps(activeStep) {
    steps.forEach((step) => {
        const stepNum = parseInt(step.dataset.step);
        step.classList.remove("active", "completed");
        if (stepNum < activeStep) step.classList.add("completed");
        if (stepNum === activeStep) step.classList.add("active");
    });
}

function markAllStepsDone() {
    steps.forEach((step) => {
        step.classList.remove("active");
        step.classList.add("completed");
    });
}

function showError(message) {
    errorBox.style.display = "block";
    errorBox.textContent = "❌ " + message;
    progressSection.style.display = "none";
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}


// ============================================
// 检查更新
// ============================================

const updateBtn = document.getElementById("updateBtn");
const updateModal = document.getElementById("updateModal");
const updateClose = document.getElementById("updateClose");
const startUpdateBtn = document.getElementById("startUpdateBtn");

// 打开更新弹窗
updateBtn.addEventListener("click", () => {
    updateModal.style.display = "flex";
    resetUpdateUI();
    checkForUpdate();
});

// 关闭更新弹窗
updateClose.addEventListener("click", () => {
    updateModal.style.display = "none";
});
updateModal.addEventListener("click", (e) => {
    if (e.target === updateModal) {
        updateModal.style.display = "none";
    }
});
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && updateModal.style.display === "flex") {
        updateModal.style.display = "none";
    }
});

function resetUpdateUI() {
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    const setDisplay = (id, val) => { const el = document.getElementById(id); if (el) el.style.display = val; };

    setText("updateAppVersion", t("update.detecting"));
    setText("updateAppDesc", "—");
    setText("updateEditorName", t("update.detecting"));
    setText("updateEditorVersion", "—");
    setText("updateCompatStatus", t("update.detecting"));
    setText("updateJypRange", "—");
    setText("updateCapcutRange", "—");
    setDisplay("updateAvailableSection", "none");
    setDisplay("updateProgressSection", "none");
    setDisplay("updateMessage", "none");
    setDisplay("updateGitInfo", "none");
    setDisplay("updateMethodRow", "none");
}

async function checkForUpdate() {
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    const setHTML = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    const setDisplay = (id, val) => { const el = document.getElementById(id); if (el) el.style.display = val; };
    const setClass = (id, cls) => { const el = document.getElementById(id); if (el) el.className = cls; };
    const getEl = (id) => document.getElementById(id);

    try {
        const resp = await fetch("/api/check-update");
        const data = await resp.json();

        const compat = data.compatibility || {};

        // 填充当前版本信息
        setText("updateAppVersion", `Movie Music Matcher v${compat.app_version || "—"}`);
        setText("updateAppDesc", compat.description || "—");

        // 编辑器信息
        setText("updateEditorName", compat.editor_name || t("update.notDetected"));
        setText("updateEditorVersion", compat.editor_version || t("update.notInstalled"));

        // 兼容状态
        const compatStatus = getEl("updateCompatStatus");
        if (compatStatus) {
            if (compat.is_compatible) {
                compatStatus.innerHTML = '<span class="compat-badge compat-ok">' + t("update.compatible") + '</span>';
            } else {
                compatStatus.innerHTML = '<span class="compat-badge compat-warn">' + t("update.incompatible") + '</span>';
            }
        }

        // 兼容范围
        setText("updateJypRange", compat.compatible_jyp_range || "—");
        setText("updateCapcutRange", compat.compatible_capcut_range || "—");

        // 更新可用
        if (data.has_update && data.update_info) {
            const info = data.update_info;
            setText("updateLatestVersion", `v${info.version}`);
            setText("updateLatestDesc", info.description || "—");
            setText("updateLatestJyp", info.compatible_jyp_range || "—");
            setDisplay("updateAvailableSection", "block");

            // 更新目标说明
            if (info.best_for_editor) {
                setText("updateLatestVersion", `v${info.version}（适配 ${info.best_for_editor}）`);
            }

            // 更新方式
            const methodRow = getEl("updateMethodRow");
            const methodSpan = getEl("updateMethod");
            const gitInfo = getEl("updateGitInfo");
            const gitBadge = getEl("updateGitBadge");
            const gitDetail = getEl("updateGitDetail");
            const startBtn = getEl("startUpdateBtn");

            const updateMethod = data.update_method || "manual";

            if (updateMethod === "git") {
                if (methodRow) methodRow.style.display = "flex";
                if (methodSpan) methodSpan.innerHTML = '<span class="compat-badge compat-ok">' + t("update.gitAutoUpdate") + '</span>';
                if (startBtn) { startBtn.textContent = t("update.oneClickGit"); startBtn.className = "btn-primary btn-git-update"; }

                // Git 详情
                if (data.git_check) {
                    if (gitInfo) gitInfo.style.display = "block";
                    const gc = data.git_check;
                    if (gc.remote_url) {
                        if (gitBadge) gitBadge.innerHTML = '<span class="compat-badge compat-ok">' + t("update.gitConnected") + '</span>';
                        if (gitDetail) gitDetail.innerHTML = `
                            ${t("update.remoteRepo")}: ${gc.remote_url}<br>
                            ${t("update.behindCommits")}: <strong>${gc.behind_count || 0}</strong>
                        `;
                    } else {
                        if (gitBadge) gitBadge.innerHTML = '<span class="compat-badge compat-warn">' + t("update.gitNotConfigured") + '</span>';
                    }
                }
            } else {
                if (methodRow) methodRow.style.display = "flex";
                if (methodSpan) methodSpan.innerHTML = '<span class="compat-badge compat-warn">' + t("update.manualDownload") + '</span>';
                if (startBtn) { startBtn.textContent = t("update.startUpdate"); startBtn.className = "btn-primary"; }

                // 显示 Git 设置指引
                if (data.git_check && data.git_check.error) {
                    if (gitInfo) gitInfo.style.display = "block";
                    if (gitBadge) gitBadge.innerHTML = '<span class="compat-badge compat-warn">' + t("update.suggestGit") + '</span>';
                    if (gitDetail) gitDetail.textContent = data.git_check.error;
                }
            }
        } else {
            // 没有更新，显示提示
            const msg = getEl("updateMessage");
            if (msg) {
                msg.style.display = "block";
                msg.className = "update-message update-message-info";
                msg.textContent = t("update.noUpdate");
            }
        }
    } catch (err) {
        const msg = getEl("updateMessage");
        if (msg) {
            msg.style.display = "block";
            msg.className = "update-message update-message-error";
            msg.textContent = "❌ " + t("update.checkFailed") + ": " + err.message;
        }
    }
}

// 开始更新
startUpdateBtn.addEventListener("click", async () => {
    startUpdateBtn.disabled = true;
    document.getElementById("updateProgressSection").style.display = "block";
    document.getElementById("updateMessage").style.display = "none";

    try {
        // 轮询更新进度（先触发更新）
        const startResp = await fetch("/api/start-update", { method: "POST" });
        const startData = await startResp.json();

        if (startData.is_guidance) {
            // 无远程 URL，显示指引信息
            document.getElementById("updateProgressSection").style.display = "none";
            const msg = document.getElementById("updateMessage");
            msg.style.display = "block";
            msg.className = "update-message update-message-guidance";
            msg.innerHTML = startData.message.replace(/\n/g, "<br>");
            startUpdateBtn.disabled = false;
            return;
        }

        if (!startData.success) {
            throw new Error(startData.message || t("errors.updateStartFailed"));
        }

        // 轮询更新进度
        await pollUpdateProgress();

    } catch (err) {
        document.getElementById("updateProgressSection").style.display = "none";
        const msg = document.getElementById("updateMessage");
        msg.style.display = "block";
        msg.className = "update-message update-message-error";
        msg.textContent = "❌ " + err.message;
        startUpdateBtn.disabled = false;
    }
});

async function pollUpdateProgress() {
    const maxAttempts = 120;
    let attempts = 0;

    while (attempts < maxAttempts) {
        await sleep(1000);
        attempts++;

        try {
            const resp = await fetch("/api/update-status");
            const data = await resp.json();

            document.getElementById("updateProgressBar").style.width = data.progress + "%";
            document.getElementById("updateProgressPercent").textContent = data.progress + "%";
            document.getElementById("updateProgressText").textContent = data.message;

            if (!data.in_progress) {
                // 更新完成或失败
                document.getElementById("updateProgressSection").style.display = "none";
                const msg = document.getElementById("updateMessage");
                msg.style.display = "block";
                if (data.error) {
                    msg.className = "update-message update-message-error";
                    msg.textContent = "❌ " + data.error;
                } else {
                    msg.className = "update-message update-message-success";
                    msg.textContent = data.message;
                }
                startUpdateBtn.disabled = false;
                return;
            }
        } catch (err) {
            console.warn("查询更新进度失败，重试中...", err.message);
        }
    }

    throw new Error(t("errors.updateTimeout"));
}

// ============================================
// v3.0 管道模式
// ============================================

let isV3Mode = false;
let v3TaskId = null;
let v3CurrentPhase = "";
let v3ProjectSlug = "";
let v3EditingMode = "video_first";
let v3CustomExportPath = "";
let v3VideoFile = null;
let v3AudioFiles = [];

// ---- v3/v2 模式切换 ----
let v3Initialized = false;  // 必须在 URL 检测之前声明，避免 TDZ 错误

const v3Switch = document.getElementById("v3Switch");
const v2Content = document.getElementById("v2Content");
const v3Content = document.getElementById("v3Content");
const v2Subtitle = document.getElementById("v2Subtitle");
const v3Subtitle = document.getElementById("v3Subtitle");

// 检测 URL 参数 ?v=3
if (window.location.search.includes("v=3")) {
    v3Switch.checked = true;
    switchToV3();
}

v3Switch.addEventListener("change", () => {
    if (v3Switch.checked) {
        switchToV3();
        // 更新 URL
        if (!window.location.search.includes("v=3")) {
            window.history.replaceState({}, "", "?v=3");
        }
    } else {
        switchToV2();
        window.history.replaceState({}, "", window.location.pathname);
    }
});

function switchToV3() {
    isV3Mode = true;
    v2Content.style.display = "none";
    v3Content.style.display = "block";
    if (v2Subtitle) v2Subtitle.style.display = "none";
    if (v3Subtitle) v3Subtitle.style.display = "";
    document.getElementById("v2Badge").style.opacity = "0.5";
    document.getElementById("v3Badge").style.opacity = "1";
    initV3Mode();
}

function switchToV2() {
    isV3Mode = false;
    v2Content.style.display = "";
    v3Content.style.display = "none";
    if (v2Subtitle) v2Subtitle.style.display = "";
    if (v3Subtitle) v3Subtitle.style.display = "none";
    document.getElementById("v2Badge").style.opacity = "1";
    document.getElementById("v3Badge").style.opacity = "0.5";
}

// ---- v3 初始化 ----
function initV3Mode() {
    if (v3Initialized) return;  // 防止重复绑定事件
    v3Initialized = true;

    // 偏好芯片选择器
    initPrefChips();

    // 简报创建
    document.getElementById("createBriefBtn").addEventListener("click", createBrief);

    // v3 上传
    setupV3Upload();

    // v3 剪辑模式
    document.querySelectorAll("[data-v3-mode]").forEach(card => {
        card.addEventListener("click", () => {
            document.querySelectorAll("[data-v3-mode]")
                .forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            v3EditingMode = card.dataset.v3Mode;
        });
    });

    // v3 导出路径
    loadV3ExportPath();
    document.getElementById("v3ExportPathToggle").addEventListener("click", () => {
        const body = document.getElementById("v3ExportPathBody");
        const arrow = document.getElementById("v3ExportPathArrow");
        if (body.style.display !== "none") {
            body.style.display = "none";
            arrow.textContent = "▶";
        } else {
            body.style.display = "block";
            arrow.textContent = "▼";
        }
    });
    document.getElementById("v3PickExportPathBtn").addEventListener("click", (e) => {
        e.stopPropagation();
        pickFolder(
            document.getElementById("v3ExportPathInput"),
            document.getElementById("v3ExportPathSuggestions")
        );
    });
    document.getElementById("v3ResetExportPathBtn").addEventListener("click", (e) => {
        e.stopPropagation();
        document.getElementById("v3ExportPathInput").value = "";
        v3CustomExportPath = "";
    });

    // v3 开始按钮
    document.getElementById("v3StartBtn").addEventListener("click", startV3Pipeline);

    // 确认面板按钮
    document.getElementById("approveBtn").addEventListener("click", approvePhase);
    document.getElementById("retryBtn").addEventListener("click", retryPhase);
    document.getElementById("v3SkipBtn").addEventListener("click", skipPhase);
}

async function loadV3ExportPath() {
    try {
        const resp = await fetch("/api/default-export-path");
        const data = await resp.json();
        document.getElementById("v3ExportPathInput").placeholder = data.default_path || "";
        document.getElementById("v3ExportPathHint").textContent = "Default: " + (data.default_path || "");
        // 构建 v3 路径建议
        const v3Paths = data.common_paths || [];
        buildExportPathSuggestions(
            v3Paths,
            document.getElementById("v3ExportPathSuggestions"),
            document.getElementById("v3ExportPathInput")
        );
    } catch (err) {
        console.warn("加载默认导出路径失败:", err.message);
    }
}

// ============================================
// 🎨 偏好设置 Chip 选择器
// ============================================

let selectedPrefs = {};  // { group: [values] }

function initPrefChips() {
    let needsI18nReapply = false;

    document.querySelectorAll(".prefs-chips").forEach(chipGroup => {
        const groupName = chipGroup.dataset.prefsGroup;
        if (!groupName) return;
        selectedPrefs[groupName] = [];

        // 为每个分类添加计数徽章（放在 label 后面作为兄弟节点，避免被 i18n textContent 清除）
        const catLabel = chipGroup.closest(".prefs-category")?.querySelector(".prefs-cat-label");
        if (catLabel) {
            // 将 label 的文本包裹在 span 中，方便 i18n 单独更新
            if (!catLabel.querySelector(".prefs-cat-text")) {
                const textSpan = document.createElement("span");
                textSpan.className = "prefs-cat-text";
                textSpan.textContent = catLabel.textContent || "";
                catLabel.textContent = "";
                catLabel.appendChild(textSpan);
                // 移除 data-i18n 避免 i18n 覆盖整个 label
                const i18nKey = catLabel.getAttribute("data-i18n");
                catLabel.removeAttribute("data-i18n");
                if (i18nKey) {
                    textSpan.setAttribute("data-i18n", i18nKey);
                    needsI18nReapply = true;  // 新元素需要翻译
                }
            }
            // 添加计数徽章
            if (!catLabel.parentElement.querySelector(".pref-count-badge")) {
                const badge = document.createElement("span");
                badge.className = "pref-count-badge";
                badge.style.display = "none";
                catLabel.insertAdjacentElement("afterend", badge);
            }
        }

        chipGroup.querySelectorAll(".pref-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                const value = chip.dataset.prefsValue;
                if (!value) return;

                // 切换选中状态
                chip.classList.toggle("active");

                if (chip.classList.contains("active")) {
                    if (!selectedPrefs[groupName].includes(value)) {
                        selectedPrefs[groupName].push(value);
                    }
                } else {
                    selectedPrefs[groupName] = selectedPrefs[groupName].filter(v => v !== value);
                }

                updatePrefsSummary();
                updateCatBadge(chipGroup, groupName);
            });
        });
    });

    // 如果 i18n 已初始化且我们创建了新的 data-i18n 元素，重新应用翻译
    if (needsI18nReapply && I18N._locale) {
        I18N._applyToDOM();
    }
}

function updateCatBadge(chipGroup, groupName) {
    const catLabel = chipGroup.closest(".prefs-category")?.querySelector(".prefs-cat-label");
    if (!catLabel) return;
    // 徽章是 label 的下一个兄弟元素
    const badge = catLabel.nextElementSibling;
    if (!badge || !badge.classList.contains("pref-count-badge")) return;

    const count = (selectedPrefs[groupName] || []).length;
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = "inline-flex";
    } else {
        badge.style.display = "none";
    }
}

function updatePrefsSummary() {
    const summary = document.getElementById("prefsSelectedSummary");
    const tags = document.getElementById("prefsSelectedTags");
    if (!summary || !tags) return;

    const allSelected = Object.values(selectedPrefs).flat();
    if (allSelected.length === 0) {
        summary.style.display = "none";
        return;
    }

    summary.style.display = "flex";
    tags.innerHTML = allSelected
        .map(v => `<span class="pref-summary-tag">${v.replace(/_/g, " ")}</span>`)
        .join("");
}

function collectPrefsData() {
    // 返回结构化偏好对象，只包含有选择的组
    const result = {};
    for (const [group, values] of Object.entries(selectedPrefs)) {
        if (values.length > 0) {
            result[group] = values;
        }
    }
    return result;
}

// ---- v3 简报创建 ----
async function createBrief() {
    const topic = document.getElementById("briefTopic").value.trim();
    if (!topic) {
        alert(t("errors.briefTopicRequired"));
        return;
    }

    // 收集结构化偏好
    const prefsData = collectPrefsData();

    const editingMode = document.getElementById("briefEditingMode").value;

    const briefData = {
        topic: topic,
        target_duration: parseInt(document.getElementById("briefDuration").value) || 120,
        platform: document.getElementById("briefPlatform").value,
        aspect_ratio: document.getElementById("briefAspectRatio").value,
        editing_mode: editingMode,
        editing_preferences: JSON.stringify(prefsData),
    };

    try {
        const resp = await fetch("/api/brief/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(briefData),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || t("errors.briefCreateFailed"));

        v3TaskId = data.task_id;
        v3ProjectSlug = data.project_slug;
        // 同步剪辑模式到 V3 后续步骤
        v3EditingMode = editingMode;

        // 显示上传区域（先更新 DOM）
        document.getElementById("briefSection").style.display = "none";
        document.getElementById("v3UploadSection").style.display = "grid";
        document.getElementById("v3EditingSection").style.display = "block";
        document.getElementById("v3UploadBtnBar").style.display = "block";

        // 同步剪辑模式卡片的高亮
        document.querySelectorAll("[data-v3-mode]").forEach(c => {
            c.classList.toggle("active", c.dataset.v3Mode === editingMode);
        });

        // 强制触发 IntersectionObserver 重新检测（.reveal 元素从 display:none 变为可见）
        document.querySelectorAll("#v3UploadSection.reveal, #v3EditingSection.reveal, #v3UploadBtnBar.reveal").forEach(el => {
            el.classList.add("visible");
        });

        // 滚动到上传区域
        document.getElementById("v3UploadSection").scrollIntoView({ behavior: "smooth", block: "start" });

        // 使用 setTimeout 延迟 alert，让浏览器先完成渲染
        const prefsInfo = data.ai_interpretation || data.preferences_summary || "";
        setTimeout(() => {
            let alertMsg = t("errors.promptBriefCreated") + ": " + data.project_slug;
            if (prefsInfo) {
                alertMsg += "\n\n" + (data.ai_interpretation ? "[AI Style Guide]\n" : "[Preferences]\n") + prefsInfo;
            }
            alertMsg += "\n\n" + t("errors.briefCreated");
            alert(alertMsg);
        }, 300);
    } catch (err) {
        alert(t("errors.briefCreateFailed") + ": " + err.message);
    }
}

// ---- v3 上传设置 ----
function setupV3Upload() {
    const v3VideoBox = document.getElementById("v3VideoUploadBox");
    const v3AudioBox = document.getElementById("v3AudioUploadBox");
    const v3VideoInput = document.getElementById("v3VideoInput");
    const v3AudioInput = document.getElementById("v3AudioInput");

    if (!v3VideoBox || !v3AudioBox || !v3VideoInput || !v3AudioInput) {
        console.error("[V3 Upload] Cannot setup - elements not found:", {
            videoBox: !!v3VideoBox, audioBox: !!v3AudioBox,
            videoInput: !!v3VideoInput, audioInput: !!v3AudioInput
        });
        return;
    }

    console.log("[V3 Upload] Setup complete - boxes ready for click/drag");
    v3VideoBox.addEventListener("click", () => v3VideoInput.click());
    v3AudioBox.addEventListener("click", () => v3AudioInput.click());

    v3VideoInput.addEventListener("change", () => {
        if (v3VideoInput.files.length > 0) {
            v3VideoFile = v3VideoInput.files[0];
            document.getElementById("v3VideoFileInfo").textContent =
                "✅ " + v3VideoFile.name + " (" + (v3VideoFile.size / 1024 / 1024).toFixed(1) + " MB)";
            v3VideoBox.classList.add("has-file");
            checkV3Ready();
        }
    });

    v3AudioInput.addEventListener("change", () => {
        v3AudioFiles = Array.from(v3AudioInput.files);
        if (v3AudioFiles.length > 0) {
            document.getElementById("v3AudioFileInfo").innerHTML = "✅ " +
                v3AudioFiles.map(f => f.name + " (" + (f.size / 1024 / 1024).toFixed(1) + " MB)").join("<br>");
            v3AudioBox.classList.add("has-file");
            checkV3Ready();
        }
    });

    // 拖拽支持
    [v3VideoBox, v3AudioBox].forEach(box => {
        box.addEventListener("dragover", e => { e.preventDefault(); box.style.borderColor = "var(--primary)"; });
        box.addEventListener("dragleave", () => { box.style.borderColor = "var(--border)"; });
        box.addEventListener("drop", e => {
            e.preventDefault();
            box.style.borderColor = "var(--border)";
            const files = e.dataTransfer.files;
            if (box === v3VideoBox && files.length > 0) {
                v3VideoFile = files[0];
                document.getElementById("v3VideoFileInfo").textContent =
                    "✅ " + v3VideoFile.name;
                box.classList.add("has-file");
                checkV3Ready();
            } else if (box === v3AudioBox) {
                v3AudioFiles = Array.from(files);
                document.getElementById("v3AudioFileInfo").innerHTML = "✅ " +
                    v3AudioFiles.map(f => f.name).join("<br>");
                box.classList.add("has-file");
                checkV3Ready();
            }
        });
    });
}

function checkV3Ready() {
    document.getElementById("v3StartBtn").disabled = !(v3VideoFile && v3AudioFiles.length > 0);
}

// ---- v3 管道启动 ----
async function startV3Pipeline() {
    if (!v3VideoFile) {
        alert(t("errors.noVideoFile") || "Please select a video file first");
        return;
    }
    if (!v3AudioFiles || v3AudioFiles.length === 0) {
        alert(t("errors.noAudioFile") || "Please select at least one music file");
        return;
    }

    v3CustomExportPath = document.getElementById("v3ExportPathInput").value.trim();

    const formData = new FormData();
    if (v3VideoFile._serverPath) {
        formData.append("video_server_path", v3VideoFile._serverPath);
        formData.append("video_filename", v3VideoFile.name);
        formData.append("video", new Blob([""], { type: "video/mp4" }), v3VideoFile.name);
    } else {
        formData.append("video", v3VideoFile);
    }
    formData.append("project_slug", v3ProjectSlug);
    formData.append("editing_mode", v3EditingMode);
    if (v3CustomExportPath) {
        formData.append("custom_export_path", v3CustomExportPath);
    }
    v3AudioFiles.forEach(f => {
        if (f._serverPath) {
            formData.append("audio_server_paths", f._serverPath);
            formData.append("audio_filenames_list", f.name);
            formData.append("audio", new Blob([""], { type: "audio/mpeg" }), f.name);
        } else {
            formData.append("audio", f);
        }
    });

    // 隐藏上传区，显示管道步骤+进度条
    document.getElementById("v3UploadBtnBar").style.display = "none";
    document.getElementById("pipelineSteps").style.display = "flex";
    document.getElementById("pipelineProgressSection").style.display = "block";
    document.getElementById("v3UploadSection").style.display = "none";
    document.getElementById("v3EditingSection").style.display = "none";

    try {
        const resp = await fetch("/api/upload/v3", {
            method: "POST",
            body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error);

        v3TaskId = data.task_id;
        v3CurrentPhase = data.phase || "media_scan";
        updatePipelineStep(v3CurrentPhase, "active");
        updatePipelineProgress(v3CurrentPhase, 0, t("pipeline.statusInit"));
        await pollV3Pipeline();
    } catch (err) {
        alert(t("errors.pipelineStartFailed") + ": " + err.message);
        // 恢复UI
        document.getElementById("pipelineProgressSection").style.display = "none";
        document.getElementById("pipelineSteps").style.display = "none";
    }
}

// ---- v3 管道轮询（带进度条） ----
let pollingForPhase = null;

async function pollV3Pipeline() {
    const maxAttempts = 600;
    let attempts = 0;
    let lastStatus = "";

    while (attempts < maxAttempts) {
        await sleep(1000);
        attempts++;

        try {
            const resp = await fetch("/api/pipeline/status/" + v3TaskId);
            const data = await resp.json();

            const status = data.status || "";
            const phase = data.phase || v3CurrentPhase;
            const progress = data.progress || 0;
            const message = data.message || "";

            // 更新阶段显示和进度条
            v3CurrentPhase = phase;
            updatePipelineStep(phase, "active");
            updatePipelineProgress(phase, progress, message);

            // 检查最终完成
            if (status === "completed") {
                updatePipelineProgress("build", 100, t("pipeline.phaseNames.build") + " ✅");
                markAllPipelineStepsDone();
                document.getElementById("pipelineProgressSection").style.display = "none";
                showV3Results(data);
                return;
            }

            // 检查是否到达阶段完成状态（等待确认）
            if (status.endsWith("_complete") && status !== lastStatus) {
                updatePipelineStep(phase, "completed");
                updatePipelineProgress(phase, 100, message || (getPhaseDisplayName(phase) + " complete"));
                showApprovalPanel(phase, data);
                return;
            }

            if (status === "error") {
                updatePipelineProgress(phase, 0, "Error: " + message.substring(0, 60));
                throw new Error(message || t("errors.pipelineError"));
            }

            lastStatus = status;
        } catch (err) {
            if (err.message && (err.message.includes("❌") || err.message.includes("fail") || err.message.includes("error"))) {
                alert(t("errors.pipelineError") + ": " + err.message);
                return;
            }
            console.warn("v3 管道轮询失败，重试中...", err.message);
        }
    }

    alert(t("errors.pipelineTimeout"));
}

// ---- v3 确认面板 ----
function showApprovalPanel(phase, data) {
    const panel = document.getElementById("approvalPanel");
    panel.style.display = "block";

    const phaseNames = {
        "media_scan": t("pipeline.phaseNames.media_scan"),
        "material_review": t("pipeline.phaseNames.material_review"),
        "story": t("pipeline.phaseNames.story"),
        "blueprint": t("pipeline.phaseNames.blueprint"),
        "validate": t("pipeline.phaseNames.validate"),
    };

    document.getElementById("approvalTitle").textContent =
        (phaseNames[phase] || phase) + " ✓";

    let summary = "";
    const review = document.getElementById("approvalReview");

    // 默认隐藏跳过按钮，各阶段按需显示
    document.getElementById("v3SkipBtn").style.display = "none";

    switch (phase) {
        case "media_scan":
            const scan = data.scan_preview || {};
            summary = `Scanned ${scan.total_files || "?"} files (${scan.duration_display || ""})`;
            review.innerHTML = scan.files ? scan.files.map(f =>
                `<div style="padding:4px 0;">${f.filename} (${f.size_mb}MB, ${f.duration}s)</div>`
            ).join("") : "<p>已生成 media-manifest.json</p>";
            break;
        case "material_review":
            const rv = data.review || {};
            summary = `ID: ${rv.movie_name || "?"} | Genre: ${rv.genre || ""} | Mood: ${rv.mood || ""}`;
            review.innerHTML = `
                <p><strong>Class:</strong> Action=${rv.action_intensity || ""}, Emotion=${(rv.emotional_range || []).join(", ")}</p>
                <p><strong>Narrative:</strong> ${(rv.narrative_uses || []).join(", ")}</p>
            `;
            break;
        case "story":
            const st = data.story || {};
            summary = st.core_idea || t("pipeline.phaseNames.story") + " complete";
            review.innerHTML = `
                <p><strong>Core Idea:</strong> ${st.core_idea || ""}</p>
                <p><strong>Structure:</strong> ${st.selected_structure || ""}</p>
                <p><strong>Emotional Curve:</strong> ${st.emotional_curve || ""}</p>
                <p><strong>Scene Beats:</strong> ${(st.scene_beats || []).length}</p>
            `;
            document.getElementById("v3SkipBtn").style.display = "";  // 故事可跳过
            break;
        case "blueprint":
            const bp = data.blueprint || {};
            summary = `${bp.total_clips || "?"} clips, ${bp.total_duration || "?"}s, avg score ${bp.avg_highlight_score || "?"}`;
            let viz = '<div class="mini-timeline">';
            (bp.clips || []).forEach(c => {
                const toneColors = {
                    action: "#ff3b3b", emotional: "#ff9800", tension: "#e91e63",
                    calm: "#4caf50", triumph: "#ff9800", climax: "#ff3b3b",
                    mystery: "#9c27b0", melancholy: "#607d8b"
                };
                const color = toneColors[c.emotional_tone] || "#6c63ff";
                viz += `<div class="mini-clip" style="background:${color};flex:${c.duration || 1};" title="${c.emotional_tone}: ${c.purpose}"></div>`;
            });
            viz += '</div>';
            review.innerHTML = viz +
                '<p style="margin-top:8px;">Tone distribution: ' + JSON.stringify(bp.emotional_tones || {}) + '</p>';
            break;
        case "validate":
            const val = data.validation || {};
            summary = val.summary || "";
            review.innerHTML = (val.issues || []).map(i =>
                `<div style="padding:2px 0;color:${i.level === 'error' ? 'var(--error)' : 'var(--warning)'};">${i.level}: ${i.message}</div>`
            ).join("") || "<p>Validation passed</p>";
            break;
        default:
            summary = "Phase complete";
            review.innerHTML = "<p>Ready for next phase</p>";
    }

    document.getElementById("approvalSummary").textContent = summary;
    panel.scrollIntoView({ behavior: "smooth" });
}

// ---- v3 确认/重试/跳过 ----
async function approvePhase() {
    document.getElementById("approvalPanel").style.display = "none";
    try {
        const resp = await fetch("/api/pipeline/confirm/" + v3TaskId, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phase: v3CurrentPhase }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error);

        // 更新到下一阶段并等待完成
        v3CurrentPhase = data.next_phase;
        updatePipelineStep(v3CurrentPhase, "active");
        // 短暂延迟，确保后端线程已启动
        await sleep(500);
        await pollV3Pipeline();
    } catch (err) {
        alert(t("errors.confirmFailed") + ": " + err.message);
        // 恢复面板以便重试
        document.getElementById("approvalPanel").style.display = "block";
    }
}

async function retryPhase() {
    document.getElementById("approvalPanel").style.display = "none";
    try {
        const resp = await fetch("/api/pipeline/retry/" + v3TaskId, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phase: v3CurrentPhase }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error);
        await sleep(500);
        await pollV3Pipeline();
    } catch (err) {
        alert(t("errors.retryFailed") + ": " + err.message);
        document.getElementById("approvalPanel").style.display = "block";
    }
}

async function skipPhase() {
    document.getElementById("approvalPanel").style.display = "none";
    try {
        const resp = await fetch("/api/pipeline/skip/" + v3TaskId, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phase: v3CurrentPhase }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error);

        v3CurrentPhase = data.next_phase;
        updatePipelineStep(v3CurrentPhase, "active");
        await sleep(500);
        await pollV3Pipeline();
    } catch (err) {
        alert(t("errors.skipFailed") + ": " + err.message);
        document.getElementById("approvalPanel").style.display = "block";
    }
}

// ---- v3 管道步骤可视化 + 进度条 ----
function getPhaseDisplayName(phase) {
    return t("pipeline.phaseNames." + phase) || phase;
}

function updatePipelineStep(phase, status) {
    const phaseMap = {
        "media_scan": 0, "material_review": 1, "story": 2,
        "blueprint": 3, "validate": 4, "build": 5
    };
    const activeIdx = phaseMap[phase] || 0;

    document.querySelectorAll(".pstep").forEach((step, idx) => {
        step.classList.remove("active", "completed");
        if (idx < activeIdx) step.classList.add("completed");
        if (idx === activeIdx && status === "active") step.classList.add("active");
        if (idx === activeIdx && status === "completed") step.classList.add("completed");
    });

    // 更新进度条上的阶段名称
    document.getElementById("pipelinePhaseName").textContent =
        getPhaseDisplayName(phase);
}

function updatePipelineProgress(phase, progress, message) {
    // 更新进度百分比
    const bar = document.getElementById("pipelineProgressBar");
    const pct = document.getElementById("pipelinePhasePercent");
    const statusText = document.getElementById("pipelineStatusText");

    bar.style.width = Math.min(100, Math.max(0, progress)) + "%";
    pct.textContent = Math.round(progress) + "%";
    if (message) {
        statusText.textContent = message;
    }
    // 更新阶段名
    document.getElementById("pipelinePhaseName").textContent =
        getPhaseDisplayName(phase);

    // 运行时脉冲动画
    if (progress > 0 && progress < 100) {
        bar.classList.add("pipeline-running");
    } else {
        bar.classList.remove("pipeline-running");
    }
}

function markAllPipelineStepsDone() {
    document.querySelectorAll(".pstep").forEach(step => {
        step.classList.remove("active");
        step.classList.add("completed");
    });
}

// ---- v3 结果显示 ----
function showV3Results(data) {
    document.getElementById("pipelineSteps").style.display = "none";
    const resultSection = document.getElementById("v3ResultSection");
    resultSection.style.display = "block";

    let html = "";

    // 草稿信息
    if (data.draft_info) {
        const draft = data.draft_info;
        html += `<div class="result-card">
            <h3>✂️ ${t("results.draftGenerated")}</h3>
            <p>${t("results.draftName")}: <strong>${draft.draft_name}</strong></p>
            <p class="export-path-display">📁 ${data.export_path || ""}</p>
            ${draft.capcut_draft_path ? '<p style="color:var(--success);">✅ ' + t("results.draftSynced") + '</p>' : ''}
        </div>`;
    }

    // 审计报告
    if (data.audit) {
        const audit = data.audit;
        html += `<div class="result-card">
            <h3>📊 ${t("results.auditReport")}</h3>
            <p>${audit.summary || ""}</p>
            ${(audit.issues || []).slice(0, 5).map(i =>
                `<div style="color:${i.level === 'error' ? 'var(--error)' : 'var(--warning)'};font-size:0.85rem;">• ${i.message}</div>`
            ).join("")}
        </div>`;
    }

    // 补拍建议
    if (data.pickup) {
        const pu = data.pickup;
        html += `<div class="result-card">
            <h3>📋 ${t("results.pickupReport")}</h3>
            <p>${t("results.pickupP0")}: ${pu.p0_count || 0} | ${t("results.pickupP1")}: ${pu.p1_count || 0} | ${t("results.pickupP2")}: ${pu.p2_count || 0}</p>
            ${(pu.p0_items || []).slice(0, 3).map(i =>
                `<div style="font-size:0.85rem;margin-top:4px;">• <strong>${i.missing_info || ""}</strong>: ${i.shot_spec?.subject || ""}</div>`
            ).join("")}
        </div>`;
    }

    document.getElementById("v3ResultContent").innerHTML = html || ("<p>" + t("results.analysisComplete") + "</p>");
    resultSection.scrollIntoView({ behavior: "smooth" });
}

// ============================================
// 🎬 滚动揭示动画 (IntersectionObserver)
// ============================================
(function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("visible");
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: "0px 0px -40px 0px",
    });

    document.querySelectorAll(".reveal").forEach(el => observer.observe(el));

    // 动态元素：MutationObserver 监听新增的 .reveal 元素
    const dynObserver = new MutationObserver((mutations) => {
        mutations.forEach(m => {
            m.addedNodes.forEach(node => {
                if (node.nodeType === 1) {
                    if (node.classList?.contains("reveal")) observer.observe(node);
                    node.querySelectorAll?.(".reveal").forEach(el => observer.observe(el));
                }
            });
        });
    });
    dynObserver.observe(document.body, { childList: true, subtree: true });
})();

// ============================================
// 导航栏按钮（新版）+ v3 切换活跃状态
// ============================================
(function initNavButtons() {
    const tutorialNavBtn = document.getElementById("tutorialNavBtn");
    const updateNavBtn = document.getElementById("updateNavBtn");
    const oldTutorialBtn = document.getElementById("tutorialBtn");
    const oldUpdateBtn = document.getElementById("updateBtn");

    if (tutorialNavBtn && oldTutorialBtn) {
        tutorialNavBtn.addEventListener("click", () => oldTutorialBtn.click());
    }
    if (updateNavBtn && oldUpdateBtn) {
        updateNavBtn.addEventListener("click", () => oldUpdateBtn.click());
    }

    // Language toggle
    const langToggleBtn = document.getElementById("langToggleBtn");
    if (langToggleBtn) {
        langToggleBtn.addEventListener("click", () => {
            I18N.switchLanguage();
        });
    }

    // ---- 🎯 开始旅程：从 Hero 跳转到功能区域 ----
    // 根据当前 V2/V3 模式滚动到正确的功能区
    function scrollToFunctionalSection() {
        const isV3 = document.getElementById("v3Content")?.style.display !== "none";
        const target = isV3
            ? document.getElementById("briefSection")
            : document.getElementById("uploadSection");
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        // 更新导航栏活跃状态：取消所有 link，高亮对应功能
        document.querySelectorAll(".nav-links a").forEach(l => l.classList.remove("active"));
        const navTarget = isV3
            ? document.querySelector('.nav-links a[href="#briefSection"]')
            : document.querySelector('.nav-links a[href="#uploadSection"]');
        if (navTarget) navTarget.classList.add("active");
    }

    // 暴露到全局，供 HTML inline onclick 调用
    window.scrollToFunctionalSection = scrollToFunctionalSection;

    // Nav CTA: scroll to functional section
    const navCTA = document.getElementById("navCTA");
    if (navCTA) {
        navCTA.addEventListener("click", () => scrollToFunctionalSection());
    }

    // Nav links: highlight active on click
    document.querySelectorAll(".nav-links a").forEach(link => {
        link.addEventListener("click", function() {
            document.querySelectorAll(".nav-links a").forEach(l => l.classList.remove("active"));
            this.classList.add("active");
        });
    });

    // Suggestions nav button
    const suggestionsNavBtn = document.getElementById("suggestionsNavBtn");
    if (suggestionsNavBtn) {
        suggestionsNavBtn.addEventListener("click", () => openSuggestions());
    }
})();

// ============================================
// 📬 意见箱
// ============================================

let adminKey = "";  // 管理员密钥（登录后设置）

function isAdmin() { return !!adminKey; }

function adminHeaders() {
    return adminKey ? { "X-Admin-Key": adminKey } : {};
}

function openSuggestions() {
    const modal = document.getElementById("suggestionsModal");
    if (!modal) return;
    modal.style.display = "flex";
    updateAdminUI();
    loadSuggestions();
}

function closeSuggestions() {
    const modal = document.getElementById("suggestionsModal");
    if (modal) modal.style.display = "none";
}

async function loadSuggestions() {
    const list = document.getElementById("suggestionsList");
    const total = document.getElementById("suggestionsTotal");
    if (!list) return;

    list.innerHTML = `<p class="suggestions-loading">${t("suggestions.loading")}</p>`;

    try {
        const url = isAdmin() ? "/api/suggestions?all=1" : "/api/suggestions";
        const resp = await fetch(url, { headers: adminHeaders() });
        const data = await resp.json();
        const suggestions = data.suggestions || [];

        if (total) total.textContent = `${data.total || 0} ${t("suggestions.total")}`;

        if (suggestions.length === 0) {
            list.innerHTML = `<p class="suggestions-empty">${t("suggestions.empty")}</p>`;
            return;
        }

        list.innerHTML = suggestions.map(s => renderSuggestionItem(s)).join("");
    } catch (err) {
        list.innerHTML = `<p class="suggestions-error-msg">${t("suggestions.loadFailed")}: ${err.message}</p>`;
    }
}

function renderSuggestionItem(s) {
    const statusLabels = {
        "pending": t("suggestions.statusPending"),
        "in_progress": t("suggestions.statusInProgress"),
        "completed": t("suggestions.statusCompleted"),
    };
    const status = s.status || "pending";
    const statusLabel = statusLabels[status] || status;
    const hidden = s.hidden || false;

    let adminControls = "";
    if (isAdmin()) {
        const statusOptions = ["pending", "in_progress", "completed"].map(st => {
            const sel = st === status ? " selected" : "";
            return `<option value="${st}"${sel}>${statusLabels[st]}</option>`;
        }).join("");

        adminControls = `
        <div class="suggestion-admin-controls">
            <select class="suggestion-status-select" data-sid="${s.id}" onchange="updateSuggestionStatus('${s.id}', this.value)">
                ${statusOptions}
            </select>
            ${hidden ? `
                <button class="btn-xs btn-restore" onclick="restoreSuggestion('${s.id}')" title="${t("suggestions.restore")}">↩ ${t("suggestions.restore")}</button>
            ` : `
                <button class="btn-xs btn-delete" onclick="deleteSuggestion('${s.id}')" title="${t("suggestions.delete")}">✕ ${t("suggestions.delete")}</button>
            `}
        </div>`;
    }

    const visibility = s.visibility || "public";
    const hiddenBadge = hidden ? `<span class="suggestion-badge-hidden">${t("suggestions.hidden")}</span>` : "";
    const privBadge = visibility === "private"
        ? `<span class="suggestion-badge-private">${t("suggestions.visibilityPrivateBadge")}</span>`
        : "";

    return `
        <div class="suggestion-item${hidden ? " suggestion-hidden" : ""}${visibility === "private" ? " suggestion-private" : ""}">
            <div class="suggestion-item-header">
                <div class="suggestion-item-left">
                    <span class="suggestion-nickname">${escapeHTML(s.nickname)}</span>
                    <span class="suggestion-status-badge status-${status}">${statusLabel}</span>
                    ${privBadge}
                    ${hiddenBadge}
                </div>
                <span class="suggestion-time">${escapeHTML(s.created_at || "")}</span>
            </div>
            <p class="suggestion-content">${escapeHTML(s.content)}</p>
            ${adminControls}
        </div>
    `;
}

async function submitSuggestion() {
    const nicknameEl = document.getElementById("suggestionsNickname");
    const contentEl = document.getElementById("suggestionsContent");
    const errorEl = document.getElementById("suggestionsError");
    const submitBtn = document.getElementById("suggestionsSubmitBtn");

    const nickname = nicknameEl?.value.trim() || "";
    const content = contentEl?.value.trim() || "";

    if (!nickname) {
        showSuggestionsError(t("suggestions.nicknameRequired"));
        return;
    }
    if (!content) {
        showSuggestionsError(t("suggestions.contentRequired"));
        return;
    }

    if (submitBtn) submitBtn.disabled = true;
    if (errorEl) errorEl.style.display = "none";

    const visEl = document.querySelector('input[name="suggestionsVisibility"]:checked');
    const visibility = visEl ? visEl.value : "public";

    try {
        const resp = await fetch("/api/suggestions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nickname, content, visibility }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || "Submit failed");

        if (nicknameEl) nicknameEl.value = "";
        if (contentEl) { contentEl.value = ""; updateSuggestionsCharCount(); }

        await loadSuggestions();
    } catch (err) {
        showSuggestionsError(err.message);
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
}

async function deleteSuggestion(sid) {
    if (!confirm(t("suggestions.confirmDelete") || "Confirm delete?")) return;
    try {
        const resp = await fetch(`/api/suggestions/${sid}`, {
            method: "DELETE",
            headers: adminHeaders(),
        });
        if (!resp.ok) { const d = await resp.json(); throw new Error(d.error); }
        await loadSuggestions();
    } catch (err) {
        alert(err.message);
    }
}

async function restoreSuggestion(sid) {
    try {
        const resp = await fetch(`/api/suggestions/${sid}/restore`, {
            method: "POST",
            headers: adminHeaders(),
        });
        if (!resp.ok) { const d = await resp.json(); throw new Error(d.error); }
        await loadSuggestions();
    } catch (err) {
        alert(err.message);
    }
}

async function updateSuggestionStatus(sid, newStatus) {
    try {
        const resp = await fetch(`/api/suggestions/${sid}/status`, {
            method: "PUT",
            headers: { ...adminHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) { const d = await resp.json(); throw new Error(d.error); }
        // 不重新加载列表，只更新徽章颜色
        const badge = document.querySelector(`.suggestion-status-badge[data-sid="${sid}"]`);
        if (badge) {
            badge.className = `suggestion-status-badge status-${newStatus}`;
            const labels = {
                "pending": t("suggestions.statusPending"),
                "in_progress": t("suggestions.statusInProgress"),
                "completed": t("suggestions.statusCompleted"),
            };
            badge.textContent = labels[newStatus] || newStatus;
        }
    } catch (err) {
        alert(err.message);
    }
}

function adminLogin() {
    const key = prompt(t("suggestions.adminPrompt") || "Enter admin key:");
    if (key !== null && key.trim()) {
        adminKey = key.trim();
        updateAdminUI();
        loadSuggestions();
    }
}

function adminLogout() {
    adminKey = "";
    updateAdminUI();
    loadSuggestions();
}

function updateAdminUI() {
    const loginBtn = document.getElementById("suggestionsAdminBtn");
    const adminBar = document.getElementById("suggestionsAdminBar");
    if (loginBtn) {
        loginBtn.textContent = isAdmin() ? t("suggestions.adminLogout") : t("suggestions.adminLogin");
        loginBtn.className = isAdmin() ? "btn-secondary btn-xs" : "btn-primary btn-xs";
    }
    if (adminBar) {
        adminBar.style.display = isAdmin() ? "flex" : "none";
    }
}

function showSuggestionsError(msg) {
    const errorEl = document.getElementById("suggestionsError");
    if (errorEl) {
        errorEl.textContent = msg;
        errorEl.style.display = "block";
        setTimeout(() => { errorEl.style.display = "none"; }, 4000);
    }
}

function updateSuggestionsCharCount() {
    const contentEl = document.getElementById("suggestionsContent");
    const countEl = document.getElementById("suggestionsCharCount");
    if (contentEl && countEl) {
        countEl.textContent = `${contentEl.value.length}/2000`;
    }
}

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
}

// ---- 意见箱事件绑定 ----
(function initSuggestions() {
    const modal = document.getElementById("suggestionsModal");
    if (!modal) return;

    const closeBtn = document.getElementById("suggestionsClose");
    if (closeBtn) closeBtn.addEventListener("click", closeSuggestions);

    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeSuggestions();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal.style.display === "flex") {
            closeSuggestions();
        }
    });

    const submitBtn = document.getElementById("suggestionsSubmitBtn");
    if (submitBtn) submitBtn.addEventListener("click", submitSuggestion);

    const refreshBtn = document.getElementById("suggestionsRefreshBtn");
    if (refreshBtn) refreshBtn.addEventListener("click", loadSuggestions);

    const adminBtn = document.getElementById("suggestionsAdminBtn");
    if (adminBtn) {
        adminBtn.addEventListener("click", () => {
            if (isAdmin()) adminLogout(); else adminLogin();
        });
    }

    const contentEl = document.getElementById("suggestionsContent");
    if (contentEl) {
        contentEl.addEventListener("input", updateSuggestionsCharCount);
        contentEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                submitSuggestion();
            }
        });
    }
})();
