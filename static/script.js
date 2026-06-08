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

tutorialBtn.addEventListener("click", () => {
    tutorialModal.style.display = "flex";
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

    // 草稿信息
    if (data.draft_info) {
        const draft = data.draft_info;
        const draftCard = document.createElement("div");
        draftCard.className = "result-card";
        draftCard.innerHTML = `
            <h3>✂️ 剪映草稿已生成</h3>
            <p style="margin-bottom:8px;">草稿名称: <strong>${draft.draft_name}</strong></p>
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
