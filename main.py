import os
import re
import io
import json
import asyncio
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from google import genai
from logger import write_log

# =========================
# APP INIT
# =========================

app = FastAPI(title="AI Vision Reader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================

def load_api_keys() -> List[str]:
    keys = []
    for i in range(1, 6):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key)
    return keys

def load_models() -> List[str]:
    models_env = os.getenv("GEMINI_MODELS", "")
    return [m.strip() for m in models_env.split(",") if m.strip()]

GEMINI_KEYS = load_api_keys()
GEMINI_MODELS = load_models()

# =========================
# AUTH
# =========================

def verify_api_key(x_api_key: str = Header(None)):
    expected_key = os.getenv("ODOMETER_API_KEY")
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

# =========================
# PROMPT BUILDER
# =========================

def build_prompt(mode: str) -> str:

    if mode == "odometer":
        return """
        Extract only the odometer numeric reading from this image.
        Return ONLY a JSON object with the following structure:
        {
            "odometer": "string of digits only",
            "confidence": float (0.0 to 1.0)
        }
        Rules:
        - The "odometer" value must NOT be alphanumeric; it must contain ONLY digits (0-9).
        - No units, no letters, no symbols, no explanation.
        - If unreadable, set "odometer" to null and "confidence" to 0.0.
        """

    elif mode == "tyre":
        return """
        Extract the tire serial number (DOT code) from this image.
        Return ONLY a JSON object with the following structure:
        {
            "tire_serial": "string",
            "confidence": float (0.0 to 1.0)
        }
        Rules:
        - The "tire_serial" should follow the DOT format (e.g., 'DOT' followed by 8-13 characters like 'DOT 1Y7 A1111 1215').
        - Keep letters and numbers as they appear in the DOT serial.
        - No explanation, no extra text.
        - If unreadable, set "tire_serial" to null and "confidence" to 0.0.
        """

    else:
        raise ValueError("Invalid mode")

# =========================
# UTILS
# =========================

def parse_json_response(text: str) -> Optional[dict]:
    try:
        # Try to find JSON block in case LLM wraps it in markdown
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except Exception:
        return None

# =========================
# LLM FALLBACK LOGIC
# =========================

async def try_extract(file_bytes: bytes, mode: str):

    if not GEMINI_KEYS:
        raise Exception("No Gemini API keys configured")

    if not GEMINI_MODELS:
        raise Exception("No Gemini models configured")

    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception as e:
        print(f"[ERROR] Invalid image: {e}")
        return {"status": "fail", "message": "Invalid image file"}

    prompt = build_prompt(mode)
    last_error = None

    for model in GEMINI_MODELS:
        for key in GEMINI_KEYS:
            try:
                print(f"[TRY] mode={mode} model={model} key_end={key[-4:]}")

                client = genai.Client(api_key=key)

                response = await client.aio.models.generate_content(
                    model=model,
                    contents=[prompt, image]
                )

                raw_text = response.text.strip()
                data = parse_json_response(raw_text)

                if not data:
                    print(f"[RETRY] Failed to parse JSON: {raw_text}")
                    continue

                # Check if it was "NOT_FOUND" logically (null in JSON)
                val_key = "odometer" if mode == "odometer" else "tire_serial"
                if data.get(val_key) is None:
                    return None

                return data

            except Exception as e:
                print(f"[FAIL] model={model} key_end={key[-4:]} error={str(e)}")
                last_error = e
                continue

    raise Exception(f"All attempts failed: {last_error}")

# =========================
# API ROUTE
# =========================
@app.post("/api/vision-read")
async def vision_read(
    mode: str = Form(...),
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    x_api_key: str = Header(None)
):

    verify_api_key(x_api_key)

    # Combine file and files into a single list
    all_files = []
    if file:
        all_files.append(file)
    if files:
        all_files.extend(files)

    if not all_files:
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail",
                "message": "No image files provided"
            }
        )

    # Validate mode early
    if mode not in ["odometer", "tyre"]:
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail",
                "message": "Invalid mode. Use 'odometer' or 'tyre'."
            }
        )

    # Process files
    async def process_one(f: UploadFile):
        if not f.content_type.startswith("image/"):
            return {"status": "fail", "filename": f.filename, "message": "Only image files allowed"}

        try:
            content = await f.read()
            result = await try_extract(content, mode)

            if not result:
                write_log("fail", mode, None)
                return {"status": "fail", "filename": f.filename, "message": "Value not detected"}

            # Log success (using the value from the result dict)
            val_key = "odometer" if mode == "odometer" else "tire_serial"
            write_log("success", mode, str(result.get(val_key)))

            return {
                "status": "success",
                "filename": f.filename,
                "result": result
            }
        except Exception as e:
            write_log("fail", mode, None)
            return {"status": "error", "filename": f.filename, "message": str(e)}

    # Handle multiple requests (files) at the same time
    results = await asyncio.gather(*(process_one(f) for f in all_files))

    return {
        "status": "success",
        "mode": mode,
        "results": results
    }