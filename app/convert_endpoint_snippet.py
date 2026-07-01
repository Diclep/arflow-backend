"""
Snippet da integrare in main.py, in sostituzione della chiamata
a process_conversion.delay(...) (Celery).

Copiare le funzioni sotto dentro main.py, adattando gli import
in cima al file (mesh_to_usd, usd_export, supabase_client già esistenti).
"""
import os
import tempfile

import requests
from fastapi import BackgroundTasks

from app.mesh_to_usd import convert_mesh_to_usd
from app.usd_export import export_usd_to_glb
from app.supabase_client import (
    upload_to_storage,
    update_model_status,
    update_model_result,
)


def process_conversion_sync(file_url: str, fmt: str, model_id: str, user_id: str) -> None:
    input_path = usd_path = glb_path = None
    try:
        update_model_status(model_id, "processing")

        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp_in:
            resp = requests.get(file_url, timeout=60)
            resp.raise_for_status()
            tmp_in.write(resp.content)
            input_path = tmp_in.name

        usd_path = input_path.replace(f".{fmt}", ".usdc")
        glb_path = input_path.replace(f".{fmt}", ".glb")

        convert_mesh_to_usd(input_path, usd_path, asset_name=model_id)
        export_usd_to_glb(usd_path, glb_path)

        with open(glb_path, "rb") as f:
            glb_bytes = f.read()

        storage_path = f"{user_id}/converted/{model_id}.glb"
        public_url = upload_to_storage(
            storage_path, glb_bytes, content_type="model/gltf-binary"
        )

        update_model_result(model_id, public_url)
        update_model_status(model_id, "completed")

    except Exception:
        update_model_status(model_id, "failed")
        raise
    finally:
        for p in (input_path, usd_path, glb_path):
            if p and os.path.exists(p):
                os.remove(p)


# Nel router FastAPI esistente, sostituire il contenuto dell'endpoint /convert con:
#
# @app.post("/convert")
# async def convert_endpoint(
#     background_tasks: BackgroundTasks,
#     file_url: str,
#     fmt: str,
#     model_id: str,
#     user_id: str,
# ):
#     background_tasks.add_task(process_conversion_sync, file_url, fmt, model_id, user_id)
#     return {"status": "accepted", "model_id": model_id}
