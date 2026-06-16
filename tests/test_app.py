from io import BytesIO

from fastapi import APIRouter
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from pytest import MonkeyPatch

from app.api import routes as vision_routes
from app.core.config import Settings
from app.core.observability import _parse_otlp_headers, _trace_endpoint
from app.main import create_app


def test_hello_world() -> None:
    client = TestClient(create_app(_test_settings()))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, World!"}
    assert len(response.headers["x-trace-id"]) == 32


def test_healthz() -> None:
    client = TestClient(create_app(_test_settings()))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_creation_without_observability_secrets() -> None:
    app = create_app(_test_settings())

    assert app.title == "test-service"


def test_traceparent_header_is_reused_for_response_trace_id() -> None:
    client = TestClient(create_app(_test_settings()))
    trace_id = "0af7651916cd43dd8448eb211c80319c"

    response = client.get("/", headers={"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"})

    assert response.headers["x-trace-id"] == trace_id


def test_unhandled_exceptions_include_request_trace_id() -> None:
    app = create_app(_test_settings())
    router = APIRouter()
    trace_id = "0af7651916cd43dd8448eb211c80319c"

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom", headers={"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"})

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["x-trace-id"] == trace_id


def test_grafana_otlp_base_endpoint_is_normalized_to_trace_endpoint() -> None:
    endpoint = "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp"

    assert _trace_endpoint(endpoint) == f"{endpoint}/v1/traces"


def test_trace_endpoint_is_not_double_appended() -> None:
    endpoint = "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp/v1/traces/"

    assert _trace_endpoint(endpoint) == endpoint.rstrip("/")


def test_otlp_headers_are_url_decoded() -> None:
    headers = _parse_otlp_headers("Authorization=Basic%20abc123")

    assert headers == {"Authorization": "Basic abc123"}


def test_vision_read_success(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(vision_routes, "try_extract", _fake_extract)
    monkeypatch.setattr(vision_routes, "write_log", lambda *_args, **_kwargs: None)
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/api/vision-read",
        headers={"x-api-key": "test-odometer-key"},
        data={"mode": "odometer"},
        files={"file": ("sample.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["result"]["odometer"] == "144969"


def test_vision_read_parse_error(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(vision_routes, "try_extract", _fake_parse_error)
    monkeypatch.setattr(vision_routes, "write_log", lambda *_args, **_kwargs: None)
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/api/vision-read",
        headers={"x-api-key": "test-odometer-key"},
        data={"mode": "odometer"},
        files={"file": ("sample.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["status"] == "fail"
    assert body["results"][0]["reason"] == "parse_error"


def test_vision_read_value_not_detected(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(vision_routes, "try_extract", _fake_not_detected)
    monkeypatch.setattr(vision_routes, "write_log", lambda *_args, **_kwargs: None)
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/api/vision-read",
        headers={"x-api-key": "test-odometer-key"},
        data={"mode": "odometer"},
        files={"file": ("sample.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["message"] == "Value not detected"


def test_vision_read_rejects_non_image(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(vision_routes, "write_log", lambda *_args, **_kwargs: None)
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/api/vision-read",
        headers={"x-api-key": "test-odometer-key"},
        data={"mode": "odometer"},
        files={"file": ("sample.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["message"] == "Only image files allowed"


def test_vision_read_unauthorized() -> None:
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/api/vision-read",
        headers={"x-api-key": "wrong-key"},
        data={"mode": "odometer"},
        files={"file": ("sample.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 401


async def _fake_extract(_file_bytes: bytes, _mode: str, _settings: Settings) -> dict[str, object]:
    return {"odometer": "144969", "confidence": 0.98}


async def _fake_parse_error(
    _file_bytes: bytes,
    _mode: str,
    _settings: Settings,
) -> dict[str, object]:
    return {
        "status": "fail",
        "reason": "parse_error",
        "message": "Model response was not valid JSON",
        "raw_text": "{bad json",
    }


async def _fake_not_detected(
    _file_bytes: bytes,
    _mode: str,
    _settings: Settings,
) -> dict[str, object]:
    return {
        "status": "fail",
        "reason": "value_not_detected",
        "message": "Value not detected",
    }


def _png_bytes() -> bytes:
    image = Image.new("RGB", (1, 1), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _test_settings() -> Settings:
    return Settings(
        APP_NAME="test-service",
        ENVIRONMENT="test",
        LOG_LEVEL="WARNING",
        ODOMETER_API_KEY=SecretStr("test-odometer-key"),
        GEMINI_API_KEY_1=SecretStr("test-gemini-key"),
        GEMINI_MODELS=SecretStr("gemini-2.5-flash"),
    )
