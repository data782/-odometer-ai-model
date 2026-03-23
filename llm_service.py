import re
import os
from PIL import Image
from google import genai
import io

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def extract_odometer_llm(file_bytes: bytes):

    try:
        image = Image.open(io.BytesIO(file_bytes))

        prompt = """
        Extract only the odometer numeric reading from this image.

        Rules:
        - Return digits only
        - No explanation
        - No units
        - If unreadable return NOT_FOUND
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, image]
        )

        raw_text = response.text.strip()
        digits = re.findall(r"\d+", raw_text)

        return "".join(digits) if digits else None

    except Exception as e:
        print("LLM Error:", e)
        return None