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
const CHANGELOG_STORAGE_KEY = "ttf-tool-changelog-2026-06-16-1636";
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
    const { blob, disposition } = await submitConversion(formData);
    const filename = getDownloadName(disposition, file.name);
    activeDownloadUrl = URL.createObjectURL(blob);
    downloadLink.href = activeDownloadUrl;
    downloadLink.download = filename;
    downloadLink.textContent = `下载 ${filename}`;
    downloadLink.hidden = false;
    applyPreviewFont(activeDownloadUrl);
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

function submitConversion(formData) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/convert");
    xhr.responseType = "blob";

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }

      const uploadPercent = Math.round((event.loaded / event.total) * 100);
      setProgress(Math.min(70, Math.round(uploadPercent * 0.7)), `正在上传 ${uploadPercent}%`);
    });

    xhr.upload.addEventListener("load", () => {
      setProcessingProgress("正在转换字体...");
      statusText.textContent = "正在转换字体...";
    });

    xhr.addEventListener("load", async () => {
      stopProgressTimer();
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({
          blob: xhr.response,
          disposition: xhr.getResponseHeader("content-disposition"),
        });
        return;
      }

      reject(new Error(await readXhrError(xhr)));
    });

    xhr.addEventListener("error", () => {
      stopProgressTimer();
      reject(new Error("网络错误，转换请求未完成"));
    });

    xhr.addEventListener("abort", () => {
      stopProgressTimer();
      reject(new Error("转换请求已取消"));
    });

    xhr.send(formData);
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
