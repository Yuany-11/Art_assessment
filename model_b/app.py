"""模型B服务：美术四维评分 + 学情报告。

加载到训练权重时返回 status=success / fallbackUsed=false；
权重或 torch 不可用时回落到启发式基线，返回 degraded / true 并标明版本。
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import swagger_ui_bundle
    SWAGGER_DIR = os.path.join(os.path.dirname(swagger_ui_bundle.__file__), "vendor", "swagger-ui-4.15.5")
except ImportError:
    SWAGGER_DIR = None

import model_runtime
import report as report_rules
import scoring

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "dev-token")
MODEL_TIMEOUT_S = 60
STARTED_AT = datetime.now().isoformat(timespec="seconds")

app = FastAPI(title="Art Assessment Model B", version=scoring.MODEL_VERSION, docs_url=None, redoc_url=None)
app.mount("/samples", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "samples")), name="samples")
if SWAGGER_DIR:
    app.mount("/static/swagger", StaticFiles(directory=SWAGGER_DIR), name="swagger-static")
    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
        name="local-static",
    )


_base_openapi = app.openapi


def _swagger_compatible_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = _base_openapi()
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return schema


app.openapi = _swagger_compatible_openapi


@app.get("/docs", include_in_schema=False)
def docs():
    if SWAGGER_DIR:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title="Art Assessment Model B - API",
            swagger_js_url="/static/swagger/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui.css",
        )
    return JSONResponse({"detail": "swagger assets not installed"}, status_code=500)


def _envelope(code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(status_code=code, content={"code": code, "message": message, "data": data})


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return _envelope(exc.status_code, str(exc.detail), None)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return _envelope(400, "请求参数校验失败", None)


@app.exception_handler(scoring.ScoringError)
async def scoring_error(request: Request, exc: scoring.ScoringError):
    return _envelope(exc.status_code, exc.message, None)


def verify_token(x_internal_token: Optional[str] = Header(default=None)) -> None:
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="内部令牌缺失或错误")


class Rubric(BaseModel):
    composition: float
    color: float
    modeling: float
    creativity: float


class ArtScoreRequest(BaseModel):
    imageUrl: str = Field(min_length=1)
    workType: str = "painting"
    studentId: int
    assessmentId: Optional[int] = None
    questionId: Optional[int] = None
    rubric: Optional[Rubric] = None
    requestId: Optional[str] = None


class LearningReportRequest(BaseModel):
    studentId: int
    subject: str = "art"
    records: List[Dict] = []
    timeRange: Optional[Dict] = None
    focus: Optional[str] = None
    language: str = "zh"


@app.on_event("startup")
def _warmup_model():
    model_runtime.preload()


@app.get("/health")
def health():
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "ok",
            "modelVersion": model_runtime.loaded_version() or scoring.MODEL_VERSION,
            "mode": "model" if model_runtime.loaded_version() else "baseline",
            "startedAt": STARTED_AT,
            "uptimeSeconds": int((datetime.now() - datetime.fromisoformat(STARTED_AT)).total_seconds()),
        },
    }


def _predict_with_model(img):
    started = time.perf_counter()
    try:
        pred = model_runtime.predict(img)
    except model_runtime.ModelUnavailable:
        return None
    if time.perf_counter() - started > MODEL_TIMEOUT_S:
        raise scoring.ScoringError(500, "模型推理超时（超过60秒），本次不返回分数")
    return pred


def _model_scores(pred, rubric):
    scores = dict(pred["scores"])
    total = round(sum(scores[d] * rubric[d] for d in scoring.DIMENSIONS) / 100.0, 2)
    scores["total"] = total
    level = scoring.level_of(total)
    return {
        "scores": scores,
        "level": level,
        **scoring.describe_scores(scores, level),
        "contentFlags": pred["flags"],
        "warnings": [],
    }


@app.post("/api/v1/ai/art/score", dependencies=[Depends(verify_token)])
def art_score(req: ArtScoreRequest):
    started = time.perf_counter()
    rubric = scoring.validate_rubric(req.rubric.model_dump() if req.rubric else None)
    img = scoring.fetch_image(req.imageUrl)

    pred = _predict_with_model(img)
    if pred is None:
        result = scoring.score_image(img, rubric)
        status, fallback_used, version = "degraded", True, scoring.MODEL_VERSION
    else:
        result = _model_scores(pred, rubric)
        status, fallback_used, version = "success", False, pred["modelVersion"]
        if "low_res" in result["contentFlags"]:
            result["warnings"].append(f"图片分辨率偏低（短边 {min(img.size)}px），分数参考性下降")

    if any(f in result["contentFlags"] for f in ("document", "screenshot", "blank")):
        raise scoring.ScoringError(422, "未检测到绘画内容（文字/截图/空白），无法给出评分")

    request_id = req.requestId or f"ai-art-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8]}"
    data = {
        "requestId": request_id,
        "status": status,
        "workType": req.workType,
        "scores": result["scores"],
        "level": result["level"],
        "dimensionComments": result["dimensionComments"],
        "strengths": result["strengths"],
        "improvements": result["improvements"],
        "summary": result["summary"],
        "warnings": result["warnings"],
        "contentFlags": result["contentFlags"],
        "fallbackUsed": fallback_used,
        "modelVersion": version,
        "costMs": int((time.perf_counter() - started) * 1000),
    }
    return {"code": 200, "message": "success", "data": data}


@app.post("/api/v1/ai/learning-report", dependencies=[Depends(verify_token)])
def learning_report(req: LearningReportRequest):
    started = time.perf_counter()
    data = report_rules.build_report(
        student_id=req.studentId,
        subject=req.subject,
        records=req.records,
        time_range=req.timeRange,
        focus=req.focus,
        language=req.language,
    )
    data["costMs"] = int((time.perf_counter() - started) * 1000)
    return {"code": 200, "message": "success", "data": data}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
