from pydantic import BaseModel


class VisionSuccessResult(BaseModel):
    status: str
    filename: str
    result: dict[str, object]


class VisionErrorResult(BaseModel):
    status: str
    filename: str
    message: str


class VisionReadResponse(BaseModel):
    status: str
    mode: str
    results: list[VisionSuccessResult | VisionErrorResult]
