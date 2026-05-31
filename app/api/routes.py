import asyncio
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.vision import try_extract
from logger import write_log

router = APIRouter()


@router.get("/")
def hello_world() -> dict[str, str]:
    return {"message": "Hello, World!"}


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/vision-read")
async def vision_read(
    mode: str = Form(...),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    x_api_key: str | None = Header(None),
) -> dict[str, Any]:
    settings = get_settings()

    if x_api_key != settings.odometer_auth_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    all_files: list[UploadFile] = []
    if file:
        all_files.append(file)
    if files:
        all_files.extend(files)

    if not all_files:
        return JSONResponse(
            status_code=400,
            content={"status": "fail", "message": "No image files provided"},
        )

    if mode not in ["odometer", "tyre"]:
        return JSONResponse(
            status_code=400,
            content={"status": "fail", "message": "Invalid mode. Use 'odometer' or 'tyre'."},
        )

    async def process_one(f: UploadFile) -> dict[str, Any]:
        if not f.content_type or not f.content_type.startswith("image/"):
            return {"status": "fail", "filename": f.filename, "message": "Only image files allowed"}

        try:
            content = await f.read()
            result = await try_extract(content, mode, settings)
            if not result:
                write_log("fail", mode, None)
                return {"status": "fail", "filename": f.filename, "message": "Value not detected"}
            if isinstance(result, dict) and result.get("status") == "fail":
                write_log("fail", mode, None)
                return {"status": "fail", "filename": f.filename, "message": result.get("message")}

            val_key = "odometer" if mode == "odometer" else "tire_serial"
            write_log("success", mode, str(result.get(val_key)))
            return {"status": "success", "filename": f.filename, "result": result}
        except Exception as e:
            write_log("fail", mode, None)
            return {"status": "error", "filename": f.filename, "message": str(e)}

    results = await asyncio.gather(*(process_one(f) for f in all_files))
    return {"status": "success", "mode": mode, "results": results}
