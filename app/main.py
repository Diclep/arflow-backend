"""
ARFlow Backend — Microservizio di conversione CAD
Gestisce: STEP/STP → glTF, ZIP multi-file → glTF, USD/USDZ → glTF
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI(
    title="ARFlow Conversion Backend",
    description="Microservizio per conversione file CAD verso glTF/GLB",
    version="0.1.0",
)

# CORS — permette chiamate dalla dashboard ARFlow
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.leodiclemente.it", "http://www.leodiclemente.it"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── HEALTH CHECK ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"service": "ARFlow Conversion Backend", "status": "online", "version": "0.1.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ── MODELLI RICHIESTA/RISPOSTA ───────────────────────────────────────────────
class ConvertRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    file_url: str          # URL pubblico del file su Supabase Storage
    format: str             # step, stp, zip, usd, usdz
    model_id: str           # UUID del modello nel database ARFlow
    user_id: str            # UUID dell'utente proprietario
    callback_url: Optional[str] = None  # opzionale, per notifiche


class ConvertResponse(BaseModel):
    job_id: str
    status: str              # queued, processing, ready, error
    message: str


# ── ENDPOINT CONVERSIONE (placeholder — implementato nello step successivo) ──
@app.post("/convert", response_model=ConvertResponse)
def convert_file(req: ConvertRequest):
    """
    Riceve un file da convertire, lo accoda per il processing asincrono.
    Per ora risponde subito senza processare — la logica reale arriva
    quando aggiungiamo Celery + Redis nello step successivo.
    """
    supported = ["step", "stp", "zip", "usd", "usdz"]
    fmt = req.format.lower()
    if fmt not in supported:
        raise HTTPException(status_code=400, detail=f"Formato '{fmt}' non supportato. Supportati: {supported}")

    # TODO step successivo: pubblica job su coda Celery
    # job = process_conversion.delay(req.file_url, fmt, req.model_id, req.user_id)

    return ConvertResponse(
        job_id="placeholder-job-id",
        status="queued",
        message=f"Job di conversione {fmt.upper()} accodato (placeholder — worker non ancora attivo)"
    )


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Polling dello stato di un job di conversione."""
    # TODO: query reale su Celery result backend (Redis)
    return {"job_id": job_id, "status": "unknown", "message": "Worker non ancora implementato"}
