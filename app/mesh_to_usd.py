"""
Converte GLB/OBJ/STL in uno stage OpenUSD (.usdc), preservando geometria,
UV, materiali PBR (base color, metallic/roughness, normal map) e texture.
USD è lo strato nascosto interno: da qui partiranno le esportazioni
(GLB per il viewer, USDZ in futuro, metadata per la knowledge layer AI).

Nota sui limiti: STL non contiene mai UV/materiali/texture — è un limite
del formato stesso, non di questo convertitore. OBJ le contiene solo se
accompagnato da un file .mtl con texture referenziate.
"""
import os
import tempfile

import trimesh
from pxr import Usd, UsdGeom, UsdShade, Sdf, Kind


def convert_mesh_to_usd(input_path: str, output_usd_path: str, asset_name: str,
                         texture_dir: str = None) -> dict:
    """
    input_path: percorso file GLB/OBJ/STL
    output_usd_path: dove salvare il file .usdc risultante
    asset_name: nome logico dell'asset (usato per assetInfo)
    texture_dir: cartella dove salvare le texture estratte (creata se non passata)

    Ritorna un dict: {"triangle_count", "bounding_box", "hierarchy", "texture_dir"}
    texture_dir va rimossa dal chiamante dopo l'uso (contiene file temporanei).
    """
    loaded = trimesh.load(input_path, process=False, force=None)

    if texture_dir is None:
        texture_dir = tempfile.mkdtemp(prefix="arflow_tex_")

    stage = Usd.Stage.CreateNew(output_usd_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)

    root_path = "/Root"
    root_xform = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root_xform.GetPrim())

    root_xform.GetPrim().SetAssetInfoByKey("name", asset_name)
    root_xform.GetPrim().SetAssetInfoByKey("identifier", asset_name)

    triangle_count = 0
    hierarchy = []
    tex_counter = [0]

    if isinstance(loaded, trimesh.Scene):
        Usd.ModelAPI(root_xform.GetPrim()).SetKind(Kind.Tokens.assembly)
        for idx, (node_name, mesh) in enumerate(loaded.geometry.items()):
            prim_name = _safe_name(node_name, idx)
            _write_mesh_prim(stage, root_path, prim_name, mesh, texture_dir, tex_counter)
            triangle_count += len(mesh.faces)
            hierarchy.append(prim_name)
        bounds = loaded.bounds
    else:
        Usd.ModelAPI(root_xform.GetPrim()).SetKind(Kind.Tokens.component)
        prim_name = _safe_name(asset_name, 0)
        _write_mesh_prim(stage, root_path, prim_name, loaded, texture_dir, tex_counter)
        triangle_count = len(loaded.faces)
        hierarchy.append(prim_name)
        bounds = loaded.bounds

    stage.GetRootLayer().Save()

    bounding_box = None
    if bounds is not None:
        bounding_box = {"min": bounds[0].tolist(), "max": bounds[1].tolist()}

    return {
        "triangle_count": int(triangle_count),
        "bounding_box": bounding_box,
        "hierarchy": hierarchy,
        "texture_dir": texture_dir,
    }


def _write_mesh_prim(stage: Usd.Stage, parent_path: str, prim_name: str, mesh,
                      texture_dir: str, tex_counter: list) -> None:
    prim_path = f"{parent_path}/{prim_name}"
    usd_mesh = UsdGeom.Mesh.Define(stage, prim_path)

    points = [tuple(v) for v in mesh.vertices]
    face_indices = mesh.faces.flatten().tolist()
    face_counts = [3] * len(mesh.faces)  # trimesh triangola sempre

    usd_mesh.CreatePointsAttr(points)
    usd_mesh.CreateFaceVertexIndicesAttr(face_indices)
    usd_mesh.CreateFaceVertexCountsAttr(face_counts)

    if mesh.vertex_normals is not None and len(mesh.vertex_normals) == len(mesh.vertices):
        usd_mesh.CreateNormalsAttr([tuple(n) for n in mesh.vertex_normals])

    usd_mesh.CreateExtentAttr(
        UsdGeom.Boundable.ComputeExtentFromPlugins(usd_mesh, Usd.TimeCode.Default())
    )

    # ── UV (coordinate texture) ────────────────────────────────────────────────
    uv = getattr(getattr(mesh, "visual", None), "uv", None)
    has_uv = uv is not None and len(uv) == len(mesh.vertices)
    if has_uv:
        primvars_api = UsdGeom.PrimvarsAPI(usd_mesh)
        st_primvar = primvars_api.CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
        )
        st_primvar.Set([tuple(c) for c in uv])

    Usd.ModelAPI(usd_mesh.GetPrim()).SetKind(Kind.Tokens.component)

    # ── Materiale PBR + texture (se presenti) ─────────────────────────────────
    _write_material(stage, mesh, prim_path, texture_dir, tex_counter, has_uv)


def _write_material(stage, mesh, mesh_prim_path, texture_dir, tex_counter, has_uv):
    visual = getattr(mesh, "visual", None)
    if visual is None:
        return
    material = getattr(visual, "material", None)

    mat_path = f"{mesh_prim_path}/Material"
    usd_material = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")

    def _uv_reader():
        reader = UsdShade.Shader.Define(stage, f"{mat_path}/UVReader_{tex_counter[0]}")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        return reader

    def _save_texture(img, label):
        if img is None:
            return None
        try:
            path = os.path.join(texture_dir, f"{label}_{tex_counter[0]}.png")
            tex_counter[0] += 1
            img.convert("RGBA").save(path)
            return path
        except Exception:
            return None

    def _texture_shader(img, label):
        """Crea un nodo UsdUVTexture con canali r/g/b/a esposti. None se manca UV o immagine."""
        if not has_uv:
            return None
        path = _save_texture(img, label)
        if not path:
            return None
        tex = UsdShade.Shader.Define(stage, f"{mat_path}/{label}Tex")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(path)
        reader = _uv_reader()
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            reader.ConnectableAPI(), "result"
        )
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        tex.CreateOutput("r", Sdf.ValueTypeNames.Float)
        tex.CreateOutput("g", Sdf.ValueTypeNames.Float)
        tex.CreateOutput("b", Sdf.ValueTypeNames.Float)
        tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
        return tex

    def _norm_color(factor, default=(0.8, 0.8, 0.8)):
        if factor is None:
            return default
        vals = list(factor[:3])
        if max(vals) > 1.0:  # 0-255 -> 0-1
            vals = [v / 255.0 for v in vals]
        return tuple(vals)

    wrote_material = False

    # ── glTF / PBRMaterial (caso più comune: GLB con texture) ────────────────
    if material is not None and hasattr(material, "baseColorTexture"):
        base_tex = _texture_shader(getattr(material, "baseColorTexture", None), "BaseColor")
        if base_tex:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                base_tex.ConnectableAPI(), "rgb"
            )
            wrote_material = True
        else:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                _norm_color(getattr(material, "baseColorFactor", None))
            )

        mr_tex = _texture_shader(getattr(material, "metallicRoughnessTexture", None), "MetallicRoughness")
        if mr_tex:
            # Convenzione glTF: canale G = roughness, canale B = metallic
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(
                mr_tex.ConnectableAPI(), "g"
            )
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).ConnectToSource(
                mr_tex.ConnectableAPI(), "b"
            )
            wrote_material = True
        else:
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
                float(getattr(material, "roughnessFactor", 1.0) or 1.0)
            )
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(
                float(getattr(material, "metallicFactor", 0.0) or 0.0)
            )

        normal_tex = _texture_shader(getattr(material, "normalTexture", None), "Normal")
        if normal_tex:
            shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(
                normal_tex.ConnectableAPI(), "rgb"
            )
            wrote_material = True

        occlusion_tex = _texture_shader(getattr(material, "occlusionTexture", None), "Occlusion")
        if occlusion_tex:
            shader.CreateInput("occlusion", Sdf.ValueTypeNames.Float).ConnectToSource(
                occlusion_tex.ConnectableAPI(), "r"
            )

        emissive_tex = _texture_shader(getattr(material, "emissiveTexture", None), "Emissive")
        if emissive_tex:
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                emissive_tex.ConnectableAPI(), "rgb"
            )

    # ── OBJ / SimpleMaterial (diffuse texture singola, se presente il .mtl) ───
    elif material is not None and hasattr(material, "image") and material.image is not None:
        base_tex = _texture_shader(material.image, "BaseColor")
        if base_tex:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                base_tex.ConnectableAPI(), "rgb"
            )
            wrote_material = True
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

    # ── Nessuna texture/materiale rilevato: colore piatto di fallback ─────────
    else:
        flat_color = _norm_color(getattr(visual, "main_color", None))
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(flat_color)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

    shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    usd_material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(mesh_prim_path)).Bind(usd_material)


def _safe_name(raw_name, fallback_idx: int) -> str:
    """USD non accetta certi caratteri nei nomi dei prim."""
    if not raw_name:
        return f"part_{fallback_idx}"
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in str(raw_name))
    if safe and safe[0].isdigit():
        safe = f"p_{safe}"
    return safe or f"part_{fallback_idx}"
