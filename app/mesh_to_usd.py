"""
Converte GLB/OBJ/STL in USD (.usdc, con materiali/texture/UV) e GLB,
delegando l'import/export a Blender headless (bpy).
"""
import json
import os
import subprocess
import tempfile

BLENDER_SCRIPT = os.path.join(os.path.dirname(__file__), "blender_convert.py")
BLENDER_TIMEOUT_SECONDS = 300  # 5 minuti max per singola conversione

# Frammenti di testo che Blender stampa quando non trova/collega una texture.
# Non fanno fallire la conversione (il GLB viene comunque prodotto), ma
# vale la pena segnalarlo con un messaggio semplice invece del log grezzo.
TEXTURE_WARNING_MARKERS = [
    "could not copy texture",
    "has no size and cannot be exported",
]


def convert_mesh_to_usd_and_glb(input_path: str, usd_output_path: str, glb_output_path: str) -> dict:
    """
    Esegue Blender in modalità headless per:
      1. Importare il file sorgente (GLB/OBJ/STL/PLY/FBX/ABC)
      2. Esportare USD (.usdc) — hub interno nascosto, con materiali/texture/UV
      3. Esportare GLB dalla stessa scena — per il viewer web/AR

    Ritorna: {"triangle_count", "bounding_box", "hierarchy", ed eventuale "texture_warning"}
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as meta_file:
        meta_path = meta_file.name

    try:
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
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Conversione interrotta: superato il limite di {BLENDER_TIMEOUT_SECONDS}s. "
                "File troppo grande/complesso per i tempi attuali, o texture troppo pesanti."
            )

        if result.returncode != 0:
            if result.returncode < 0:
                raise RuntimeError(
                    f"Conversione terminata dal sistema (segnale {-result.returncode}). "
                    "Causa più probabile: memoria insufficiente sul servizio Railway. "
                    "Serve più RAM allocata al servizio, oppure meno texture/più leggere."
                )
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

        combined_output = (result.stdout or "") + (result.stderr or "")
        if any(marker in combined_output for marker in TEXTURE_WARNING_MARKERS):
            metadata["texture_warning"] = (
                "Controlla le texture: una o più potrebbero non essere state "
                "collegate correttamente (nome file diverso da quello referenziato "
                "nel modello)."
            )

        return metadata

    finally:
        if os.path.exists(meta_path):
            os.remove(meta_path)
