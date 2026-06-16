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
const previewSlots = {
  target: {
    card: document.querySelector("#target-preview-card"),
    output: document.querySelector("#target-preview-output"),
    style: document.createElement("style"),
  },
  source: {
    card: document.querySelector("#source-preview-card"),
    output: document.querySelector("#source-preview-output"),
    style: document.createElement("style"),
  },
  result: {
    card: document.querySelector("#result-preview-card"),
    output: document.querySelector("#preview-output"),
    style: document.createElement("style"),
  },
};
const previewFileUrls = {
  target: null,
  source: null,
};
const CHANGELOG_STORAGE_KEY = "ttf-tool-changelog-2026-06-16-2001";
let activeDownloadUrl = null;
let progressTimer = null;

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

  try {
    const formData = buildConversionFormData();
    const job = await submitConversionJob(formData);
    setJobProgress(job);
    const completedJob = await pollConversionJob(job.job_id);
    const filename = completedJob.download_name || getDownloadName("", file.name);
    const downloadUrl = completedJob.download_url;
    downloadLink.href = downloadUrl;
    downloadLink.download = filename;
    downloadLink.textContent = `下载 ${filename}`;
    downloadLink.hidden = false;
    applyPreviewFont(downloadUrl);
    setProgress(100, "转换完成");
    statusText.textContent = "转换完成，点击下载按钮保存文件";
  } catch (error) {
    statusText.textContent = "转换失败";
    setProgress(0, "转换失败");
    showError(error.message || "转换失败，请换一个字体文件重试");
  } finally {
    stopProgressTimer();
    submitButton.disabled = false;
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
      stopProgressTimer();
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
      stopProgressTimer();
      reject(new Error("网络错误，后台任务未创建"));
    });

    xhr.addEventListener("abort", () => {
      stopProgressTimer();
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
  updateRecentConversion(job.recent_conversion);
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
  queueInfo.textContent = "暂无排队任务";
}

function updateRecentConversion(recent) {
  if (!recentConversion) {
    return;
  }
  if (!recent) {
    recentConversion.textContent = "暂无最近转换记录";
    return;
  }
  const region = recent.region || "未知地区";
  const duration = formatDuration(recent.duration_seconds);
  recentConversion.textContent = `最近 ${region} 用户转换完成，用时 ${duration}`;
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
}

function setProcessingProgress(label) {
  stopProgressTimer();
  progressBar.removeAttribute("value");
  progressPercent.textContent = "处理中";
  progressLabel.textContent = label;
}

function stopProgressTimer() {
  if (progressTimer) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
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

function applyPreviewFont(fontUrl) {
  setPreviewFont("result", fontUrl);
}

function applyFilePreview(slotName, file) {
  clearFilePreview(slotName);
  previewFileUrls[slotName] = URL.createObjectURL(file);
  setPreviewFont(slotName, previewFileUrls[slotName]);
}

function setPreviewFont(slotName, fontUrl) {
  const slot = previewSlots[slotName];
  const fontFamily = `${slotName}Preview-${Date.now()}`;
  slot.style.textContent = `
    @font-face {
      font-family: "${fontFamily}";
      src: url("${fontUrl}") format("truetype");
    }
  `;
  slot.output.style.fontFamily = `"${fontFamily}", "Microsoft YaHei", sans-serif`;
  slot.card.hidden = false;
  updatePreviewText();
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
  clearPreviewSlot("result");
  updatePreviewText();
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  downloadLink.removeAttribute("download");
  downloadLink.textContent = "下载转换后的字体";
  if (queueInfo) {
    queueInfo.textContent = "暂无排队任务";
  }
  setProgress(0, "等待开始");
}

function clearFilePreview(slotName) {
  if (previewFileUrls[slotName]) {
    URL.revokeObjectURL(previewFileUrls[slotName]);
    previewFileUrls[slotName] = null;
  }
  clearPreviewSlot(slotName);
}

function clearPreviewSlot(slotName) {
  const slot = previewSlots[slotName];
  slot.style.textContent = "";
  slot.output.style.removeProperty("font-family");
  slot.card.hidden = true;
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

updatePreviewText();
