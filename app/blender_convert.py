"""
Script eseguito DENTRO Blender in modalità headless (bpy). Uso:

  blender --background --factory-startup --python blender_convert.py -- \
      <input> <usd_output> <glb_output> <meta_output>

Importa il file sorgente usando gli importer nativi di Blender, poi esporta:
  - USD (.usdc): hub interno nascosto, con materiali/texture/UV/gerarchia
  - GLB: per il viewer web/AR
  - JSON metadata: triangle_count, bounding_box, hierarchy (gerarchia VERA,
    non solo lista di mesh — includono anche gli Empty/gruppi, come si vede
    nell'Outliner di Blender)

Nota sui parametri Blender: i nomi esatti delle property di wm.usd_export
cambiano tra versioni (es. export_textures -> export_textures_mode in 5.0).
Per non far crashare lo script su un nome sbagliato, i parametri desiderati
vengono filtrati contro le property REALMENTE presenti in questa versione di
Blender (_filter_supported_kwargs) — quelli non supportati vengono ignorati
e loggati, non causano un errore fatale.
"""
import sys
import os
import json

import bpy
from mathutils import Vector


# ── Import multi-formato, con fallback su nomi di operatori alternativi ───────
# (alcuni operatori sono stati rinominati tra versioni Blender: es. STL/OBJ
# sono passati da import_mesh.*/import_scene.* a wm.*_import in Blender 4.x+)
IMPORT_CANDIDATES = {
    ".glb": [("import_scene", "gltf")],
    ".gltf": [("import_scene", "gltf")],
    ".obj": [("wm", "obj_import"), ("import_scene", "obj")],
    ".stl": [("wm", "stl_import"), ("import_mesh", "stl")],
    ".ply": [("wm", "ply_import"), ("import_mesh", "ply")],
    ".fbx": [("import_scene", "fbx")],
    ".abc": [("wm", "alembic_import")],
}


def _import_file(input_path: str) -> None:
    ext = os.path.splitext(input_path)[1].lower()
    candidates = IMPORT_CANDIDATES.get(ext)
    if not candidates:
        raise ValueError(f"Formato non supportato da questo script: {ext}")

    last_error = None
    for namespace, opname in candidates:
        try:
            op = getattr(getattr(bpy.ops, namespace), opname)
            op(filepath=input_path)
            return
        except AttributeError as e:
            last_error = e
            continue
    raise RuntimeError(
        f"Nessun operatore di import disponibile per {ext} in questa versione "
        f"di Blender (provati: {candidates}). Ultimo errore: {last_error}"
    )


def _filter_supported_kwargs(operator, desired: dict) -> dict:
    """Mantiene solo le property che esistono davvero su questo operatore,
    in questa versione di Blender. Evita crash su nomi di parametro cambiati."""
    try:
        valid_props = {p.identifier for p in operator.get_rna_type().properties}
    except Exception:
        # Se l'introspezione fallisce per qualche motivo, meglio non passare nulla
        # di rischioso piuttosto che far crashare l'intera conversione.
        print("[ARFlow] Introspezione parametri operatore fallita, uso solo filepath.")
        return {}

    supported, skipped = {}, []
    for key, value in desired.items():
        if key in valid_props:
            supported[key] = value
        else:
            skipped.append(key)
    if skipped:
        print(f"[ARFlow] Parametri non presenti in questa versione di Blender, ignorati: {skipped}")
    return supported


def _build_hierarchy(objects) -> list:
    """Gerarchia VERA (parent/child), non solo l'elenco delle mesh — include
    Empty e gruppi, esattamente come si vedono nell'Outliner di Blender."""
    objects = list(objects)
    roots = [o for o in objects if o.parent is None]

    def node_for(obj):
        node = {"name": obj.name, "type": obj.type}
        if obj.type == "MESH" and obj.data:
            mesh = obj.data
            mesh.calc_loop_triangles()
            node["triangles"] = len(mesh.loop_triangles)
            materials = [slot.material.name for slot in obj.material_slots if slot.material]
            if materials:
                node["materials"] = materials
        children = [c for c in objects if c.parent == obj]
        if children:
            node["children"] = [node_for(c) for c in children]
        return node

    return [node_for(r) for r in roots]


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]
    input_path, usd_out, glb_out, meta_out = argv[:4]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _import_file(input_path)

    scene_objects = list(bpy.context.scene.objects)
    mesh_objects = [o for o in scene_objects if o.type == "MESH"]

    triangle_count = 0
    min_co = [float("inf")] * 3
    max_co = [float("-inf")] * 3

    for obj in mesh_objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        triangle_count += len(mesh.loop_triangles)
        for corner in obj.bound_box:
            world_co = obj.matrix_world @ Vector(corner)
            for i in range(3):
                min_co[i] = min(min_co[i], world_co[i])
                max_co[i] = max(max_co[i], world_co[i])

    metadata = {
        "triangle_count": triangle_count,
        "bounding_box": {"min": min_co, "max": max_co} if mesh_objects else None,
        "hierarchy": _build_hierarchy(scene_objects),
    }
    with open(meta_out, "w") as f:
        json.dump(metadata, f)

    # ── Export USD — impostazioni allineate a quelle scelte per il progetto ──
    # (Root Prim /root, Animation incluse, texture "keep", USD Preview Surface).
    # I parametri qui sotto sono filtrati automaticamente: se un nome non esiste
    # in questa versione di Blender viene ignorato e loggato, non crasha nulla.
    desired_usd_kwargs = {
        "root_prim_path": "/root",
        "selected_objects_only": False,
        "export_animation": True,
        "export_custom_properties": True,
        "author_blender_name": True,
        "allow_unicode": True,
        "relative_paths": True,
        "convert_orientation": False,
        "export_uvmaps": True,
        "export_normals": True,
        "export_materials": True,
        "generate_preview_surface": True,
        "generate_materialx_network": True,
        "export_textures_mode": "KEEP",
        "export_meshes": True,
        "export_lights": True,
        "export_cameras": True,
        "export_curves": True,
        "export_shapekeys": True,
        "export_armatures": True,
    }
    usd_kwargs = _filter_supported_kwargs(bpy.ops.wm.usd_export, desired_usd_kwargs)
    bpy.ops.wm.usd_export(filepath=usd_out, **usd_kwargs)

    # ── Export GLB — per il viewer/AR ──────────────────────────────────────
    bpy.ops.export_scene.gltf(filepath=glb_out, export_format="GLB")

    print(f"CONVERSIONE OK: {triangle_count} triangoli, {len(scene_objects)} oggetti")


if __name__ == "__main__":
    main()
