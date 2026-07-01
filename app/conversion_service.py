"""
Logica di conversione eseguita in background (FastAPI BackgroundTasks).
Pipeline: download file sorgente -> Blender headless (import nativo +
export USD con materiali/texture/UV + export GLB, in un solo passaggio)
-> upload GLB su Supabase Storage -> aggiornamento stato/risultato su Supabase.
"""
import os
import tempfile

import requests

from app.mesh_to_usd import convert_mesh_to_usd_and_glb
from app.supabase_client import (
    upload_to_storage,
    update_model_status,
    update_model_result,
)


def process_conversion(file_url: str, fmt: str, model_id: str, user_id: str) -> None:
    input_path = usd_path = glb_path = None
    try:
        update_model_status(model_id, "processing")

        # 1. Scarica il file sorgente
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp_in:
            resp = requests.get(file_url, timeout=120)
            resp.raise_for_status()
            tmp_in.write(resp.content)
            input_path = tmp_in.name

        usd_path = input_path.replace(f".{fmt}", ".usdc")
        glb_path = input_path.replace(f".{fmt}", ".glb")

        # 2. Blender headless: import nativo + export USD (hub, con materiali/
        #    texture/UV) + export GLB, in un solo passaggio
        metadata = convert_mesh_to_usd_and_glb(input_path, usd_path, glb_path)

        # 3. Upload risultato su Supabase Storage
        with open(glb_path, "rb") as f:
            glb_bytes = f.read()
        file_size = len(glb_bytes)

        storage_path = f"{user_id}/converted/{model_id}.glb"
        public_url = upload_to_storage(
            storage_path, glb_bytes, content_type="model/gltf-binary"
        )

        # 4. Aggiorna il modello: status -> "ready" (impostato dentro update_model_result)
        update_model_result(
            model_id,
            file_url=public_url,
            file_path=storage_path,
            file_size=file_size,
            triangle_count=metadata["triangle_count"],
            auto_metadata=metadata,
        )

    except Exception as exc:
        update_model_status(model_id, "error", error_message=str(exc))
        raise
    finally:
        for p in (input_path, usd_path, glb_path):
            if p and os.path.exists(p):
                os.remove(p)
