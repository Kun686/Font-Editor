from io import BytesIO
from pathlib import Path
import shutil
from time import sleep

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont
import pytest

import main
from main import ConversionJob, RUNTIME_DIR, _job_payload, app, jobs, jobs_lock


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_job_runtime():
    with jobs_lock:
        jobs.clear()
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    yield
    with jobs_lock:
        jobs.clear()
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)


def test_convert_endpoint_returns_ttf_download(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "125",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "font/ttf"
    assert "attachment" in response.headers["content-disposition"]
    assert "demo-125pct-bold-u5.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"][0] > 625


def _wait_for_job(job_id: str) -> dict[str, object]:
    for _ in range(50):
        status_response = client.get(f"/api/convert-jobs/{job_id}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "complete":
            return status_payload
        sleep(0.05)
    raise AssertionError("conversion job did not complete")


def test_async_conversion_job_completes_and_downloads_ttf(sample_ttf_bytes):
    response = client.post(
        "/api/convert-jobs",
        data={
            "scale_percent": "125",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] in {"queued", "running", "complete"}
    assert payload["download_name"] == "demo-125pct-bold-u5.ttf"

    status_payload = _wait_for_job(payload["job_id"])
    assert status_payload["progress"] == 100
    assert status_payload["download_url"].endswith(f"/{payload['job_id']}/download")

    download_response = client.get(status_payload["download_url"])
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "font/ttf"
    assert "demo-125pct-bold-u5.ttf" in download_response.headers["content-disposition"]
    font = TTFont(BytesIO(download_response.content))
    assert font["hmtx"].metrics["A"][0] > 625


def test_async_conversion_status_survives_memory_cache_loss(sample_ttf_bytes):
    response = client.post(
        "/api/convert-jobs",
        data={
            "scale_percent": "100",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )
    job_id = response.json()["job_id"]
    status_payload = _wait_for_job(job_id)

    with jobs_lock:
        jobs.clear()

    recovered_response = client.get(f"/api/convert-jobs/{job_id}")

    assert recovered_response.status_code == 200
    assert recovered_response.json()["status"] == status_payload["status"]
    assert recovered_response.json()["download_url"].endswith(f"/{job_id}/download")


def test_job_payload_reports_queue_position():
    now = 1000.0
    running = ConversionJob(
        job_id="running",
        status="running",
        progress=10,
        message="running",
        download_name="running.ttf",
        output_path=Path("running.ttf"),
        created_at=now,
        updated_at=now,
    )
    queued = ConversionJob(
        job_id="queued",
        status="queued",
        progress=5,
        message="queued",
        download_name="queued.ttf",
        output_path=Path("queued.ttf"),
        created_at=now + 1,
        updated_at=now + 1,
    )
    with jobs_lock:
        jobs[running.job_id] = running
        jobs[queued.job_id] = queued

    payload = _job_payload(queued)

    assert payload["queue_position"] == 2
    assert payload["queued_ahead"] == 1


def test_recent_conversion_reports_source_and_duration(sample_ttf_bytes):
    response = client.post(
        "/api/convert-jobs",
        data={
            "scale_percent": "100",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
        headers={"x-forwarded-for": "8.8.4.4"},
    )

    status_payload = _wait_for_job(response.json()["job_id"])

    assert status_payload["recent_conversion"]["region"] == "IP 8.8.*.*"
    assert status_payload["recent_conversion"]["duration_seconds"] >= 0


def test_worker_crash_marks_job_failed_without_losing_status(sample_ttf_bytes, monkeypatch):
    def fail_worker(*_args, **_kwargs):
        raise RuntimeError("worker crashed")

    monkeypatch.setattr(main, "_run_worker_subprocess", fail_worker, raising=False)

    response = client.post(
        "/api/convert-jobs",
        data={
            "scale_percent": "100",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )
    job_id = response.json()["job_id"]

    for _ in range(50):
        status_response = client.get(f"/api/convert-jobs/{job_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        if payload["status"] == "failed":
            break
        sleep(0.05)
    else:
        raise AssertionError("conversion job did not fail")

    assert payload["error"] == "worker crashed"


def test_legacy_convert_worker_crash_returns_json_error(sample_ttf_bytes, monkeypatch):
    def fail_worker(*_args, **_kwargs):
        raise main.WorkerConversionError("worker crashed")

    monkeypatch.setattr(main, "_run_worker_subprocess", fail_worker)

    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "worker crashed"


def test_convert_endpoint_replaces_characters_from_source_font(build_ttf_bytes):
    source = build_ttf_bytes({"1": (10, 0, 210, 400), "A": (30, 0, 430, 700)})
    target = build_ttf_bytes({"1": (60, 0, 160, 200), "B": (70, 0, 370, 500)})

    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "replacement_scope": "digits",
            "custom_replacement_chars": "A",
        },
        files={
            "font_file": ("target.ttf", target, "font/ttf"),
            "source_font_file": ("source.ttf", source, "font/ttf"),
        },
    )

    assert response.status_code == 200
    assert "target-100pct-none-replace-digits.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    cmap = font.getBestCmap()
    glyph_one = font["glyf"][cmap[ord("1")]]
    glyph_one.recalcBounds(font["glyf"])
    glyph_a = font["glyf"][cmap[ord("A")]]
    glyph_a.recalcBounds(font["glyf"])
    glyph_b = font["glyf"][cmap[ord("B")]]
    glyph_b.recalcBounds(font["glyf"])

    assert (glyph_one.xMin, glyph_one.yMin, glyph_one.xMax, glyph_one.yMax) == (10, 0, 210, 400)
    assert (glyph_a.xMin, glyph_a.yMin, glyph_a.xMax, glyph_a.yMax) == (30, 0, 430, 700)
    assert (glyph_b.xMin, glyph_b.yMin, glyph_b.xMax, glyph_b.yMax) == (70, 0, 370, 500)


def test_convert_endpoint_applies_layout_spacing(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "spacing_left_percent": "2",
            "spacing_right_percent": "3",
            "spacing_top_percent": "4",
            "spacing_bottom_percent": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert "demo-100pct-none-space-l2-r3-t4-b5.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"] == (550, 70)
    assert font["hhea"].ascent == 840
    assert font["hhea"].descent == -250


def test_homepage_includes_spacing_controls_and_progress_bar():
    response = client.get("/")

    assert response.status_code == 200
    assert '/static/styles.css?v=' in response.text
    assert '/static/app.js?v=' in response.text
    assert 'id="changelog-dialog"' in response.text
    assert "2026-06-16 16:10 +08:00" in response.text
    assert "上传字体后立即预览当前字符效果" in response.text
    assert "修复进度条停在 95%" in response.text
    assert "2026-06-16 16:36 +08:00" in response.text
    assert "字重强度改为单一字体单位输入" in response.text
    assert "2026-06-16 17:10 +08:00" in response.text
    assert "加粗算法改为保留原轮廓并追加平移轮廓副本" in response.text
    assert "2026-06-16 18:05 +08:00" in response.text
    assert "转换接口改为先写入服务器临时 TTF 文件" in response.text
    assert "2026-06-16 19:09 +08:00" in response.text
    assert "转换流程改为后台任务模式" in response.text
    assert "2026-06-16 20:01 +08:00" in response.text
    assert "新增排队序号显示" in response.text
    assert "2026-06-16 20:43 +08:00" in response.text
    assert "字体转换改为独立子进程执行" in response.text
    assert "2026-06-16 22:02 +08:00" in response.text
    assert "大字体 Bold 自动切换低内存轮廓外扩模式" in response.text
    assert "选择要处理的字体 .ttf" in response.text
    assert "选择 B 目标字体" not in response.text
    assert "<span>水平效果" not in response.text
    assert "<span>垂直效果" not in response.text
    assert "可选：字符替换" in response.text
    assert "可选：选择 A 来源字体 .ttf" in response.text
    assert response.text.index("排版间距 (%)") < response.text.index("可选：字符替换")
    assert 'id="download-link"' in response.text
    assert 'id="clear-font-file"' in response.text
    assert 'id="clear-source-font-file"' in response.text
    assert 'id="effect-units"' in response.text
    assert 'id="spacing-left"' in response.text
    assert 'id="spacing-right"' in response.text
    assert 'id="spacing-top"' in response.text
    assert 'id="spacing-bottom"' in response.text
    assert 'id="progress-bar"' in response.text
    assert 'id="queue-info"' in response.text
    assert 'id="recent-conversion"' in response.text
    assert 'id="source-font-file"' in response.text
    assert 'id="replacement-scope"' in response.text
    assert 'id="custom-replacement-chars"' in response.text
    assert 'id="target-preview-output"' in response.text
    assert 'id="source-preview-output"' in response.text
    assert 'id="preview-output"' in response.text


def test_convert_endpoint_rejects_non_ttf(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "100", "weight_mode": "none"},
        files={"font_file": ("demo.otf", sample_ttf_bytes, "font/otf")},
    )

    assert response.status_code == 400
    assert "只支持 .ttf" in response.json()["detail"]


def test_convert_endpoint_rejects_invalid_scale(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "500", "weight_mode": "none"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "缩放比例" in response.json()["detail"]


def test_convert_endpoint_rejects_invalid_weight_mode(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "100", "weight_mode": "wide"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "字形效果" in response.json()["detail"]


def test_convert_endpoint_rejects_extreme_effect_value(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "thin",
            "effect_units": "501",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "效果数值" in response.json()["detail"]


def test_convert_endpoint_rejects_extreme_spacing_value(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "spacing_left_percent": "80",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "间距" in response.json()["detail"]
