/**
 * Movie Music Matcher - 前端交互逻辑
 */

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
            `<p style="color:var(--error)">加载教程失败: ${err.message}</p>`;
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

// ---- 剪辑模式选择 ----
document.querySelectorAll(".editing-mode-cards .mode-card").forEach(card => {
    card.addEventListener("click", () => {
        document.querySelectorAll(".editing-mode-cards .mode-card")
            .forEach(c => c.classList.remove("active"));
        card.classList.add("active");
        editingMode = card.dataset.mode;
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
        exportPathHint.textContent = "默认: " + defaultPath;
        // 构建路径建议列表
        buildExportPathSuggestions(commonPaths, exportPathSuggestions, exportPathInput);
    } catch (err) {
        console.warn("加载默认导出路径失败:", err.message);
    }
}
loadDefaultExportPath();

// 构建路径建议列表
function buildExportPathSuggestions(paths, container, inputEl) {
    if (!paths.length) {
        container.style.display = "none";
        return;
    }
    let html = '<div class="path-suggestions-title">📂 常用路径（点击选择）：</div>';
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
    formData.append("video", videoFile);
    formData.append("mode", "manual");
    formData.append("editing_mode", editingMode);
    // 读取自定义导出路径
    customExportPath = exportPathInput.value.trim();
    if (customExportPath) {
        formData.append("custom_export_path", customExportPath);
    }
    audioFiles.forEach((f) => formData.append("audio", f));

    try {
        // 上传
        progressText.textContent = "正在上传文件...";
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

    throw new Error("处理超时（超过 5 分钟），请检查文件大小或重试");
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
                    <span class="result-label">电影类型</span>
                    <span class="result-value">${style.genre || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">情绪氛围</span>
                    <span class="result-value">${style.mood || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">色调风格</span>
                    <span class="result-value">${style.color_palette || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">画面节奏</span>
                    <span class="result-value">${style.pacing || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">视觉风格</span>
                    <span class="result-value">${style.visual_style || "—"}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">推荐音乐流派</span>
                    <span class="result-value">${style.recommended_music?.genre || "—"}</span>
                </div>
            </div>
            <div style="margin-top:12px;">
                <span class="result-label">核心主题</span>
                <div class="themes-list" style="margin-top:6px;">
                    ${(style.themes || []).map(t => `<span class="theme-tag">${t}</span>`).join("")}
                </div>
            </div>
        `;
    } else {
        styleContent.innerHTML = `<p style="color:var(--text-secondary)">风格分析结果解析中...</p>`;
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
                const name = m.file_path ? m.file_path.split(/[/\\]/).pop() : `音乐 ${i + 1}`;
                const isBest = i === 0 ? " 🏆" : "";

                return `
                <div class="match-item">
                    <div class="match-item-header">
                        <span class="match-item-name">${name}${isBest}</span>
                        <span class="match-item-score ${scoreClass}">${score} 分</span>
                    </div>
                    <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:6px;">
                        ${match.analysis || ""}
                    </p>
                    <div style="font-size:0.8rem;color:var(--text-secondary);">
                        BPM: ${m.tempo_bpm || "?"} | 调性: ${m.estimated_key || "?"} | 时长: ${m.duration_seconds || "?"}s
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
        matchContent.innerHTML = `<p style="color:var(--text-secondary)">未找到匹配结果</p>`;
    }

    // 智能剪辑信息
    if (data.smart_segments_info) {
        const ssi = data.smart_segments_info;
        const smartCard = document.createElement("div");
        smartCard.className = "result-card";
        const modeLabel = data.editing_mode === "video_first" ? "🎬 视频优先" : "🎵 音乐优先";
        smartCard.innerHTML = `
            <h3>✂️ 智能剪辑详情</h3>
            <div class="result-grid">
                <div class="result-item">
                    <span class="result-label">剪辑模式</span>
                    <span class="result-value">${modeLabel}</span>
                </div>
                <div class="result-item">
                    <span class="result-label">检测场景</span>
                    <span class="result-value">${ssi.scene_count || "?"} 个</span>
                </div>
                <div class="result-item">
                    <span class="result-label">生成片段</span>
                    <span class="result-value">${ssi.segment_count || "?"} 个</span>
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
            <h3>🎬 已识别电影</h3>
            <p><strong>${mi.movie_name}</strong> (${mi.year || ""}) — 置信度: ${mi.confidence || "?"}</p>
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
            <h3>🎵 音乐结构分析</h3>
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
            <h3>✂️ 剪映草稿已生成</h3>
            <p style="margin-bottom:8px;">草稿名称: <strong>${draft.draft_name}</strong></p>
            <p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">📁 导出位置: <code style="font-size:0.78rem;">${exportPath}</code></p>
            ${draft.capcut_draft_path
                ? `<p style="color:var(--success);">✅ 草稿已自动复制到剪映目录，请在剪映中打开查看！</p>`
                : `<p style="color:var(--text-secondary);">📂 草稿保存在: ${draft.draft_folder}</p>
                   <p style="color:var(--warning);">⚠️ 请手动将草稿文件夹复制到剪映草稿目录</p>`
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
    document.getElementById("updateAppVersion").textContent = "检测中...";
    document.getElementById("updateAppDesc").textContent = "—";
    document.getElementById("updateEditorName").textContent = "检测中...";
    document.getElementById("updateEditorVersion").textContent = "—";
    document.getElementById("updateCompatStatus").textContent = "检测中...";
    document.getElementById("updateJypRange").textContent = "—";
    document.getElementById("updateCapcutRange").textContent = "—";
    document.getElementById("updateAvailableSection").style.display = "none";
    document.getElementById("updateProgressSection").style.display = "none";
    document.getElementById("updateMessage").style.display = "none";
    document.getElementById("updateGitInfo").style.display = "none";
    document.getElementById("updateMethodRow").style.display = "none";
}

async function checkForUpdate() {
    try {
        const resp = await fetch("/api/check-update");
        const data = await resp.json();

        const compat = data.compatibility || {};

        // 填充当前版本信息
        document.getElementById("updateAppVersion").textContent =
            `Movie Music Matcher v${compat.app_version || "—"}`;
        document.getElementById("updateAppDesc").textContent =
            compat.description || "—";

        // 编辑器信息
        document.getElementById("updateEditorName").textContent =
            compat.editor_name || "未检测到";
        document.getElementById("updateEditorVersion").textContent =
            compat.editor_version || "未安装";

        // 兼容状态
        const compatStatus = document.getElementById("updateCompatStatus");
        if (compat.is_compatible) {
            compatStatus.innerHTML = '<span class="compat-badge compat-ok">✅ 当前版本兼容</span>';
        } else {
            compatStatus.innerHTML = '<span class="compat-badge compat-warn">⚠️ 版本不兼容，建议更新</span>';
        }

        // 兼容范围
        document.getElementById("updateJypRange").textContent =
            compat.compatible_jyp_range || "—";
        document.getElementById("updateCapcutRange").textContent =
            compat.compatible_capcut_range || "—";

        // 更新可用
        if (data.has_update && data.update_info) {
            const info = data.update_info;
            document.getElementById("updateLatestVersion").textContent =
                `v${info.version}`;
            document.getElementById("updateLatestDesc").textContent =
                info.description || "—";
            document.getElementById("updateLatestJyp").textContent =
                info.compatible_jyp_range || "—";
            document.getElementById("updateAvailableSection").style.display = "block";

            // 更新目标说明
            if (info.best_for_editor) {
                document.getElementById("updateLatestVersion").textContent =
                    `v${info.version}（适配 ${info.best_for_editor}）`;
            }

            // 更新方式
            const methodRow = document.getElementById("updateMethodRow");
            const methodSpan = document.getElementById("updateMethod");
            const gitInfo = document.getElementById("updateGitInfo");
            const gitBadge = document.getElementById("updateGitBadge");
            const gitDetail = document.getElementById("updateGitDetail");
            const startBtn = document.getElementById("startUpdateBtn");

            const updateMethod = data.update_method || "manual";

            if (updateMethod === "git") {
                methodRow.style.display = "flex";
                methodSpan.innerHTML = '<span class="compat-badge compat-ok">🔄 Git 自动更新</span>';
                startBtn.textContent = "🚀 一键 Git 更新";
                startBtn.className = "btn-primary btn-git-update";

                // Git 详情
                if (data.git_check) {
                    gitInfo.style.display = "block";
                    const gc = data.git_check;
                    if (gc.remote_url) {
                        gitBadge.innerHTML = '<span class="compat-badge compat-ok">✅ Git 已连接</span>';
                        gitDetail.innerHTML = `
                            远程仓库：${gc.remote_url}<br>
                            落后提交：<strong>${gc.behind_count || 0}</strong> 个
                        `;
                    } else {
                        gitBadge.innerHTML = '<span class="compat-badge compat-warn">⚠️ Git 未配置远程</span>';
                    }
                }
            } else {
                methodRow.style.display = "flex";
                methodSpan.innerHTML = '<span class="compat-badge compat-warn">📥 手动下载更新</span>';
                startBtn.textContent = "🚀 开始更新";
                startBtn.className = "btn-primary";

                // 显示 Git 设置指引
                if (data.git_check && data.git_check.error) {
                    gitInfo.style.display = "block";
                    gitBadge.innerHTML = '<span class="compat-badge compat-warn">💡 建议启用 Git 自动更新</span>';
                    gitDetail.textContent = data.git_check.error;
                }
            }
        } else {
            // 没有更新，显示提示
            const msg = document.getElementById("updateMessage");
            msg.style.display = "block";
            msg.className = "update-message update-message-info";
            msg.textContent = "✅ 当前已是最新版本，无需更新。";
        }
    } catch (err) {
        const msg = document.getElementById("updateMessage");
        msg.style.display = "block";
        msg.className = "update-message update-message-error";
        msg.textContent = "❌ 检查更新失败：" + err.message;
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
            throw new Error(startData.message || "更新启动失败");
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

    throw new Error("更新超时，请重试");
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
    v2Subtitle.style.display = "none";
    v3Subtitle.style.display = "";
    document.getElementById("v2Badge").style.opacity = "0.5";
    document.getElementById("v3Badge").style.opacity = "1";
    // 隐藏 v2 的教程和更新按钮
    document.getElementById("tutorialBtn").style.display = "none";
    document.getElementById("updateBtn").style.display = "none";
    initV3Mode();
}

function switchToV2() {
    isV3Mode = false;
    v2Content.style.display = "";
    v3Content.style.display = "none";
    v2Subtitle.style.display = "";
    v3Subtitle.style.display = "none";
    document.getElementById("v2Badge").style.opacity = "1";
    document.getElementById("v3Badge").style.opacity = "0.5";
    document.getElementById("tutorialBtn").style.display = "";
    document.getElementById("updateBtn").style.display = "";
}

// ---- v3 初始化 ----
let v3Initialized = false;

function initV3Mode() {
    if (v3Initialized) return;  // 防止重复绑定事件
    v3Initialized = true;

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
        document.getElementById("v3ExportPathHint").textContent = "默认: " + (data.default_path || "");
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

// ---- v3 简报创建 ----
async function createBrief() {
    const topic = document.getElementById("briefTopic").value.trim();
    if (!topic) {
        alert("请输入项目主题");
        return;
    }

    const briefData = {
        topic: topic,
        target_duration: parseInt(document.getElementById("briefDuration").value) || 120,
        platform: document.getElementById("briefPlatform").value,
        aspect_ratio: document.getElementById("briefAspectRatio").value,
        language: document.getElementById("briefLanguage").value,
        editing_mode: document.getElementById("briefEditingMode").value,
        narration_enabled: document.getElementById("briefNarration").value === "true",
        editing_preferences: document.getElementById("briefPreferences").value,
    };

    try {
        const resp = await fetch("/api/brief/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(briefData),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || "创建失败");

        v3TaskId = data.task_id;
        v3ProjectSlug = data.project_slug;

        // 显示上传区域
        document.getElementById("briefSection").style.display = "none";
        document.getElementById("v3UploadSection").style.display = "grid";
        document.getElementById("v3EditingSection").style.display = "block";
        document.getElementById("v3UploadBtnBar").style.display = "block";

        alert("✅ 简报已创建！项目: " + data.project_slug + "\n请选择视频和音乐文件后点击「开始管道处理」");
    } catch (err) {
        alert("创建简报失败: " + err.message);
    }
}

// ---- v3 上传设置 ----
function setupV3Upload() {
    const v3VideoBox = document.getElementById("v3VideoUploadBox");
    const v3AudioBox = document.getElementById("v3AudioUploadBox");
    const v3VideoInput = document.getElementById("v3VideoInput");
    const v3AudioInput = document.getElementById("v3AudioInput");

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
    if (!v3VideoFile) return;

    v3CustomExportPath = document.getElementById("v3ExportPathInput").value.trim();

    const formData = new FormData();
    formData.append("video", v3VideoFile);
    formData.append("project_slug", v3ProjectSlug);
    formData.append("editing_mode", v3EditingMode);
    if (v3CustomExportPath) {
        formData.append("custom_export_path", v3CustomExportPath);
    }
    v3AudioFiles.forEach(f => formData.append("audio", f));

    // 隐藏上传区，显示管道步骤
    document.getElementById("v3UploadBtnBar").style.display = "none";
    document.getElementById("pipelineSteps").style.display = "flex";
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
        await pollV3Pipeline();
    } catch (err) {
        alert("管道启动失败: " + err.message);
    }
}

// ---- v3 管道轮询 ----
// 跟踪当前等待的阶段完成状态，避免竞态条件
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

            // 更新阶段显示
            v3CurrentPhase = phase;
            updatePipelineStep(phase, "active");

            // 检查最终完成
            if (status === "completed") {
                markAllPipelineStepsDone();
                showV3Results(data);
                return;
            }

            // 检查是否到达阶段完成状态（等待确认）
            // 关键：只接受 _complete 且状态已改变（排除竞态）
            if (status.endsWith("_complete") && status !== lastStatus) {
                // 额外确认：状态对应的阶段与当前阶段一致
                const expectedComplete = phase + "_complete";
                if (status === expectedComplete || status !== lastStatus) {
                    updatePipelineStep(phase, "completed");
                    showApprovalPanel(phase, data);
                    return;
                }
            }

            if (status === "error") {
                throw new Error(data.message || "管道处理出错");
            }

            lastStatus = status;

            // 更新进度信息
            if (data.message) {
                updatePipelineStep(phase, "active");
            }
        } catch (err) {
            if (err.message && (err.message.includes("❌") || err.message.includes("失败"))) {
                alert("管道处理出错: " + err.message);
                return;
            }
            console.warn("v3 管道轮询失败，重试中...", err.message);
        }
    }

    alert("管道处理超时（超过 10 分钟）");
}

// ---- v3 确认面板 ----
function showApprovalPanel(phase, data) {
    const panel = document.getElementById("approvalPanel");
    panel.style.display = "block";

    const phaseNames = {
        "media_scan": "媒体扫描",
        "material_review": "素材审查",
        "story": "故事开发",
        "blueprint": "剪辑蓝图",
        "validate": "蓝图验证",
    };

    document.getElementById("approvalTitle").textContent =
        (phaseNames[phase] || phase) + " 完成";

    let summary = "";
    const review = document.getElementById("approvalReview");

    // 默认隐藏跳过按钮，各阶段按需显示
    document.getElementById("v3SkipBtn").style.display = "none";

    switch (phase) {
        case "media_scan":
            const scan = data.scan_preview || {};
            summary = `扫描了 ${scan.total_files || "?"} 个文件（${scan.duration_display || ""}）`;
            review.innerHTML = scan.files ? scan.files.map(f =>
                `<div style="padding:4px 0;">${f.filename} (${f.size_mb}MB, ${f.duration}s)</div>`
            ).join("") : "<p>已生成 media-manifest.json</p>";
            break;
        case "material_review":
            const rv = data.review || {};
            summary = `识别: ${rv.movie_name || "未知"} | 类型: ${rv.genre || ""} | 情绪: ${rv.mood || ""}`;
            review.innerHTML = `
                <p><strong>分类:</strong> 动作强度=${rv.action_intensity || ""}, 情绪范围=${(rv.emotional_range || []).join(", ")}</p>
                <p><strong>叙事用途:</strong> ${(rv.narrative_uses || []).join(", ")}</p>
            `;
            break;
        case "story":
            const st = data.story || {};
            summary = st.core_idea || "故事开发完成";
            review.innerHTML = `
                <p><strong>核心创意:</strong> ${st.core_idea || ""}</p>
                <p><strong>叙事结构:</strong> ${st.selected_structure || ""}</p>
                <p><strong>情绪曲线:</strong> ${st.emotional_curve || ""}</p>
                <p><strong>场景节拍:</strong> ${(st.scene_beats || []).length} 个</p>
            `;
            document.getElementById("v3SkipBtn").style.display = "";  // 故事可跳过
            break;
        case "blueprint":
            const bp = data.blueprint || {};
            summary = `${bp.total_clips || "?"} 个片段, ${bp.total_duration || "?"}s, 平均分 ${bp.avg_highlight_score || "?"}`;
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
                '<p style="margin-top:8px;">情绪分布: ' + JSON.stringify(bp.emotional_tones || {}) + '</p>';
            break;
        case "validate":
            const val = data.validation || {};
            summary = val.summary || "";
            review.innerHTML = (val.issues || []).map(i =>
                `<div style="padding:2px 0;color:${i.level === 'error' ? 'var(--error)' : 'var(--warning)'};">${i.level}: ${i.message}</div>`
            ).join("") || "<p>验证通过</p>";
            break;
        default:
            summary = "阶段完成";
            review.innerHTML = "<p>准备进入下一阶段</p>";
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
        alert("确认失败: " + err.message);
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
        alert("重试失败: " + err.message);
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
        alert("跳过失败: " + err.message);
        document.getElementById("approvalPanel").style.display = "block";
    }
}

// ---- v3 管道步骤可视化 ----
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
            <h3>✂️ 剪映草稿已生成</h3>
            <p>草稿: <strong>${draft.draft_name}</strong></p>
            <p class="export-path-display">📁 ${data.export_path || ""}</p>
            ${draft.capcut_draft_path ? '<p style="color:var(--success);">✅ 已同步到剪映目录</p>' : ''}
        </div>`;
    }

    // 审计报告
    if (data.audit) {
        const audit = data.audit;
        html += `<div class="result-card">
            <h3>📊 审计报告</h3>
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
            <h3>📋 补拍建议</h3>
            <p>P0(必须): ${pu.p0_count || 0} | P1(建议): ${pu.p1_count || 0} | P2(可选): ${pu.p2_count || 0}</p>
            ${(pu.p0_items || []).slice(0, 3).map(i =>
                `<div style="font-size:0.85rem;margin-top:4px;">• <strong>${i.missing_info || ""}</strong>: ${i.shot_spec?.subject || ""}</div>`
            ).join("")}
        </div>`;
    }

    document.getElementById("v3ResultContent").innerHTML = html || "<p>分析完成</p>";
    resultSection.scrollIntoView({ behavior: "smooth" });
}
