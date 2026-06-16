from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def test_frontend_explicitly_appends_optional_source_font_file():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function buildConversionFormData" in script
    assert 'formData.delete("font_file")' in script
    assert 'formData.append("font_file", targetFile' in script
    assert 'formData.delete("source_font_file")' in script
    assert 'formData.append("source_font_file", sourceFile' in script


def test_frontend_previews_uploaded_fonts_before_conversion():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function applyFilePreview" in script
    assert 'applyFilePreview("target", file)' in script
    assert 'applyFilePreview("source", file)' in script
    assert 'target-preview-output' in script
    assert 'source-preview-output' in script


def test_frontend_uses_indeterminate_progress_during_conversion():
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function setProcessingProgress" in script
    assert 'progressBar.removeAttribute("value")' in script
    assert "正在转换字体" in script


def test_status_message_uses_full_action_width():
    styles = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".status" in styles
    assert "grid-column: 1 / -1" in styles
