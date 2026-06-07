#!/usr/bin/env python3
"""
Generate visual diagnostic bundles for the worst MeshMamba benchmark cases.

Reads the benchmark CSV, selects:
  - top-N worst rows by KLD (largest first)
  - top-N worst rows by CC (smallest first)

For each selected row it runs the appropriate MeshMamba GT viewer:
  - screen_space -> preview_meshmamba_screenspace_alignment.py
  - cone         -> preview_meshmamba_cone_alignment.py

Outputs:
  <output-root>/
    generated/<case-id>/...png
    worst_kld_top10/...
    worst_cc_top10/...
    worst_kld_top10.zip
    worst_cc_top10.zip
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_BY_METHOD = {
    "cone": REPO_ROOT / "gt_visualizations" / "preview_meshmamba_cone_alignment.py",
    "screen_space": REPO_ROOT / "gt_visualizations" / "preview_meshmamba_screenspace_alignment.py",
}
METHOD_FILENAME_BY_METHOD = {
    "cone": "cone_gaussian_on_mesh",
    "screen_space": "screen_space_gaussian",
}


@dataclass(frozen=True)
class CaseRow:
    texture_type: str
    model: str
    method: str
    cc: float
    kld: float
    source_row: dict[str, str]

    @property
    def case_key(self) -> str:
        return f"{self.texture_type}__{self.method}__{self.model}"

    @property
    def output_stem(self) -> str:
        return f"{self.model}__{METHOD_FILENAME_BY_METHOD[self.method]}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--benchmark-csv",
        type=Path,
        default=REPO_ROOT
        / "results"
        / "benchmark_runs"
        / "meshmamba"
        / "2026-06-02_meshmamba_reference"
        / "meshmamba_reference_long.csv",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT
        / "results"
        / "diagnostics"
        / "2026-06-02_meshmamba_worst_cases",
    )
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument(
        "--python-bin",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter used to launch the viewer scripts.",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip case generation if the expected summary PNG already exists.",
    )
    return p.parse_args()


def load_rows(csv_path: Path) -> list[CaseRow]:
    rows: list[CaseRow] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") != "ok":
                continue
            method = row.get("method", "")
            if method not in VIEWER_BY_METHOD:
                continue
            try:
                cc = float(row["CC"])
                kld = float(row["KLD"])
            except Exception:
                continue
            rows.append(
                CaseRow(
                    texture_type=row["texture_type"],
                    model=row["model"],
                    method=method,
                    cc=cc,
                    kld=kld,
                    source_row=row,
                )
            )
    return rows


def pick_rankings(rows: list[CaseRow], top_n: int) -> dict[str, list[CaseRow]]:
    return {
        "worst_kld": sorted(rows, key=lambda r: (-r.kld, r.cc, r.case_key))[:top_n],
        "worst_cc": sorted(rows, key=lambda r: (r.cc, -r.kld, r.case_key))[:top_n],
    }


def generate_case(
    case: CaseRow,
    output_dir: Path,
    python_bin: Path,
    skip_existing: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_png = output_dir / f"{case.output_stem}__summary.png"
    if skip_existing and summary_png.exists():
        return

    cmd = [
        str(python_bin),
        str(VIEWER_BY_METHOD[case.method]),
        "--model",
        case.model,
        "--texture-type",
        case.texture_type,
        "--output-dir",
        str(output_dir),
    ]
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def copy_case_into_bundle(
    case: CaseRow,
    rank: int,
    generated_root: Path,
    bundle_root: Path,
) -> None:
    src_dir = generated_root / case.case_key
    dst_dir = bundle_root / f"{rank:02d}__{case.texture_type}__{case.method}__{case.model}"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)


def write_manifest_csv(bundle_root: Path, rows: list[CaseRow], metric_name: str) -> Path:
    out_csv = bundle_root / f"{metric_name}_manifest.csv"
    fieldnames = [
        "rank",
        "selection_metric",
        "selection_value",
        "texture_type",
        "method",
        "model",
        "CC",
        "KLD",
        "report_path",
        "stdout_log_path",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, case in enumerate(rows, start=1):
            writer.writerow(
                {
                    "rank": idx,
                    "selection_metric": metric_name,
                    "selection_value": f"{getattr(case, metric_name.split('_', 1)[1]):.6f}",
                    "texture_type": case.texture_type,
                    "method": case.method,
                    "model": case.model,
                    "CC": f"{case.cc:.6f}",
                    "KLD": f"{case.kld:.6f}",
                    "report_path": case.source_row.get("report_path", ""),
                    "stdout_log_path": case.source_row.get("stdout_log_path", ""),
                }
            )
    return out_csv


def make_zip(bundle_root: Path) -> Path:
    archive_base = bundle_root.parent / bundle_root.name
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=str(bundle_root.parent), base_dir=bundle_root.name)
    return Path(archive_path)


def main() -> None:
    args = parse_args()
    rows = load_rows(args.benchmark_csv)
    rankings = pick_rankings(rows, args.top_n)

    args.output_root.mkdir(parents=True, exist_ok=True)
    generated_root = args.output_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    unique_cases: dict[str, CaseRow] = {}
    for cases in rankings.values():
        for case in cases:
            unique_cases[case.case_key] = case

    futures = {}
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        for case in unique_cases.values():
            out_dir = generated_root / case.case_key
            futures[
                pool.submit(
                    generate_case,
                    case,
                    out_dir,
                    args.python_bin,
                    args.skip_existing,
                )
            ] = case

        for future in as_completed(futures):
            case = futures[future]
            future.result()
            print(f"[done] {case.case_key}")

    for metric_name, cases in rankings.items():
        bundle_root = args.output_root / f"{metric_name}_top{args.top_n}"
        if bundle_root.exists():
            shutil.rmtree(bundle_root)
        bundle_root.mkdir(parents=True, exist_ok=True)

        for idx, case in enumerate(cases, start=1):
            copy_case_into_bundle(case, idx, generated_root, bundle_root)
        write_manifest_csv(bundle_root, cases, metric_name)
        zip_path = make_zip(bundle_root)
        print(f"[zip] {zip_path}")

    print(f"\nOutput root: {args.output_root}")


if __name__ == "__main__":
    main()
