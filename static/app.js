const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#font-file");
const fileMeta = document.querySelector("#file-meta");
const sourceFileInput = document.querySelector("#source-font-file");
const sourceFileMeta = document.querySelector("#source-file-meta");
const scaleInput = document.querySelector("#scale-percent");
const scaleRange = document.querySelector("#scale-range");
const effectXInput = document.querySelector("#effect-x");
const effectYInput = document.querySelector("#effect-y");
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
const previewOutput = document.querySelector("#preview-output");
const previewStyle = document.createElement("style");
let activeDownloadUrl = null;
let progressTimer = null;
let previewFontFamily = null;

document.head.appendChild(previewStyle);

fileInput.addEventListener("change", () => {
  clearDownload();
  const file = fileInput.files[0];
  if (!file) {
    fileMeta.textContent = "输出会以 B 字体为基础";
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  fileMeta.textContent = `${file.name} · ${sizeMb.toFixed(2)}MB`;
  statusText.textContent = "等待转换";
  setProgress(0, "等待开始");
});

sourceFileInput.addEventListener("change", () => {
  const file = sourceFileInput.files[0];
  if (!file) {
    sourceFileMeta.textContent = "可选，用 A 的字符替换到 B";
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  sourceFileMeta.textContent = `${file.name} · ${sizeMb.toFixed(2)}MB`;
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

  const effectX = Number(effectXInput.value);
  const effectY = Number(effectYInput.value);
  if (!isValidEffect(effectX) || !isValidEffect(effectY)) {
    showError("水平和垂直效果数值必须在 -500 到 500 字体单位之间");
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
    const formData = new FormData(form);
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
  return Number.isFinite(value) && value >= -500 && value <= 500;
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
      setProgress(75, "正在转换字体...");
      startProcessingProgress();
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
  progressBar.value = bounded;
  progressPercent.textContent = `${bounded}%`;
  progressLabel.textContent = label;
}

function startProcessingProgress() {
  stopProgressTimer();
  progressTimer = window.setInterval(() => {
    const current = Number(progressBar.value);
    if (current < 95) {
      setProgress(current + 1, "正在转换字体...");
    }
  }, 250);
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
  previewFontFamily = `ConvertedPreview-${Date.now()}`;
  previewStyle.textContent = `
    @font-face {
      font-family: "${previewFontFamily}";
      src: url("${fontUrl}") format("truetype");
    }
  `;
  previewOutput.style.fontFamily = `"${previewFontFamily}", "Microsoft YaHei", sans-serif`;
  updatePreviewText();
}

function updatePreviewText() {
  previewOutput.textContent = previewText.value || " ";
}

function clearDownload() {
  if (activeDownloadUrl) {
    URL.revokeObjectURL(activeDownloadUrl);
    activeDownloadUrl = null;
  }
  previewStyle.textContent = "";
  previewFontFamily = null;
  previewOutput.style.removeProperty("font-family");
  updatePreviewText();
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  downloadLink.removeAttribute("download");
  downloadLink.textContent = "下载转换后的字体";
  setProgress(0, "等待开始");
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.hidden = true;
  errorMessage.textContent = "";
}

updatePreviewText();
