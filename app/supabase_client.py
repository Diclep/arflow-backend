"""
Wrapper minimale per le operazioni Supabase necessarie al backend di conversione.
Usa la SECRET key (sb_secret_..., non la publishable/anon) perché il backend
deve poter scrivere su qualsiasi riga indipendentemente dalle policy RLS.

Nota tecnica: con le nuove API key (sb_publishable_/sb_secret_), la chiave va
inviata SOLO nell'header `apikey`. Inviarla anche in `Authorization: Bearer`
(come richiedevano le vecchie service_role key basate su JWT) causa un
rifiuto della richiesta, perché il valore non è un JWT.
"""
import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("⚠ ATTENZIONE: SUPABASE_URL o SUPABASE_SERVICE_KEY non configurate. "
          "Imposta queste variabili d'ambiente su Railway prima di processare conversioni reali.")


def _headers(prefer_return=False):
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }
    if prefer_return:
        h["Prefer"] = "return=representation"
    return h


def upload_to_storage(path: str, file_bytes: bytes, content_type: str, bucket: str = "models") -> str:
    """Carica un file su Supabase Storage e restituisce l'URL pubblico."""
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
    }
    resp = requests.post(url, headers=headers, data=file_bytes, timeout=120)
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"


def update_model_status(model_id: str, status: str, error_message: str = None):
    """Aggiorna solo lo stato del modello (es. 'processing', 'error')."""
    url = f"{SUPABASE_URL}/rest/v1/models?id=eq.{model_id}"
    payload = {"status": status}
    if error_message:
        payload["conversion_error"] = error_message
    resp = requests.patch(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def update_model_result(model_id: str, file_url: str, file_path: str, file_size: int,
                         triangle_count: int, auto_metadata: dict):
    """Aggiorna il modello con il risultato della conversione completata."""
    url = f"{SUPABASE_URL}/rest/v1/models?id=eq.{model_id}"
    payload = {
        "status": "ready",
        "file_url": file_url,
        "file_path": file_path,
        "file_size": file_size,
        "format": "GLB",
        "triangle_count": triangle_count,
        "auto_metadata_json": auto_metadata,
    }
    resp = requests.patch(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
