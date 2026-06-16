from io import BytesIO

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont

from main import app


client = TestClient(app)


def test_convert_endpoint_returns_ttf_download(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "125",
            "weight_mode": "bold",
            "effect_x_percent": "5",
            "effect_y_percent": "0",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "font/ttf"
    assert "attachment" in response.headers["content-disposition"]
    assert "demo-125pct-bold-x5-y0.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"][0] > 500


def test_homepage_includes_manual_download_button():
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="download-link"' in response.text
    assert "下载转换后的字体" in response.text


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
            "effect_x_percent": "80",
            "effect_y_percent": "0",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "效果数值" in response.json()["detail"]
