"""
Script eseguito DENTRO Blender in modalità headless (bpy), non da FastAPI
direttamente. Uso:

  blender --background --factory-startup --python blender_convert.py -- \
      <input> <usd_output> <glb_output> <meta_output>

Importa il file sorgente (GLB/OBJ/STL) usando gli importer nativi di Blender
(molto più completi e testati di un parser scritto a mano), poi esporta:
  - USD (.usdc): hub interno nascosto, con materiali/texture/UV/gerarchia
  - GLB: per il viewer web/AR
  - JSON metadata: triangle_count, bounding_box, hierarchy

Nota sui parametri Blender: per gli operatori import/export usiamo solo i
parametri di cui siamo certi (nomi confermati nella documentazione ufficiale
per questa versione). Per tutto il resto lasciamo i default di Blender, che
per USD includono già materiali/texture/UV/normali attivi. Se un log mostra
un errore "unexpected keyword argument", è lì che va aggiornato un nome di
parametro cambiato in una versione diversa di Blender.
"""
import sys
import os
import json

import bpy
from mathutils import Vector


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]
    input_path, usd_out, glb_out, meta_out = argv[:4]

    # Scena vuota, senza il cubo/luce/camera di default
    bpy.ops.wm.read_factory_settings(use_empty=True)

    ext = os.path.splitext(input_path)[1].lower()

    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=input_path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=input_path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=input_path)
    else:
        raise ValueError(f"Formato non supportato da questo script: {ext}")

    # ── Metadata: triangle count, bounding box, gerarchia ──────────────────
    mesh_objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]

    triangle_count = 0
    hierarchy = []
    min_co = [float("inf")] * 3
    max_co = [float("-inf")] * 3

    for obj in mesh_objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        triangle_count += len(mesh.loop_triangles)
        hierarchy.append(obj.name)

        for corner in obj.bound_box:
            world_co = obj.matrix_world @ Vector(corner)
            for i in range(3):
                min_co[i] = min(min_co[i], world_co[i])
                max_co[i] = max(max_co[i], world_co[i])

    metadata = {
        "triangle_count": triangle_count,
        "bounding_box": {"min": min_co, "max": max_co} if mesh_objects else None,
        "hierarchy": hierarchy,
    }
    with open(meta_out, "w") as f:
        json.dump(metadata, f)

    # ── Export USD — hub interno, con materiali/texture/UV (default Blender) ─
    bpy.ops.wm.usd_export(
        filepath=usd_out,
        export_textures_mode="PRESERVE",  # come nello screenshot: "Preserve"
    )

    # ── Export GLB — per il viewer/AR ──────────────────────────────────────
    bpy.ops.export_scene.gltf(
        filepath=glb_out,
        export_format="GLB",
    )

    print(f"CONVERSIONE OK: {triangle_count} triangoli, {len(hierarchy)} componenti")


if __name__ == "__main__":
    main()
