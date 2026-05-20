#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import expm_multiply

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.mesh_space import map_metrics
from utils.path_defaults import resolve_dataset_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate geodesic-aware diffusion on Visual Attention for Rendered 3D Shapes."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="Root directory of the Visual Attention for Rendered 3D Shapes dataset.",
    )
    parser.add_argument(
        "--objects",
        nargs="+",
        default=["hand-35K", "A380", "bunny"],
        help="Object stems as used in 3DModels-Simplif and FixationMaps.",
    )
    parser.add_argument("--view", default="300")
    parser.add_argument(
        "--sigma-visual-deg",
        type=float,
        default=1.0,
        help="Published visual-angle sigma from the paper. 1.0 deg corresponds to 49 px.",
    )
    parser.add_argument(
        "--vertex-angle-deg",
        type=float,
        default=0.1,
        help="Approximate vertex spacing in visual angle from the paper.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            REPO_ROOT / "results" / "visual_attention_3d_shapes" / "geodesic_diffusion_results.json"
        ),
    )
    return parser.parse_args()


def load_obj_graph(obj_path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    faces = []
    with obj_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                verts.append((float(x), float(y), float(z)))
            elif line.startswith("f "):
                parts = line.split()[1:]
                idx = []
                for p in parts:
                    idx.append(int(p.split("/")[0]) - 1)
                if len(idx) >= 3:
                    faces.append(idx[:3])
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def build_weighted_laplacian(vertices: np.ndarray, faces: np.ndarray):
    edge_pairs = set()
    for tri in faces:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        for u, v in ((a, b), (b, c), (c, a)):
            if u > v:
                u, v = v, u
            edge_pairs.add((u, v))

    rows = []
    cols = []
    weights = []
    edge_lengths = []

    for u, v in edge_pairs:
        length = float(np.linalg.norm(vertices[u] - vertices[v]))
        if length == 0.0:
            continue
        w = 1.0 / length
        rows.extend([u, v])
        cols.extend([v, u])
        weights.extend([w, w])
        edge_lengths.append(length)

    n = len(vertices)
    W = coo_matrix((weights, (rows, cols)), shape=(n, n)).tocsr()
    degree = np.asarray(W.sum(axis=1)).ravel()
    L = diags(degree) - W
    mean_edge = float(np.mean(edge_lengths))
    return L, mean_edge


def load_subject_maps(dataset_root: Path, object_stem: str, view: str):
    per_subj_dir = dataset_root / "PerSubjectFixations"

    candidates = []
    if object_stem == "hand-35K":
        candidates = sorted(per_subj_dir.glob(f"hand_{view}.csv.T*.result"))
    else:
        candidates = sorted(per_subj_dir.glob(f"{object_stem}_{view}.csv.T*.result"))

    train = []
    test = []
    train_ids = []
    test_ids = []
    for f in candidates:
        tid = int(f.name.split(".T")[1].split(".result")[0])
        arr = np.loadtxt(f)
        if tid % 2 == 1:
            train.append(arr)
            train_ids.append(tid)
        else:
            test.append(arr)
            test_ids.append(tid)

    return np.stack(train), np.stack(test), train_ids, test_ids


def main() -> None:
    args = parse_args()
    dataset_root = resolve_dataset_root(
        args.dataset_root,
        env_var="VISUAL_ATTENTION_3D_SHAPES_ROOT",
        dataset_name="Visual Attention for Rendered 3D Shapes",
        example_path="/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GazeToGT/Visual Attention for Rendered 3D Shapes",
    )
    results = []
    sigma_vertex_steps = args.sigma_visual_deg / args.vertex_angle_deg

    for object_stem in args.objects:
        obj_path = dataset_root / "3DModels-Simplif" / f"{object_stem}.obj"
        vis_name = f"{object_stem}_{args.view}_visibility.txt"
        if object_stem == "hand-35K":
            vis_name = f"hand-35K_{args.view}_visibility.txt"

        vertices, faces = load_obj_graph(obj_path)
        laplacian, mean_edge = build_weighted_laplacian(vertices, faces)
        sigma_mesh = sigma_vertex_steps * mean_edge
        t = (sigma_mesh ** 2) / 2.0

        train_stack, test_stack, train_ids, test_ids = load_subject_maps(
            dataset_root, object_stem, args.view
        )
        train_map = train_stack.mean(axis=0)
        test_map = test_stack.mean(axis=0)
        vis = np.loadtxt(dataset_root / "CentricityAndVisibilityMaps" / vis_name) > 0

        baseline_metrics = map_metrics(
            train_map,
            test_map,
            vis,
            include_auc_visible_top20=True,
            kl_key="KL_test_to_pred",
        )

        diffused = expm_multiply((-t) * laplacian, train_map.astype(np.float64))
        diffused = np.maximum(diffused, 0.0)
        if diffused.sum() > 0.0 and train_map.sum() > 0.0:
            diffused *= train_map.sum() / diffused.sum()

        geodesic_metrics = map_metrics(
            diffused,
            test_map,
            vis,
            include_auc_visible_top20=True,
            kl_key="KL_test_to_pred",
        )

        results.append(
            {
                "object": object_stem,
                "view": args.view,
                "num_vertices": int(len(vertices)),
                "num_faces": int(len(faces)),
                "visible_vertices": int(vis.sum()),
                "train_subject_ids": train_ids,
                "test_subject_ids": test_ids,
                "mean_edge_length": mean_edge,
                "sigma_vertex_steps": sigma_vertex_steps,
                "sigma_mesh_units": sigma_mesh,
                "heat_time_t": t,
                "baseline_metrics": baseline_metrics,
                "geodesic_diffused_metrics": geodesic_metrics,
            }
        )

    payload = {
        "notes": {
            "dataset_root": str(dataset_root),
            "experiment": "apply geodesic-aware heat diffusion to published train_map and compare against test_map",
            "limitation": "raw fixation points are not public, so this is not an exact re-run of the original mapping stage",
            "sigma_mapping": "1 degree visual angle / 0.1 degree per vertex ~= 10 vertex spacings",
        },
        "results": results,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\nSaved report: {args.output_json}")


if __name__ == "__main__":
    main()
