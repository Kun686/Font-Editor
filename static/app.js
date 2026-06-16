const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#font-file");
const fileMeta = document.querySelector("#file-meta");
const scaleInput = document.querySelector("#scale-percent");
const scaleRange = document.querySelector("#scale-range");
const effectXInput = document.querySelector("#effect-x");
const effectYInput = document.querySelector("#effect-y");
const submitButton = document.querySelector("#submit-button");
const downloadLink = document.querySelector("#download-link");
const statusText = document.querySelector("#status");
const errorMessage = document.querySelector("#error-message");
let activeDownloadUrl = null;

fileInput.addEventListener("change", () => {
  clearDownload();
  const file = fileInput.files[0];
  if (!file) {
    fileMeta.textContent = "最大 50MB，文件只用于本次转换";
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  fileMeta.textContent = `${file.name} · ${sizeMb.toFixed(2)}MB`;
  statusText.textContent = "等待转换";
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

  const scale = Number(scaleInput.value);
  if (!Number.isInteger(scale) || scale < 10 || scale > 300) {
    showError("缩放比例必须在 10% 到 300% 之间");
    return;
  }

  const effectX = Number(effectXInput.value);
  const effectY = Number(effectYInput.value);
  if (!isValidEffect(effectX) || !isValidEffect(effectY)) {
    showError("水平和垂直效果数值必须在 -50 到 50 之间");
    return;
  }

  submitButton.disabled = true;
  statusText.textContent = "正在上传并转换...";

  try {
    const formData = new FormData(form);
    const response = await fetch("/api/convert", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const detail = await readError(response);
      throw new Error(detail);
    }

    const blob = await response.blob();
    const filename = getDownloadName(response.headers.get("content-disposition"), file.name);
    activeDownloadUrl = URL.createObjectURL(blob);
    downloadLink.href = activeDownloadUrl;
    downloadLink.download = filename;
    downloadLink.textContent = `下载 ${filename}`;
    downloadLink.hidden = false;
    statusText.textContent = "转换完成，点击下载按钮保存文件";
  } catch (error) {
    statusText.textContent = "转换失败";
    showError(error.message || "转换失败，请换一个字体文件重试");
  } finally {
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
  return Number.isFinite(value) && value >= -50 && value <= 50;
}

async function readError(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json();
    return data.detail || "转换失败";
  }
  return await response.text();
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

function clearDownload() {
  if (activeDownloadUrl) {
    URL.revokeObjectURL(activeDownloadUrl);
    activeDownloadUrl = null;
  }
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  downloadLink.removeAttribute("download");
  downloadLink.textContent = "下载转换后的字体";
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.hidden = true;
  errorMessage.textContent = "";
}
