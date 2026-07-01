"""
Esporta uno stage USD in GLB usando usd2gltf (CLI wrapper, pip puro,
nessuna compilazione nativa richiesta).
"""
import subprocess


def export_usd_to_glb(usd_path: str, glb_output_path: str) -> str:
    result = subprocess.run(
        ["usd2gltf", "-i", usd_path, "-o", glb_output_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"usd2gltf failed: {result.stderr}")
    return glb_output_path
