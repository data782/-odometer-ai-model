import os
import re
import io
from typing import List
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

        Rules:
        - Return digits only
        - No explanation
        - No units
        - If unreadable return NOT_FOUND
        """

    elif mode == "tyre":
        return """
        Extract only the tyre serial number from this image.

        Rules:
        - Return the full serial exactly as visible
        - Keep letters and numbers
        - No explanation
        - No extra text
        - If unreadable return NOT_FOUND
        """

    else:
        raise ValueError("Invalid mode")

# =========================
# LLM FALLBACK LOGIC
# =========================

def try_extract(file_bytes: bytes, mode: str):

    if not GEMINI_KEYS:
        raise Exception("No Gemini API keys configured")

    if not GEMINI_MODELS:
        raise Exception("No Gemini models configured")

    image = Image.open(io.BytesIO(file_bytes))
    prompt = build_prompt(mode)

    last_error = None

    for model in GEMINI_MODELS:
        for key in GEMINI_KEYS:
            try:
                print(f"[TRY] mode={mode} model={model} key_end={key[-4:]}")

                client = genai.Client(api_key=key)

                response = client.models.generate_content(
                    model=model,
                    contents=[prompt, image]
                )

                raw_text = response.text.strip()

                if raw_text.upper() == "NOT_FOUND":
                    return None

                return raw_text.strip()

            except Exception as e:
                print(f"[FAIL] model={model} key_end={key[-4:]}")
                last_error = e
                continue

    raise Exception(f"All attempts failed: {last_error}")

# =========================
# API ROUTE
# =========================
@app.post("/api/vision-read")
async def vision_read(
    mode: str = Form(...),
    file: UploadFile = File(...),
    x_api_key: str = Header(None)
):

    verify_api_key(x_api_key)

    # Validate mode early
    if mode not in ["odometer", "tyre"]:
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail",
                "message": "Invalid mode. Use 'odometer' or 'tyre'."
            }
        )

    # Validate file type
    if not file.content_type.startswith("image/"):
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail",
                "message": "Only image files are allowed"
            }
        )

    try:
        file_bytes = await file.read()
        result = try_extract(file_bytes, mode)

        if not result:
            write_log("fail", mode, None)

            return JSONResponse(
                status_code=400,
                content={
                    "status": "fail",
                    "mode": mode,
                    "message": "Value not detected"
                }
            )

        write_log("success", mode, result)

        return {
            "status": "success",
            "mode": mode,
            "result": result
        }

    except Exception as e:
        write_log("fail", mode, None)
        print("FINAL ERROR:", str(e))

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "mode": mode,
                "message": "All LLM attempts failed"
            }
        )