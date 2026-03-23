# AI Vision Reader API

A FastAPI microservice that uses Google Gemini to extract data from images. Supports odometer reading (numeric value) and tyre serial number extraction.

---

## Requirements

- Python 3.9+
- Google Gemini API key(s)
- A secret key for API authentication

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd POC-VM_2
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file or export the following variables in your shell:

```env
GEMINI_API_KEY_1=your_gemini_api_key_here
GEMINI_API_KEY_2=optional_second_key
GEMINI_MODELS=gemini-2.5-flash,gemini-1.5-flash
ODOMETER_API_KEY=your_secret_auth_key
```

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY_1` | Yes | Primary Google Gemini API key |
| `GEMINI_API_KEY_2..5` | No | Additional keys for fallback |
| `GEMINI_MODELS` | Yes | Comma-separated list of Gemini models to try in order |
| `ODOMETER_API_KEY` | Yes | Secret key used to authenticate API requests |

> **Getting a Gemini API key**: Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and generate a key.

---

## Running the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

For development with auto-reload:

```bash
uvicorn main:app --reload
```

---

## API Reference

### `POST /api/vision-read`

Extracts a value from an uploaded image.

**Headers**

| Header | Value |
|---|---|
| `X-API-Key` | Your `ODOMETER_API_KEY` value |

**Form Fields**

| Field | Type | Values |
|---|---|---|
| `mode` | string | `odometer` or `tyre` |
| `file` | file | Image file (jpg, png, etc.) |

**Example — curl**

```bash
curl -X POST "http://localhost:8000/api/vision-read" \
  -H "X-API-Key: your_secret_auth_key" \
  -F "mode=odometer" \
  -F "file=@/path/to/image.jpg"
```

**Example — Python**

```python
import requests

url = "http://localhost:8000/api/vision-read"
headers = {"X-API-Key": "your_secret_auth_key"}

with open("image.jpg", "rb") as f:
    response = requests.post(url, headers=headers, data={"mode": "odometer"}, files={"file": f})

print(response.json())
```

**Success Response**

```json
{
  "status": "success",
  "mode": "odometer",
  "result": "123456"
}
```

**Failure Responses**

| Scenario | HTTP Status | Response |
|---|---|---|
| Invalid API key | 401 | `{"detail": "Unauthorized"}` |
| Invalid mode | 400 | `{"status": "fail", "message": "Invalid mode. Use 'odometer' or 'tyre'."}` |
| Non-image file | 400 | `{"status": "fail", "message": "Only image files are allowed"}` |
| Value not found in image | 400 | `{"status": "fail", "mode": "...", "message": "Value not detected"}` |
| All Gemini attempts failed | 500 | `{"status": "error", "mode": "...", "message": "All LLM attempts failed"}` |

---

## How It Works

The service uses a **multi-key, multi-model fallback** strategy for resilience:

1. For each configured Gemini model (in `GEMINI_MODELS` order)
2. For each configured API key (`GEMINI_API_KEY_1..5`)
3. Try to extract the value using Gemini vision

If a key is rate-limited or a model fails, the next combination is tried automatically. All requests are logged to `logs.txt`.

---

## Deployment Notes

- Set `ODOMETER_API_KEY` to a strong random secret before deploying.
- Configure `GEMINI_MODELS` with at least two models for fallback reliability (e.g. `gemini-2.5-flash,gemini-1.5-flash`).
- CORS is currently open to all origins (`*`). Restrict `allow_origins` in `main.py` for production.
- The service is stateless — it can be deployed behind a load balancer or as a container without additional configuration.

### Docker (optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t vision-reader .
docker run -p 8000:8000 \
  -e GEMINI_API_KEY_1=your_key \
  -e GEMINI_MODELS=gemini-2.5-flash \
  -e ODOMETER_API_KEY=your_secret \
  vision-reader
```
