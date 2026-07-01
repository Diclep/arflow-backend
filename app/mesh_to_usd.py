"""
Converte GLB/OBJ/STL in USD (.usdc, con materiali/texture/UV) e GLB,
delegando l'import/export a Blender headless (bpy). Blender ha importer/
exporter nativi molto più maturi e completi di un writer USD scritto a mano:
materiali, texture, UV e gerarchia vengono preservati correttamente.
"""
import json
import os
import subprocess
import tempfile

BLENDER_SCRIPT = os.path.join(os.path.dirname(__file__), "blender_convert.py")
BLENDER_TIMEOUT_SECONDS = 300  # 5 minuti max per singola conversione


def convert_mesh_to_usd_and_glb(input_path: str, usd_output_path: str, glb_output_path: str) -> dict:
    """
    Esegue Blender in modalità headless per:
      1. Importare il file sorgente (GLB/OBJ/STL)
      2. Esportare USD (.usdc) — hub interno nascosto, con materiali/texture/UV
      3. Esportare GLB dalla stessa scena — per il viewer web/AR

    Ritorna: {"triangle_count": int, "bounding_box": {...}, "hierarchy": [...]}
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as meta_file:
        meta_path = meta_file.name

    try:
        result = subprocess.run(
            [
                "blender", "--background", "--factory-startup",
                "--python", BLENDER_SCRIPT,
                "--", input_path, usd_output_path, glb_output_path, meta_path,
            ],
            capture_output=True,
            text=True,
            timeout=BLENDER_TIMEOUT_SECONDS,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Conversione Blender fallita (exit {result.returncode}): "
                f"{result.stderr[-2000:] or result.stdout[-2000:]}"
            )

        if not os.path.exists(meta_path) or os.path.getsize(meta_path) == 0:
            raise RuntimeError(
                f"Blender non ha prodotto i metadata. Output: {result.stdout[-2000:]}"
            )

        with open(meta_path) as f:
            metadata = json.load(f)

        return metadata

    finally:
        if os.path.exists(meta_path):
            os.remove(meta_path)
