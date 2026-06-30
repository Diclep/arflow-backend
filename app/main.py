"""
ARFlow Backend — Microservizio di conversione CAD
Gestisce: STEP/STP → glTF, ZIP multi-file → glTF, USD/USDZ → glTF
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from app.tasks import process_conversion
from app.celery_app import celery_app

app = FastAPI(
    title="ARFlow Conversion Backend",
    description="Microservizio per conversione file CAD verso glTF/GLB",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.leodiclemente.it", "http://www.leodiclemente.it"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "ARFlow Conversion Backend", "status": "online", "version": "0.2.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


class ConvertRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    file_url: str
    format: str
    model_id: str
    user_id: str
    callback_url: Optional[str] = None


class ConvertResponse(BaseModel):
    job_id: str
    status: str
    message: str


@app.post("/convert", response_model=ConvertResponse)
def convert_file(req: ConvertRequest):
    """Accoda un job di conversione asincrono su Celery."""
    supported = ["step", "stp"]  # zip e usd arrivano negli step successivi
    fmt = req.format.lower()
    if fmt not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{fmt}' non ancora supportato dal backend. Supportati ora: {supported}"
        )

    task = process_conversion.delay(req.file_url, fmt, req.model_id, req.user_id)

    return ConvertResponse(
        job_id=task.id,
        status="queued",
        message=f"Job di conversione {fmt.upper()} accodato"
    )


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Polling dello stato di un job di conversione."""
    result = celery_app.AsyncResult(job_id)
    response = {"job_id": job_id, "status": result.state}

    if result.state == "PROCESSING":
        response["meta"] = result.info
    elif result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info)

    return response

