from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def test_frontend_explicitly_appends_optional_source_font_file():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function buildConversionFormData" in script
    assert 'formData.delete("font_file")' in script
    assert 'formData.append("font_file", targetFile' in script
    assert 'formData.delete("source_font_file")' in script
    assert 'formData.append("source_font_file", sourceFile' in script


def test_frontend_uses_background_conversion_jobs():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    markup = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'xhr.open("POST", "/api/convert-jobs")' in script
    assert "function pollConversionJob" in script
    assert "download_url" in script
    assert 'id="queue-info"' in markup
    assert 'id="recent-conversion"' in markup
    assert "function updateQueueInfo" in script
    assert "function updateRecentConversion" in script
    assert "queue_position" in script
    assert "recent_conversion" in script


def test_frontend_loads_initial_studio_status():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function loadStudioStatus" in script
    assert 'fetch("/api/status"' in script
    assert "recent_conversions" in script
    assert "function renderRecentConversions" in script


def test_frontend_reuses_download_blob_for_result_preview():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function prepareCompletedDownload" in script
    assert "URL.createObjectURL(blob)" in script
    assert "await applyPreviewFont(activeDownloadUrl)" in script
    assert "new FontFace" in script


def test_frontend_includes_studio_motion_components():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    styles = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    markup = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    assert "function initTextFlipBadges" in script
    assert "function initStudioBackground" in script
    assert 'id="studio-background"' in markup
    assert 'data-text-flip' in markup
    assert ".text-flip-badge" in styles
    assert ".studio-background" in styles
    assert "prefers-reduced-motion" in styles


def test_frontend_previews_uploaded_fonts_before_conversion():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function applyFilePreview" in script
    assert 'applyFilePreview("target", file)' in script
    assert 'applyFilePreview("source", file)' in script
    assert 'target-preview-output' in script
    assert 'source-preview-output' in script


def test_frontend_shows_default_preview_cards_before_upload():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    styles = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    markup = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="target-preview-card" class="font-preview-card" hidden' not in markup
    assert 'id="result-preview-card" class="font-preview-card result-preview-card" hidden' not in markup
    assert 'data-empty-preview="true"' in markup
    assert "function showDefaultPreview" in script
    assert 'showDefaultPreview("target")' in script
    assert 'showDefaultPreview("result")' in script
    assert '.font-preview-card[data-empty-preview="true"]' in styles


def test_frontend_can_clear_uploaded_fonts():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    markup = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="clear-font-file"' in markup
    assert 'id="clear-source-font-file"' in markup
    assert "clearTargetFileButton.addEventListener" in script
    assert "clearSourceFileButton.addEventListener" in script
    assert 'fileInput.value = ""' in script
    assert 'sourceFileInput.value = ""' in script


def test_frontend_uses_single_weight_strength_input():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    markup = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="effect-units"' in markup
    assert 'name="effect_units"' in markup
    assert "effectInput" in script
    assert "effectXInput" not in script
    assert "effectYInput" not in script
    assert "<span>水平效果" not in markup
    assert "<span>垂直效果" not in markup


def test_frontend_changelog_key_updates_for_latest_entry():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "ttf-tool-changelog-2026-06-16-2248" in script


def test_frontend_uses_indeterminate_progress_during_conversion():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function setProcessingProgress" in script
    assert 'progressBar.removeAttribute("value")' in script
    assert "正在转换字体" in script


def test_status_message_uses_full_action_width():
    styles = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".status" in styles
    assert "grid-column: 1 / -1" in styles
