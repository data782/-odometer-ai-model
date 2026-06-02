import asyncio

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.audit import write_log
from app.core.config import Settings
from app.api.schemas import VisionReadResponse
from app.services.vision import try_extract

PROCESSING_LIMIT = 5
PROCESSING_SEMAPHORE = asyncio.Semaphore(PROCESSING_LIMIT)

router = APIRouter()


@router.get("/")
def hello_world() -> dict[str, str]:
    return {"message": "Hello, World!"}


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def get_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/api/vision-read", response_model=None)
async def vision_read(
    mode: str = Form(...),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    x_api_key: str | None = Header(None),
    settings: Settings = Depends(get_runtime_settings),
) -> VisionReadResponse | JSONResponse:
    if not settings.odometer_auth_key or x_api_key != settings.odometer_auth_key:
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

    async def process_one(f: UploadFile):
        if not f.content_type or not f.content_type.startswith("image/"):
            return {"status": "fail", "filename": f.filename, "message": "Only image files allowed"}

        try:
            content = await f.read()
            async with PROCESSING_SEMAPHORE:
                result = await try_extract(content, mode, settings)
            if result.get("status") == "fail":
                await asyncio.to_thread(write_log, "fail", mode, None)
                if result.get("reason") == "parse_error":
                    return {
                        "status": "fail",
                        "filename": f.filename,
                        "message": result.get("message"),
                        "reason": result.get("reason"),
                    }
                return {"status": "fail", "filename": f.filename, "message": result.get("message")}

            val_key = "odometer" if mode == "odometer" else "tire_serial"
            await asyncio.to_thread(write_log, "success", mode, str(result.get(val_key)))
            return {"status": "success", "filename": f.filename, "result": result}
        except Exception as e:
            await asyncio.to_thread(write_log, "fail", mode, None)
            return {"status": "error", "filename": f.filename, "message": str(e)}

    results = await asyncio.gather(*(process_one(f) for f in all_files))
    return {"status": "success", "mode": mode, "results": results}
