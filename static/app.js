const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#font-file");
const fileMeta = document.querySelector("#file-meta");
const sourceFileInput = document.querySelector("#source-font-file");
const sourceFileMeta = document.querySelector("#source-file-meta");
const clearTargetFileButton = document.querySelector("#clear-font-file");
const clearSourceFileButton = document.querySelector("#clear-source-font-file");
const scaleInput = document.querySelector("#scale-percent");
const scaleRange = document.querySelector("#scale-range");
const effectInput = document.querySelector("#effect-units");
const spacingInputs = [
  document.querySelector("#spacing-left"),
  document.querySelector("#spacing-right"),
  document.querySelector("#spacing-top"),
  document.querySelector("#spacing-bottom"),
];
const submitButton = document.querySelector("#submit-button");
const downloadLink = document.querySelector("#download-link");
const statusText = document.querySelector("#status");
const errorMessage = document.querySelector("#error-message");
const progressBar = document.querySelector("#progress-bar");
const progressLabel = document.querySelector("#progress-label");
const progressPercent = document.querySelector("#progress-percent");
const queueInfo = document.querySelector("#queue-info");
const recentConversion = document.querySelector("#recent-conversion");
const previewText = document.querySelector("#preview-text");
const changelogButton = document.querySelector("#changelog-button");
const changelogDialog = document.querySelector("#changelog-dialog");
const resultPreviewStatus = document.querySelector("[data-preview-status]");
const previewSlots = {
  target: {
    card: document.querySelector("#target-preview-card"),
    output: document.querySelector("#target-preview-output"),
    style: document.createElement("style"),
    fontFace: null,
    loadToken: 0,
  },
  source: {
    card: document.querySelector("#source-preview-card"),
    output: document.querySelector("#source-preview-output"),
    style: document.createElement("style"),
    fontFace: null,
    loadToken: 0,
  },
  result: {
    card: document.querySelector("#result-preview-card"),
    output: document.querySelector("#preview-output"),
    style: document.createElement("style"),
    fontFace: null,
    loadToken: 0,
  },
};
const previewFileUrls = {
  target: null,
  source: null,
};
const CHANGELOG_STORAGE_KEY = "ttf-tool-changelog-2026-06-16-2248";
let activeDownloadUrl = null;
let studioStatusTimer = null;
let stopTextFlipBadges = null;
let stopStudioBackground = null;

Object.values(previewSlots).forEach((slot) => {
  document.head.appendChild(slot.style);
});

if (changelogButton && changelogDialog) {
  changelogButton.addEventListener("click", () => {
    openChangelog();
  });

  changelogDialog.addEventListener("close", () => {
    markChangelogSeen();
  });

  window.addEventListener("load", () => {
    if (!hasSeenChangelog()) {
      openChangelog();
    }
  });
}

fileInput.addEventListener("change", () => {
  clearDownload();
  const file = fileInput.files[0];
  if (!file) {
    clearFilePreview("target");
    fileMeta.textContent = "用于缩放、加粗、变细或作为字符替换目标";
    clearTargetFileButton.hidden = true;
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  fileMeta.textContent = `${file.name} · ${sizeMb.toFixed(2)}MB`;
  clearTargetFileButton.hidden = false;
  applyFilePreview("target", file);
  statusText.textContent = "等待转换";
  setProgress(0, "等待开始");
});

clearTargetFileButton.addEventListener("click", () => {
  fileInput.value = "";
  clearDownload();
  clearFilePreview("target");
  clearTargetFileButton.hidden = true;
  fileMeta.textContent = "用于缩放、加粗、变细或作为字符替换目标";
  statusText.textContent = "等待上传字体";
});

sourceFileInput.addEventListener("change", () => {
  clearDownload();
  const file = sourceFileInput.files[0];
  if (!file) {
    clearFilePreview("source");
    sourceFileMeta.textContent = "上传后可把 A 的指定字符替换到当前字体";
    clearSourceFileButton.hidden = true;
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  sourceFileMeta.textContent = `${file.name} · ${sizeMb.toFixed(2)}MB`;
  clearSourceFileButton.hidden = false;
  applyFilePreview("source", file);
});

clearSourceFileButton.addEventListener("click", () => {
  sourceFileInput.value = "";
  clearDownload();
  clearFilePreview("source");
  clearSourceFileButton.hidden = true;
  sourceFileMeta.textContent = "上传后可把 A 的指定字符替换到当前字体";
});

previewText.addEventListener("input", () => {
  updatePreviewText();
});

scaleInput.addEventListener("input", () => {
  scaleRange.value = clampNumber(scaleInput.value, 10, 300, 100);
});

scaleRange.addEventListener("input", () => {
  scaleInput.value = scaleRange.value;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  clearDownload();

  const file = fileInput.files[0];
  if (!file) {
    showError("请选择一个 .ttf 字体文件");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".ttf")) {
    showError("只支持 .ttf 字体文件");
    return;
  }

  const sourceFile = sourceFileInput.files[0];
  if (sourceFile && !sourceFile.name.toLowerCase().endsWith(".ttf")) {
    showError("A 来源字体只支持 .ttf 字体文件");
    return;
  }

  const scale = Number(scaleInput.value);
  if (!Number.isInteger(scale) || scale < 10 || scale > 300) {
    showError("缩放比例必须在 10% 到 300% 之间");
    return;
  }

  const effect = Number(effectInput.value);
  if (!isValidEffect(effect)) {
    showError("字重强度必须在 0 到 100 字体单位之间");
    return;
  }

  const spacingValues = spacingInputs.map((input) => Number(input.value));
  if (spacingValues.some((value) => !isValidSpacing(value))) {
    showError("上下左右间距数值必须在 -50 到 50 之间");
    return;
  }

  submitButton.disabled = true;
  statusText.textContent = "正在上传...";
  setProgress(0, "准备上传");
  showResultPreviewLoading("等待转换结果");

  try {
    const formData = buildConversionFormData();
    const job = await submitConversionJob(formData);
    setJobProgress(job);
    const completedJob = await pollConversionJob(job.job_id);
    const filename = completedJob.download_name || getDownloadName("", file.name);
    showDownloadLink(completedJob.download_url, filename);
    setProgress(100, "转换完成");
    statusText.textContent = "转换完成，正在加载预览...";
    await prepareCompletedDownload(completedJob, filename);
    statusText.textContent = "转换完成，点击下载按钮保存文件";
    setProgress(100, "转换完成");
  } catch (error) {
    statusText.textContent = "转换失败";
    setProgress(0, "转换失败");
    showError(error.message || "转换失败，请换一个字体文件重试");
  } finally {
    submitButton.disabled = false;
    loadStudioStatus();
  }
});

function clampNumber(value, min, max, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.round(number)));
}

function isValidEffect(value) {
  return Number.isFinite(value) && value >= 0 && value <= 100;
}

function isValidSpacing(value) {
  return Number.isFinite(value) && value >= -50 && value <= 50;
}

function submitConversionJob(formData) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/convert-jobs");

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }

      const uploadPercent = Math.round((event.loaded / event.total) * 100);
      setProgress(Math.min(70, Math.round(uploadPercent * 0.7)), `正在上传 ${uploadPercent}%`);
    });

    xhr.upload.addEventListener("load", () => {
      setProcessingProgress("正在创建后台任务...");
      statusText.textContent = "正在创建后台任务...";
    });

    xhr.addEventListener("load", async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("后台任务响应无法读取"));
        }
        return;
      }

      reject(new Error(await readXhrError(xhr)));
    });

    xhr.addEventListener("error", () => {
      reject(new Error("网络错误，后台任务未创建"));
    });

    xhr.addEventListener("abort", () => {
      reject(new Error("后台任务请求已取消"));
    });

    xhr.send(formData);
  });
}

async function pollConversionJob(jobId) {
  if (!jobId) {
    throw new Error("后台任务编号为空");
  }

  while (true) {
    await delay(2000);
    const response = await fetch(`/api/convert-jobs/${encodeURIComponent(jobId)}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(await readFetchError(response));
    }

    const job = await response.json();
    setJobProgress(job);
    if (job.status === "complete") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error || job.message || "转换失败");
    }
  }
}

function setJobProgress(job) {
  if (!job) {
    return;
  }
  updateQueueInfo(job);
  renderRecentConversions(job.recent_conversions || asRecentList(job.recent_conversion));
  if (job.status === "complete") {
    setProgress(100, job.message || "转换完成");
    statusText.textContent = job.message || "转换完成";
    return;
  }
  if (job.status === "failed") {
    setProgress(0, "转换失败");
    statusText.textContent = "转换失败";
    return;
  }
  if (job.status === "queued") {
    setProgress(job.progress || 5, job.message || "排队等待转换");
    statusText.textContent = job.message || "排队等待转换";
    return;
  }

  setProcessingProgress(job.message || "后台正在转换字体...");
  statusText.textContent = job.message || "后台正在转换字体...";
}

function delay(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

async function loadStudioStatus() {
  try {
    const response = await fetch("/api/status", {
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    if (queueInfo && payload.queue_message) {
      queueInfo.textContent = payload.queue_message;
    }
    renderRecentConversions(payload.recent_conversions || asRecentList(payload.recent_conversion));
  } catch {
    if (queueInfo) {
      queueInfo.textContent = "排队状态暂时无法读取";
    }
  }
}

function updateQueueInfo(job) {
  if (!queueInfo) {
    return;
  }
  const position = Number(job.queue_position || 0);
  if (job.status === "queued" && position > 0) {
    queueInfo.textContent = `当前排队第 ${position} 个，前面 ${Math.max(0, position - 1)} 个`;
    return;
  }
  if (job.status === "running" && position > 0) {
    queueInfo.textContent = `当前第 ${position} 个，正在转换`;
    return;
  }
  if (job.status === "complete") {
    queueInfo.textContent = "当前任务已完成";
    return;
  }
  if (job.status === "failed") {
    queueInfo.textContent = "当前任务失败";
    return;
  }
  queueInfo.textContent = "当前没有排队任务";
}

function updateRecentConversion(recent) {
  renderRecentConversions(asRecentList(recent));
}

function asRecentList(recent) {
  return recent ? [recent] : [];
}

function renderRecentConversions(recentList) {
  if (!recentConversion) {
    return;
  }
  const items = Array.isArray(recentList) ? recentList.slice(0, 5) : [];
  recentConversion.replaceChildren();
  if (!items.length) {
    recentConversion.textContent = "暂无最近转换记录";
    return;
  }

  items.forEach((recent) => {
    const row = document.createElement("div");
    row.className = "recent-item";

    const region = document.createElement("span");
    region.className = "recent-region";
    region.textContent = recent.region || "未知地区";

    const duration = document.createElement("span");
    duration.className = "recent-duration";
    duration.textContent = `用时 ${formatDuration(recent.duration_seconds)}`;

    const time = document.createElement("span");
    time.className = "recent-time";
    time.textContent = formatCompletedTime(recent.completed_at);

    row.append(region, duration, time);
    recentConversion.append(row);
  });
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) {
    return "未知";
  }
  if (value < 60) {
    return `${value.toFixed(1)} 秒`;
  }
  const minutes = Math.floor(value / 60);
  const restSeconds = Math.round(value % 60);
  return `${minutes} 分 ${restSeconds} 秒`;
}

function formatCompletedTime(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) {
    return "";
  }
  return new Date(value * 1000).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildConversionFormData() {
  const formData = new FormData(form);
  const targetFile = fileInput.files[0];
  const sourceFile = sourceFileInput.files[0];

  formData.delete("font_file");
  if (targetFile) {
    formData.append("font_file", targetFile, targetFile.name);
  }

  formData.delete("source_font_file");
  if (sourceFile) {
    formData.append("source_font_file", sourceFile, sourceFile.name);
  }

  return formData;
}

async function prepareCompletedDownload(job, filename) {
  const downloadUrl = job.download_url;
  if (!downloadUrl) {
    throw new Error("转换完成但下载地址为空");
  }

  showDownloadLink(downloadUrl, filename);
  showResultPreviewLoading("正在下载预览字体...");
  const response = await fetch(downloadUrl, {
    cache: "no-store",
  });
  if (!response.ok) {
    showResultPreviewLoading("预览加载失败，可直接下载文件");
    return;
  }

  const blob = await response.blob();
  if (activeDownloadUrl) {
    URL.revokeObjectURL(activeDownloadUrl);
  }
  activeDownloadUrl = URL.createObjectURL(blob);
  showDownloadLink(activeDownloadUrl, filename);
  await applyPreviewFont(activeDownloadUrl);
}

function showDownloadLink(url, filename) {
  downloadLink.href = url;
  downloadLink.download = filename;
  downloadLink.textContent = `下载 ${filename}`;
  downloadLink.hidden = false;
}

async function readXhrError(xhr) {
  const contentType = xhr.getResponseHeader("content-type") || "";
  const text = xhr.response instanceof Blob ? await xhr.response.text() : xhr.responseText;
  if (contentType.includes("application/json")) {
    try {
      const data = JSON.parse(text);
      return data.detail || "转换失败";
    } catch {
      return "转换失败";
    }
  }
  return text || "转换失败";
}

async function readFetchError(response) {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();
  if (contentType.includes("application/json")) {
    try {
      const data = JSON.parse(text);
      return data.detail || data.error || "转换失败";
    } catch {
      return "转换失败";
    }
  }
  return text || "转换失败";
}

function setProgress(percent, label) {
  const bounded = Math.min(100, Math.max(0, Math.round(percent)));
  progressBar.max = 100;
  progressBar.setAttribute("value", String(bounded));
  progressBar.value = bounded;
  progressPercent.textContent = `${bounded}%`;
  progressLabel.textContent = label;
  progressBar.dataset.state = bounded >= 100 ? "complete" : "idle";
}

function setProcessingProgress(label) {
  progressBar.removeAttribute("value");
  progressBar.dataset.state = "processing";
  progressPercent.textContent = "处理中";
  progressLabel.textContent = label;
}

function getDownloadName(disposition, sourceName) {
  if (disposition) {
    const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch) {
      return decodeURIComponent(utfMatch[1]);
    }

    const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
    if (asciiMatch) {
      return asciiMatch[1];
    }
  }

  return sourceName.replace(/\.ttf$/i, "-converted.ttf");
}

async function applyPreviewFont(fontUrl) {
  await setPreviewFont("result", fontUrl, "转换后字体已加载");
}

function applyFilePreview(slotName, file) {
  clearFilePreview(slotName);
  previewFileUrls[slotName] = URL.createObjectURL(file);
  setPreviewFont(slotName, previewFileUrls[slotName], "字体已加载");
}

async function setPreviewFont(slotName, fontUrl, loadedMessage) {
  const slot = previewSlots[slotName];
  const token = slot.loadToken + 1;
  const fontFamily = `${slotName}Preview-${Date.now()}`;
  slot.loadToken = token;
  clearPreviewFontFace(slot);

  slot.style.textContent = "";
  slot.card.hidden = false;
  slot.card.dataset.loading = "true";
  delete slot.card.dataset.emptyPreview;
  delete slot.card.dataset.loaded;
  setPreviewStatus(slotName, "正在加载字体...");
  updatePreviewText();

  if ("FontFace" in window && document.fonts) {
    const fontFace = new FontFace(fontFamily, `url("${fontUrl}") format("truetype")`, {
      display: "swap",
    });
    slot.fontFace = fontFace;
    document.fonts.add(fontFace);
    slot.output.style.fontFamily = `"${fontFamily}", "Microsoft YaHei", sans-serif`;
    try {
      await fontFace.load();
      if (slot.loadToken === token) {
        markPreviewLoaded(slotName, loadedMessage);
      }
      return;
    } catch {
      clearPreviewFontFace(slot);
    }
  }

  slot.style.textContent = `
    @font-face {
      font-family: "${fontFamily}";
      src: url("${fontUrl}") format("truetype");
      font-display: swap;
    }
  `;
  slot.output.style.fontFamily = `"${fontFamily}", "Microsoft YaHei", sans-serif`;
  markPreviewLoaded(slotName, loadedMessage);
}

function markPreviewLoaded(slotName, message) {
  const slot = previewSlots[slotName];
  delete slot.card.dataset.loading;
  delete slot.card.dataset.emptyPreview;
  slot.card.dataset.loaded = "true";
  setPreviewStatus(slotName, message);
}

function showResultPreviewLoading(message) {
  const slot = previewSlots.result;
  slot.card.hidden = false;
  slot.card.dataset.loading = "true";
  delete slot.card.dataset.emptyPreview;
  delete slot.card.dataset.loaded;
  setPreviewStatus("result", message);
  updatePreviewText();
}

function setPreviewStatus(slotName, message) {
  if (slotName === "result" && resultPreviewStatus) {
    resultPreviewStatus.textContent = message;
  }
}

function updatePreviewText() {
  const text = previewText.value || " ";
  Object.values(previewSlots).forEach((slot) => {
    slot.output.textContent = text;
  });
}

function clearDownload() {
  if (activeDownloadUrl) {
    URL.revokeObjectURL(activeDownloadUrl);
    activeDownloadUrl = null;
  }
  showDefaultPreview("result");
  updatePreviewText();
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  downloadLink.removeAttribute("download");
  downloadLink.textContent = "下载转换后的字体";
  setProgress(0, "等待开始");
}

function clearFilePreview(slotName) {
  if (previewFileUrls[slotName]) {
    URL.revokeObjectURL(previewFileUrls[slotName]);
    previewFileUrls[slotName] = null;
  }
  if (slotName === "target" || slotName === "result") {
    showDefaultPreview(slotName);
    return;
  }
  clearPreviewSlot(slotName);
}

function showDefaultPreview(slotName) {
  const slot = previewSlots[slotName];
  slot.loadToken += 1;
  clearPreviewFontFace(slot);
  slot.style.textContent = "";
  slot.output.style.removeProperty("font-family");
  slot.card.hidden = false;
  slot.card.dataset.emptyPreview = "true";
  delete slot.card.dataset.loading;
  delete slot.card.dataset.loaded;
  if (slotName === "result") {
    setPreviewStatus("result", "绛夊緟杞崲");
  }
  updatePreviewText();
}

function clearPreviewSlot(slotName) {
  const slot = previewSlots[slotName];
  slot.loadToken += 1;
  clearPreviewFontFace(slot);
  slot.style.textContent = "";
  slot.output.style.removeProperty("font-family");
  slot.card.hidden = true;
  delete slot.card.dataset.emptyPreview;
  delete slot.card.dataset.loading;
  delete slot.card.dataset.loaded;
  if (slotName === "result") {
    setPreviewStatus("result", "等待转换");
  }
}

function clearPreviewFontFace(slot) {
  if (slot.fontFace && document.fonts && typeof document.fonts.delete === "function") {
    document.fonts.delete(slot.fontFace);
  }
  slot.fontFace = null;
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.hidden = true;
  errorMessage.textContent = "";
}

function openChangelog() {
  if (!changelogDialog) {
    return;
  }
  if (changelogDialog.open) {
    return;
  }
  if (typeof changelogDialog.showModal === "function") {
    changelogDialog.showModal();
    return;
  }
  changelogDialog.setAttribute("open", "");
}

function hasSeenChangelog() {
  try {
    return window.localStorage.getItem(CHANGELOG_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function markChangelogSeen() {
  try {
    window.localStorage.setItem(CHANGELOG_STORAGE_KEY, "1");
  } catch {
    // localStorage can be unavailable in private or restricted browser contexts.
  }
}

function initDropzones() {
  document.querySelectorAll(".file-drop").forEach((dropzone) => {
    const input = dropzone.querySelector('input[type="file"]');
    if (!input) {
      return;
    }

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, () => {
        dropzone.classList.remove("is-dragging");
      });
    });

    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      const file = event.dataTransfer.files[0];
      if (!file) {
        return;
      }
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      input.files = dataTransfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
}

function initTextFlipBadges() {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduceMotion.matches) {
    return () => {};
  }

  const timers = [];
  document.querySelectorAll("[data-text-flip]").forEach((element) => {
    const words = (element.dataset.flipWords || "")
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean);
    if (words.length < 2) {
      return;
    }

    let index = Math.max(0, words.indexOf(element.textContent.trim()));
    element.textContent = words[index] || words[0];
    const timer = window.setInterval(() => {
      element.classList.add("is-flipping");
      window.setTimeout(() => {
        index = (index + 1) % words.length;
        element.textContent = words[index];
        element.classList.remove("is-flipping");
      }, 180);
    }, 2200);
    timers.push(timer);
  });

  return () => {
    timers.forEach((timer) => window.clearInterval(timer));
  };
}

function initStudioBackground() {
  const canvas = document.querySelector("#studio-background");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!canvas || reduceMotion.matches || window.innerWidth < 700) {
    return () => {};
  }

  const context = canvas.getContext("2d");
  if (!context) {
    return () => {};
  }

  const paths = Array.from({ length: 9 }, (_, index) => ({
    offset: index * 54,
    speed: 0.18 + index * 0.018,
    alpha: 0.09 + index * 0.008,
  }));
  let frameId = 0;
  let width = 0;
  let height = 0;
  let pixelRatio = 1;

  function resize() {
    pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * pixelRatio);
    canvas.height = Math.floor(height * pixelRatio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }

  function draw(time) {
    context.clearRect(0, 0, width, height);
    paths.forEach((path, index) => {
      const yBase = ((index + 1) / (paths.length + 1)) * height;
      context.beginPath();
      for (let x = -80; x <= width + 80; x += 18) {
        const wave = Math.sin((x + time * path.speed + path.offset) / 118) * 24;
        const drift = Math.cos((x + time * path.speed * 0.72) / 180) * 16;
        const y = yBase + wave + drift;
        if (x === -80) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      }
      context.strokeStyle = `rgba(15, 118, 110, ${path.alpha})`;
      context.lineWidth = 1.2;
      context.stroke();
    });
    frameId = window.requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener("resize", resize);
  frameId = window.requestAnimationFrame(draw);

  return () => {
    window.cancelAnimationFrame(frameId);
    window.removeEventListener("resize", resize);
  };
}

function cleanupStudioEnhancements() {
  if (studioStatusTimer) {
    window.clearInterval(studioStatusTimer);
    studioStatusTimer = null;
  }
  if (stopTextFlipBadges) {
    stopTextFlipBadges();
    stopTextFlipBadges = null;
  }
  if (stopStudioBackground) {
    stopStudioBackground();
    stopStudioBackground = null;
  }
}

showDefaultPreview("target");
showDefaultPreview("result");
initDropzones();
stopTextFlipBadges = initTextFlipBadges();
stopStudioBackground = initStudioBackground();
loadStudioStatus();
studioStatusTimer = window.setInterval(loadStudioStatus, 15000);
window.addEventListener("pagehide", cleanupStudioEnhancements);
