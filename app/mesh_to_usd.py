"""
Converte GLB/OBJ/STL in uno stage OpenUSD (.usdc).
USD è lo strato nascosto interno: da qui partiranno le esportazioni
(GLB per il viewer, USDZ in futuro, metadata per la knowledge layer AI).
"""
import trimesh
from pxr import Usd, UsdGeom, Kind


def convert_mesh_to_usd(input_path: str, output_usd_path: str, asset_name: str) -> str:
    """
    input_path: percorso file GLB/OBJ/STL
    output_usd_path: dove salvare il file .usdc risultante
    asset_name: nome logico dell'asset (usato per assetInfo)
    """
    loaded = trimesh.load(input_path, process=False, force=None)

    stage = Usd.Stage.CreateNew(output_usd_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)

    root_path = "/Root"
    root_xform = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root_xform.GetPrim())

    # assetInfo — utile in futuro per collegamento a BOM/PLM
    root_xform.GetPrim().SetAssetInfoByKey("name", asset_name)
    root_xform.GetPrim().SetAssetInfoByKey("identifier", asset_name)

    if isinstance(loaded, trimesh.Scene):
        # glTF con più nodi/gerarchia: assembly con più component
        Usd.ModelAPI(root_xform.GetPrim()).SetKind(Kind.Tokens.assembly)
        geometries = loaded.geometry

        for idx, (node_name, mesh) in enumerate(geometries.items()):
            _write_mesh_prim(
                stage,
                parent_path=root_path,
                prim_name=_safe_name(node_name, idx),
                mesh=mesh,
            )
    else:
        # OBJ/STL: quasi sempre una singola mesh -> component singolo
        Usd.ModelAPI(root_xform.GetPrim()).SetKind(Kind.Tokens.component)
        _write_mesh_prim(
            stage,
            parent_path=root_path,
            prim_name=_safe_name(asset_name, 0),
            mesh=loaded,
        )

    stage.GetRootLayer().Save()
    return output_usd_path


def _write_mesh_prim(stage: Usd.Stage, parent_path: str, prim_name: str, mesh) -> None:
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

    Usd.ModelAPI(usd_mesh.GetPrim()).SetKind(Kind.Tokens.component)


def _safe_name(raw_name, fallback_idx: int) -> str:
    """USD non accetta certi caratteri nei nomi dei prim."""
    if not raw_name:
        return f"part_{fallback_idx}"
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in str(raw_name))
    if safe and safe[0].isdigit():
        safe = f"p_{safe}"
    return safe or f"part_{fallback_idx}"
