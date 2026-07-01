"""
ARFlow Backend — Microservizio di conversione modelli 3D
Pipeline: GLB/glTF/OBJ/STL/PLY/FBX/ABC -> OpenUSD (hub interno nascosto,
via Blender headless) -> GLB
(STEP/STP e altri formati CAD nativi restano fuori: Blender non li supporta
nativamente, richiederebbero un add-on dedicato o OpenCASCADE — fase futura)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from app.conversion_service import process_conversion
from app.chat_service import ask_gemini

app = FastAPI(
    title="ARFlow Conversion Backend",
    description="Microservizio per conversione modelli 3D verso OpenUSD e glTF/GLB",
    version="0.4.0",
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
    return {"service": "ARFlow Conversion Backend", "status": "online", "version": "0.4.0"}


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
    model_id: str
    status: str
    message: str


# Formati supportati nativamente da Blender headless.
# STEP/STP/IGES restano fuori: Blender non li importa senza add-on dedicato.
SUPPORTED_FORMATS = ["glb", "gltf", "obj", "stl", "ply", "fbx", "abc"]


@app.post("/convert", response_model=ConvertResponse)
def convert_file(req: ConvertRequest, background_tasks: BackgroundTasks):
    """
    Avvia la conversione in background: file sorgente -> USD (hub interno,
    via Blender headless) -> GLB. Stato monitorabile su Supabase (colonna
    status: processing / ready / error).
    """
    fmt = req.format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato '{fmt}' non ancora supportato. "
                f"Supportati ora: {SUPPORTED_FORMATS}. "
                f"STEP/STP/IGES richiedono un add-on CAD dedicato, non ancora integrato."
            ),
        )

    background_tasks.add_task(
        process_conversion, req.file_url, fmt, req.model_id, req.user_id
    )

    return ConvertResponse(
        model_id=req.model_id,
        status="processing",
        message=f"Conversione {fmt.upper()} avviata in background",
    )


class ChatRequest(BaseModel):
    message: str
    history: list = []
    context: dict = {}


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Proxy verso Gemini: la chiave API resta lato server (env var GEMINI_API_KEY),
    non è mai esposta nel codice del frontend/demo.
    """
    try:
        reply = ask_gemini(req.message, req.history, req.context)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Errore chat AI: {e}")
    return ChatResponse(reply=reply)
