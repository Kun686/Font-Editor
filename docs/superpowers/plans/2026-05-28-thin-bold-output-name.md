# Thin Bold Output Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-controlled Thin/Bold glyph effects with separate horizontal and vertical values, plus user-controlled output filenames.

**Architecture:** Keep the existing FastAPI app and pure `font_processor.py` boundary. Tests define the new converter arguments and API form fields first, then the implementation updates backend validation and frontend controls.

**Tech Stack:** Python 3, FastAPI, fontTools, pytest, HTML/CSS/JavaScript.

---

### Task 1: Font Processor API

**Files:**
- Modify: `tests/test_font_processor.py`
- Modify: `font_processor.py`

- [ ] Add failing tests for `weight_mode="bold"` and `weight_mode="thin"` with `effect_x_percent` and `effect_y_percent`.
- [ ] Verify the tests fail because `convert_ttf` does not accept the new arguments.
- [ ] Replace the old boolean bold transform with mode-based `none/thin/bold` validation.
- [ ] Convert horizontal and vertical effect percentages to font units using `unitsPerEm`.
- [ ] Run `python -m pytest tests/test_font_processor.py -v`.

### Task 2: API Form Fields

**Files:**
- Modify: `tests/test_api.py`
- Modify: `main.py`

- [ ] Add failing tests for `weight_mode`, `effect_x_percent`, `effect_y_percent`, and `output_name`.
- [ ] Verify the tests fail because the endpoint ignores the new fields.
- [ ] Update `/api/convert` to pass the new effect fields to `convert_ttf`.
- [ ] Sanitize `output_name`, append `.ttf` when missing, and use it in `Content-Disposition`.
- [ ] Run `python -m pytest tests/test_api.py -v`.

### Task 3: Frontend Controls

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `README.md`

- [ ] Replace the Bold checkbox with mode controls for none, Thin, and Bold.
- [ ] Add horizontal effect, vertical effect, and output filename fields.
- [ ] Update client-side validation and status text.
- [ ] Update documentation.
- [ ] Run `python -m pytest -v` and restart the local server.
