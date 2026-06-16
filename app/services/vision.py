import asyncio
import io
import json
import logging
import re
from functools import lru_cache
from typing import Any, TypedDict, cast

import numpy as np
from scipy.ndimage import convolve

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ParseErrorResult(TypedDict):
    status: str
    reason: str
    message: str
    raw_text: str


class ValueNotDetectedResult(TypedDict):
    status: str
    reason: str
    message: str


class VisionDataResult(TypedDict, total=False):
    status: str
    odometer: str | None
    tire_serial: str | None
    confidence: float
    reason: str
    message: str
    raw_text: str


def check_image_quality(image: Any) -> str | None:
    gray = image.convert("L")
    pixels = np.array(gray, dtype=float)

    laplacian_kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
    blur_score = convolve(pixels, laplacian_kernel).var()
    if blur_score < 100:
        return "blurry"

    if pixels.mean() < 40:
        return "too_dark"

    return None


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
        - If the image does not show an odometer, return {"odometer": null, "confidence": 0.0}.
        - If the image is blurry, dark, obscured, or unreadable, return {"odometer": null, "confidence": 0.0}.
        - NEVER guess or estimate a number. Only return digits you can clearly read.
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
        - If the image does not show a tyre or DOT code, return {"tire_serial": null, "confidence": 0.0}.
        - If the image is blurry, dark, obscured, or unreadable, return {"tire_serial": null, "confidence": 0.0}.
        - NEVER guess. Only return characters you can clearly read.
        """
    raise ValueError("Invalid mode")


def parse_json_response(text: str) -> VisionDataResult | ParseErrorResult:
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return cast(VisionDataResult, json.loads(match.group()))
        return cast(VisionDataResult, json.loads(text))
    except json.JSONDecodeError:
        logger.exception("Failed to parse JSON from model response")
        return {
            "status": "fail",
            "reason": "parse_error",
            "message": "Model response was not valid JSON",
            "raw_text": text,
        }
    except Exception:
        logger.exception("Unexpected parse error while decoding model response")
        return {
            "status": "fail",
            "reason": "parse_error",
            "message": "Unexpected error while parsing model response",
            "raw_text": text,
        }


@lru_cache(maxsize=16)
def get_client(api_key: str) -> Any:
    from importlib import import_module

    genai = import_module("google.genai")
    return genai.Client(api_key=api_key)


async def try_extract(
    file_bytes: bytes,
    mode: str,
    settings: Settings,
) -> VisionDataResult | ParseErrorResult | ValueNotDetectedResult:
    if not settings.gemini_keys:
        raise Exception("No Gemini API keys configured")
    if not settings.gemini_model_list:
        raise Exception("No Gemini models configured")

    try:
        from PIL import Image

        image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
    except Exception:
        return {"status": "fail", "message": "Invalid image file"}

    quality_issue = await asyncio.to_thread(check_image_quality, image)
    if quality_issue:
        return {
            "status": "fail",
            "reason": quality_issue,
            "message": f"Image rejected: {quality_issue}",
        }

    prompt = build_prompt(mode)
    last_error: Exception | None = None

    for model in settings.gemini_model_list:
        for key in settings.gemini_keys:
            try:
                client = get_client(key)
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=[prompt, image],
                    ),
                    timeout=30.0,
                )
                raw_text = response.text.strip()
                data = parse_json_response(raw_text)

                if data.get("status") == "fail" and data.get("reason") == "parse_error":
                    last_error = Exception(data.get("message"))
                    continue

                confidence = data.get("confidence", 0.0)
                if isinstance(confidence, float) and confidence < 0.6:
                    return {
                        "status": "fail",
                        "reason": "low_confidence",
                        "message": f"Model confidence too low: {confidence}",
                    }

                val_key = "odometer" if mode == "odometer" else "tire_serial"
                if data.get(val_key) is None:
                    return {
                        "status": "fail",
                        "reason": "value_not_detected",
                        "message": "Value not detected",
                    }
                return data
            except Exception as e:
                last_error = e
                continue

    raise Exception(f"All attempts failed: {last_error}")
