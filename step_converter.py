"""
Conversione STEP/STP → glTF/GLB usando pythonocc-core (OpenCASCADE bindings)
e trimesh per l'export finale.

Pipeline:
1. pythonocc-core legge il file STEP (geometria B-Rep esatta)
2. Tessella la geometria in mesh triangolare (BRepMesh)
3. Estrae vertici/facce per ogni solido nell'assembly
4. trimesh assembla la scena e esporta in GLB
5. Estrae metadati: nomi componenti, gerarchia assembly, conteggio triangoli
"""
import os
import tempfile
import numpy as np
import trimesh

from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.BRep import BRep_Tool
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool
from OCC.Core.XCAFApp import XCAFApp_Application
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TDF import TDF_LabelSequence
from OCC.Core.TCollection import TCollection_ExtendedString
from OCC.Core.TDataStd import TDataStd_Name


def _mesh_face(face, location):
    """Estrae vertici e triangoli da una singola faccia tessellata."""
    triangulation = BRep_Tool.Triangulation(face, location)
    if triangulation is None:
        return None, None

    transform = location.Transformation()
    nb_nodes = triangulation.NbNodes()
    nb_triangles = triangulation.NbTriangles()

    vertices = np.zeros((nb_nodes, 3))
    for i in range(1, nb_nodes + 1):
        pnt = triangulation.Node(i)
        pnt_transformed = pnt.Transformed(transform)
        vertices[i - 1] = [pnt_transformed.X(), pnt_transformed.Y(), pnt_transformed.Z()]

    faces = np.zeros((nb_triangles, 3), dtype=np.int64)
    for i in range(1, nb_triangles + 1):
        tri = triangulation.Triangle(i)
        idx1, idx2, idx3 = tri.Get()
        faces[i - 1] = [idx1 - 1, idx2 - 1, idx3 - 1]

    return vertices, faces


def convert_step_to_glb(step_path: str, output_path: str, mesh_quality: float = 0.1) -> dict:
    """
    Converte un file STEP in GLB, preservando la gerarchia assembly come
    nodi separati nella scena trimesh (necessario per l'assembly tree nell'UI).

    Args:
        step_path: percorso del file .step/.stp in input
        output_path: percorso dove scrivere il .glb risultante
        mesh_quality: deflessione massima per la tessellazione (più basso = più dettagliato)

    Returns:
        dict con metadati: numero componenti, triangoli totali, nomi, errori
    """
    # ── Lettura STEP con XCAF per preservare nomi e struttura assembly ─────────
    app = XCAFApp_Application.GetApplication()
    doc = TDocStd_Document(TCollection_ExtendedString("step-doc"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)

    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise ValueError(f"Impossibile leggere il file STEP (status={status})")

    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)

    if labels.Length() == 0:
        raise ValueError("Nessuna geometria trovata nel file STEP")

    # ── Costruzione scena trimesh con un nodo per ogni shape di primo livello ──
    scene = trimesh.Scene()
    component_names = []
    total_triangles = 0
    errors = []

    for i in range(1, labels.Length() + 1):
        label = labels.Value(i)
        shape = shape_tool.GetShape(label)

        # Nome del componente: pattern via TDataStd_Name attribute.
        # Il binding SWIG di FindAttribute varia tra versioni pythonocc — proviamo
        # entrambi i pattern noti prima di accettare il nome generico di fallback.
        comp_name = f"component_{i}"
        try:
            name_attr = TDataStd_Name()
            result = label.FindAttribute(TDataStd_Name.GetID(), name_attr)
            # Alcune versioni restituiscono bool, altre (found, attr) come tupla
            found = result[0] if isinstance(result, tuple) else result
            if found:
                extracted = name_attr.Get().ToCString()
                if extracted:
                    comp_name = extracted
        except Exception:
            pass  # nome non disponibile, resta il fallback component_N

        # Tessellazione: converte la geometria B-Rep esatta in mesh triangolare
        try:
            BRepMesh_IncrementalMesh(shape, mesh_quality, False, 0.5, True)
        except Exception as e:
            errors.append(f"Tessellazione fallita per {comp_name}: {str(e)}")
            continue

        all_vertices = []
        all_faces = []
        vertex_offset = 0

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = explorer.Current()
            location = TopLoc_Location()
            vertices, faces = _mesh_face(face, location)

            if vertices is not None and len(vertices) > 0:
                all_vertices.append(vertices)
                all_faces.append(faces + vertex_offset)
                vertex_offset += len(vertices)

            explorer.Next()

        if not all_vertices:
            errors.append(f"Nessuna mesh generata per {comp_name}")
            continue

        merged_vertices = np.vstack(all_vertices)
        merged_faces = np.vstack(all_faces)

        try:
            mesh = trimesh.Trimesh(vertices=merged_vertices, faces=merged_faces, process=True)
            scene.add_geometry(mesh, node_name=comp_name)
            component_names.append(comp_name)
            total_triangles += len(mesh.faces)
        except Exception as e:
            errors.append(f"Costruzione mesh fallita per {comp_name}: {str(e)}")

    if len(scene.geometry) == 0:
        raise ValueError("Conversione fallita: nessun componente convertito con successo. " + "; ".join(errors))

    # ── Export GLB ──────────────────────────────────────────────────────────
    scene.export(output_path, file_type="glb")

    return {
        "component_count": len(component_names),
        "component_names": component_names,
        "triangle_count": total_triangles,
        "errors": errors if errors else None,
        "extraction_method": "pythonocc-core (OpenCASCADE) + trimesh — B-Rep esatto tessellato",
    }
