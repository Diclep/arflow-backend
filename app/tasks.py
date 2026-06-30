"""
Task Celery principale — orchestratore della pipeline di conversione completa.
"""
import os
import tempfile
import requests
from celery import states
from celery.exceptions import Ignore

from app.celery_app import celery_app
from app.step_converter import convert_step_to_glb
from app.supabase_client import (
    upload_to_storage,
    update_model_status,
    update_model_result,
)


@celery_app.task(bind=True, name="process_conversion")
def process_conversion(self, file_url: str, fmt: str, model_id: str, user_id: str):
    """
    Task principale: scarica il file, lo converte, carica il risultato,
    aggiorna lo stato nel database ARFlow (tabella `models` su Supabase).
    """
    fmt = fmt.lower()

    try:
        self.update_state(state="PROCESSING", meta={"step": "download"})
        update_model_status(model_id, "processing")

        # ── 1. Scarica il file sorgente ─────────────────────────────────────
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp_in:
            resp = requests.get(file_url, timeout=120)
            resp.raise_for_status()
            tmp_in.write(resp.content)
            input_path = tmp_in.name

        output_path = input_path.replace(f".{fmt}", ".glb")

        # ── 2. Conversione (router per formato) ─────────────────────────────
        self.update_state(state="PROCESSING", meta={"step": "convert"})

        if fmt in ("step", "stp"):
            result_meta = convert_step_to_glb(input_path, output_path)
        else:
            raise ValueError(f"Formato '{fmt}' non gestito da questo task (solo STEP/STP per ora)")

        # ── 3. Upload risultato su Supabase Storage ──────────────────────────
        self.update_state(state="PROCESSING", meta={"step": "upload"})
        storage_path = f"{user_id}/converted/{model_id}.glb"

        with open(output_path, "rb") as f:
            glb_bytes = f.read()

        public_url = upload_to_storage(storage_path, glb_bytes, content_type="model/gltf-binary")

        # ── 4. Aggiorna il database ARFlow ───────────────────────────────────
        update_model_result(
            model_id=model_id,
            file_url=public_url,
            file_path=storage_path,
            file_size=len(glb_bytes),
            triangle_count=result_meta["triangle_count"],
            auto_metadata={
                "format": fmt.upper(),
                "geometry": {
                    "triangleCount": result_meta["triangle_count"],
                    "meshCount": result_meta["component_count"],
                    "meshNames": result_meta["component_names"],
                },
                "extraction_method": result_meta["extraction_method"],
                "conversion_errors": result_meta.get("errors"),
                "notes": f"Convertito da {fmt.upper()} via backend pythonOCC-core. "
                         f"{result_meta['component_count']} componenti, "
                         f"{result_meta['triangle_count']} triangoli totali.",
            },
        )

        # ── 5. Pulizia file temporanei ────────────────────────────────────────
        os.unlink(input_path)
        os.unlink(output_path)

        return {"status": "ready", "model_id": model_id, "triangle_count": result_meta["triangle_count"]}

    except Exception as e:
        update_model_status(model_id, "error", error_message=str(e))
        self.update_state(state=states.FAILURE, meta={"error": str(e)})
        raise Ignore()
