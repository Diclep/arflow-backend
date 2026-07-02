"""
ARFlow Backend — Microservizio di conversione modelli 3D
Pipeline: file (o gruppo di file: glTF+bin+texture, OBJ+mtl+texture, o uno ZIP)
-> OpenUSD (hub interno nascosto, via Blender headless) -> GLB
(STEP/STP/IGES restano fuori: Blender non li supporta nativamente)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from app.conversion_service import process_conversion
from app.chat_service import ask_gemini

app = FastAPI(
    title="ARFlow Conversion Backend",
    description="Microservizio per conversione modelli 3D verso OpenUSD e glTF/GLB",
    version="0.5.0",
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
    return {"service": "ARFlow Conversion Backend", "status": "online", "version": "0.5.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


class ConvertFile(BaseModel):
    name: str  # nome file originale (serve a Blender per risolvere i riferimenti relativi)
    url: str


class ConvertRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    files: List[ConvertFile]
    main_format: str  # estensione del file 3D principale, oppure "zip"
    model_id: str
    user_id: str
    callback_url: Optional[str] = None


class ConvertResponse(BaseModel):
    model_id: str
    status: str
    message: str


# Formati supportati nativamente da Blender headless, più "zip" come contenitore
# (verrà estratto e il file 3D principale individuato al suo interno).
SUPPORTED_FORMATS = ["glb", "gltf", "obj", "stl", "ply", "fbx", "abc", "zip"]


@app.post("/convert", response_model=ConvertResponse)
def convert_file(req: ConvertRequest, background_tasks: BackgroundTasks):
    """
    Avvia la conversione in background. Accetta uno o più file (es. .gltf + .bin +
    texture, o .obj + .mtl + texture) oppure un singolo file .zip che li contiene.
    Tutti i file vengono scaricati nella stessa cartella di lavoro, cosi Blender
    può risolvere automaticamente i riferimenti tra loro (stesso comportamento
    che avrebbe aprendo quei file manualmente in Blender dalla stessa cartella).
    """
    fmt = req.main_format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato '{fmt}' non ancora supportato. "
                f"Supportati ora: {SUPPORTED_FORMATS}."
            ),
        )
    if not req.files:
        raise HTTPException(status_code=400, detail="Nessun file fornito.")

    background_tasks.add_task(
        process_conversion,
        [{"name": f.name, "url": f.url} for f in req.files],
        fmt,
        req.model_id,
        req.user_id,
    )

    return ConvertResponse(
        model_id=req.model_id,
        status="processing",
        message=f"Conversione avviata ({len(req.files)} file, formato principale {fmt.upper()})",
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
