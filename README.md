# AI Vision Reader API

FastAPI service for extracting vehicle data from images using Google Gemini Vision.

Supported modes:
- `odometer`: extract odometer reading (digits)
- `tyre`: extract tyre serial number

## Why this service
- Simple authenticated HTTP API
- Multi-model + multi-key fallback for higher reliability
- Stateless and deployable on Render, Docker, or any ASGI host

## Quick Start

### 1. Install
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables
```env
# Required
GEMINI_API_KEY_1=your_primary_gemini_key
GEMINI_MODELS=gemini-3.1-flash-lite,gemini-2.5-flash
ODOMETER_API_KEY=replace_with_strong_random_secret

# Optional fallback keys
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
GEMINI_API_KEY_5=
```

### 3. Run locally
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docs:
- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY_1` | Yes | Primary Gemini API key |
| `GEMINI_API_KEY_2..5` | No | Additional keys for fallback when one key fails or is rate-limited |
| `GEMINI_MODELS` | Yes | Comma-separated Gemini model IDs in priority order |
| `ODOMETER_API_KEY` | Yes | Shared secret expected in `X-API-Key` request header |

Notes:
- Keep `GEMINI_MODELS` ordered from preferred to fallback.
- On Render, store values exactly (no quotes).
- Rotate all secrets regularly.

## API Contract

### `POST /api/vision-read`

Headers:
- `X-API-Key: <ODOMETER_API_KEY>`

Form fields:
- `mode`: `odometer` or `tyre`
- `file`: image file (`image/*`)

Example:
```bash
curl -X POST "http://localhost:8000/api/vision-read" \
  -H "X-API-Key: your_secret" \
  -F "mode=odometer" \
  -F "file=@/path/to/image.jpg"
```

Success (`200`):
```json
{
  "status": "success",
  "mode": "odometer",
  "result": "123456"
}
```

Common errors:

| Scenario | HTTP | Response |
|---|---|---|
| Invalid API key | `401` | `{"detail":"Unauthorized"}` |
| Invalid mode | `400` | `{"status":"fail","message":"Invalid mode. Use 'odometer' or 'tyre'."}` |
| Non-image upload | `400` | `{"status":"fail","message":"Only image files are allowed"}` |
| Value not detected | `400` | `{"status":"fail","mode":"...","message":"Value not detected"}` |
| All model/key attempts failed | `500` | `{"status":"error","mode":"...","message":"All LLM attempts failed"}` |

## How fallback works
For each incoming request:
1. Iterate models in `GEMINI_MODELS`
2. For each model, iterate keys `GEMINI_API_KEY_1..5`
3. Return first successful extraction
4. If all combinations fail, return `500`

## Deploy to Render

Service settings:
- Runtime: Python
- Build command:
```bash
pip install -r requirements.txt
```
- Start command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Required env vars in Render:
```env
GEMINI_API_KEY_1=your_primary_gemini_key
GEMINI_MODELS=gemini-2.5-flash,gemini-1.5-flash
ODOMETER_API_KEY=replace_with_strong_random_secret
```

Optional env vars:
```env
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
GEMINI_API_KEY_5=
```

Post-deploy checks:
1. Open `/docs`
2. Execute one real image request
3. Confirm logs show successful extraction

## Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t ai-vision-reader .
docker run -p 8000:8000 \
  -e GEMINI_API_KEY_1=your_key \
  -e GEMINI_MODELS=gemini-2.5-flash,gemini-1.5-flash \
  -e ODOMETER_API_KEY=your_secret \
  ai-vision-reader
```

## Production Hardening Checklist
- Replace wildcard CORS (`*`) with explicit frontend origins
- Keep `ODOMETER_API_KEY` secret and rotate periodically
- Add rate limiting at gateway/load balancer
- Enforce HTTPS only
- Centralize logs and monitoring alerts
- Add uptime/health checks

## Operations & Troubleshooting

`401 Unauthorized`
- Client missing/incorrect `X-API-Key`
- Server `ODOMETER_API_KEY` mismatch

`500 All LLM attempts failed`
- Invalid Gemini key or exhausted quota
- Invalid/unsupported model in `GEMINI_MODELS`
- Upstream Gemini transient issues

`400 Value not detected`
- Poor image quality (blur/glare)
- Incorrect crop/angle

Startup failures
- Missing dependencies from `requirements.txt`
- Wrong working directory or start command
