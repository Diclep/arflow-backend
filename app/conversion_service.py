"""
Logica di conversione eseguita in background (FastAPI BackgroundTasks).
Pipeline: scarica tutti i file forniti in un'unica cartella di lavoro (così
Blender può risolvere da solo i riferimenti relativi tra .gltf/.bin/texture o
.obj/.mtl/texture) -> se è stato caricato uno ZIP, lo estrae -> individua il
file 3D principale -> collima le texture trovate in altre sottocartelle
accanto al file principale -> Blender headless (import nativo + export USD
con materiali/texture/UV/animazioni + export GLB) -> upload GLB su Supabase
Storage -> aggiornamento stato/risultato su Supabase.

File caricati per errore e non referenziati dal modello (es. una texture che
non corrisponde a nessun materiale) vengono semplicemente ignorati da Blender
stesso durante l'import — non serve una verifica esplicita separata.
"""
import os
import shutil
import tempfile
import zipfile

import requests

from app.mesh_to_usd import convert_mesh_to_usd_and_glb
from app.supabase_client import (
    upload_to_storage,
    update_model_status,
    update_model_result,
)

# Estensioni che Blender headless sa importare come file 3D "principale".
RECOGNIZED_MAIN_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl", ".ply", ".fbx", ".abc"}
_PRIORITY = [".gltf", ".glb", ".obj", ".fbx", ".abc", ".ply", ".stl"]


def _download_files(files: list, work_dir: str) -> None:
    """Scarica ogni file preservando il nome originale, nella cartella condivisa."""
    for f in files:
        dest = os.path.join(work_dir, f["name"])
        resp = requests.get(f["url"], timeout=180)
        resp.raise_for_status()
        with open(dest, "wb") as out:
            out.write(resp.content)


def _extract_zip_if_present(work_dir: str) -> None:
    """Estrae eventuali .zip nella cartella (e rimuove l'archivio dopo).
    Preserva la struttura a sottocartelle originale (es. Source/, Textures/):
    la co-locazione delle texture avviene in un passo separato."""
    for name in list(os.listdir(work_dir)):
        if name.lower().endswith(".zip"):
            zpath = os.path.join(work_dir, name)
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(work_dir)
            os.remove(zpath)


def _find_main_file(work_dir: str):
    """Trova il file 3D principale in tutta la cartella, incluse le sottocartelle."""
    found_by_ext = {}
    for root, _dirs, filenames in os.walk(work_dir):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in RECOGNIZED_MAIN_EXTENSIONS and ext not in found_by_ext:
                found_by_ext[ext] = os.path.join(root, fname)
    for ext in _PRIORITY:
        if ext in found_by_ext:
            return found_by_ext[ext]
    return None


def _collocate_supporting_files(work_dir: str, main_file: str) -> None:
    """
    Copia ogni altro file trovato nell'archivio (texture, .bin, .mtl, ecc.)
    nella STESSA cartella del file 3D principale.

    Perché serve: molti export (es. Sketchfab) organizzano lo ZIP in
    sottocartelle separate (es. "Source/model.gltf" + "Textures/diffuse.png").
    Il file principale però referenzia le texture con percorsi relativi
    "semplici" (solo il nome file, es. "diffuse.png"), assumendo che siano
    nella sua stessa cartella. Senza questo passo, Blender non le troverebbe.

    Non sposta né elimina nulla dalla posizione originale: copia soltanto,
    quindi eventuali riferimenti relativi più complessi (es. "../Textures/x.png")
    continuano a funzionare comunque.
    """
    main_dir = os.path.dirname(main_file)
    main_name = os.path.basename(main_file)
    for root, _dirs, filenames in os.walk(work_dir):
        if os.path.abspath(root) == os.path.abspath(main_dir):
            continue
        for fname in filenames:
            if fname == main_name:
                continue
            src = os.path.join(root, fname)
            dst = os.path.join(main_dir, fname)
            if not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass  # file non copiabile (permessi, ecc.) — non blocca la conversione


def process_conversion(files: list, main_format: str, model_id: str, user_id: str) -> None:
    work_dir = tempfile.mkdtemp(prefix="arflow_job_")
    usd_path = glb_path = None
    try:
        update_model_status(model_id, "processing")

        _download_files(files, work_dir)

        if main_format.lower() == "zip":
            _extract_zip_if_present(work_dir)

        main_file = _find_main_file(work_dir)
        if not main_file:
            raise RuntimeError(
                "Nessun file 3D riconosciuto tra quelli caricati "
                f"(supportati: {sorted(RECOGNIZED_MAIN_EXTENSIONS)})."
            )

        _collocate_supporting_files(work_dir, main_file)

        usd_path = os.path.join(os.path.dirname(main_file), "_arflow_output.usdc")
        glb_path = os.path.join(os.path.dirname(main_file), "_arflow_output.glb")

        # Blender importa il file principale: eventuali .bin/texture/.mtl,
        # ora tutti co-locati nella stessa cartella, vengono risolti
        # automaticamente dai suoi importer nativi.
        metadata = convert_mesh_to_usd_and_glb(main_file, usd_path, glb_path)

        with open(glb_path, "rb") as f:
            glb_bytes = f.read()
        file_size = len(glb_bytes)

        storage_path = f"{user_id}/converted/{model_id}.glb"
        public_url = upload_to_storage(
            storage_path, glb_bytes, content_type="model/gltf-binary"
        )

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
        shutil.rmtree(work_dir, ignore_errors=True)
