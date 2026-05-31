import io
import json
import re
from typing import Any

from app.core.config import Settings


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
        - The "odometer" value must contain only digits (0-9).
        - No units, no letters, no symbols, no explanation.
        - If unreadable, set "odometer" to null and "confidence" to 0.0.
        """
    if mode == "tyre":
        return """
        Extract the tire serial number (DOT code) from this image.
        Return ONLY a JSON object with the following structure:
        {
            "tire_serial": "string",
            "confidence": float (0.0 to 1.0)
        }
        Rules:
        - Keep letters and numbers as they appear.
        - No explanation, no extra text.
        - If unreadable, set "tire_serial" to null and "confidence" to 0.0.
        """
    raise ValueError("Invalid mode")


def parse_json_response(text: str) -> dict[str, Any] | None:
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except Exception:
        return None


async def try_extract(file_bytes: bytes, mode: str, settings: Settings) -> dict[str, Any] | None:
    if not settings.gemini_keys:
        raise Exception("No Gemini API keys configured")
    if not settings.gemini_model_list:
        raise Exception("No Gemini models configured")

    from PIL import Image
    from google import genai

    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception:
        return {"status": "fail", "message": "Invalid image file"}

    prompt = build_prompt(mode)
    last_error: Exception | None = None

    for model in settings.gemini_model_list:
        for key in settings.gemini_keys:
            try:
                client = genai.Client(api_key=key)
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=[prompt, image],
                )
                raw_text = response.text.strip()
                data = parse_json_response(raw_text)
                if not data:
                    continue
                val_key = "odometer" if mode == "odometer" else "tire_serial"
                if data.get(val_key) is None:
                    return None
                return data
            except Exception as e:
                last_error = e
                continue

    raise Exception(f"All attempts failed: {last_error}")
