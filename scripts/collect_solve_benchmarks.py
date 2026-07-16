# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Collect solve benchmark files below a configured results prefix.
"""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from scripts._helpers import configure_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--solver-specs", default="[]")
    return parser.parse_args()


def solver_by_label(solver_specs: list[dict]) -> dict[str, dict]:
    return {str(spec["label"]): spec for spec in solver_specs}


def strip_solver(stem: str, solver_labels: list[str]) -> tuple[str, str | None]:
    for solver in sorted(solver_labels, key=len, reverse=True):
        suffix = f"_{solver}"
        if stem.endswith(suffix):
            return stem[: -len(suffix)], solver
    return stem, None


def parse_benchmark_name(stem: str, solver_labels: list[str]) -> dict:
    case_name, solver = strip_solver(stem, solver_labels)
    metadata = {
        "benchmark": stem,
        "case_result": case_name,
        "solver": solver,
        "network_type": pd.NA,
        "clusters": pd.NA,
        "opts": pd.NA,
        "sector_opts": pd.NA,
        "planning_horizons": pd.NA,
    }

    if not case_name.startswith("base_s_"):
        return metadata

    body = case_name.removeprefix("base_s_")
    if "_elec_" in body:
        clusters, opts = body.split("_elec_", 1)
        metadata.update(
            {
                "network_type": "electricity",
                "clusters": clusters,
                "opts": opts,
            }
        )
        return metadata

    parts = body.split("_")
    if len(parts) >= 4 and parts[-3:] == ["brownfield", "all", "years"]:
        metadata.update(
            {
                "network_type": "sector",
                "clusters": parts[0],
                "opts": parts[1] if len(parts) > 1 else "",
                "sector_opts": "_".join(parts[2:-3]),
                "planning_horizons": "brownfield_all_years",
            }
        )
    elif len(parts) >= 4:
        metadata.update(
            {
                "network_type": "sector",
                "clusters": parts[0],
                "opts": parts[1],
                "sector_opts": "_".join(parts[2:-1]),
                "planning_horizons": parts[-1],
            }
        )

    return metadata


def benchmark_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = []
    for rule_dir in ["solve_network", "solve_sector_network"]:
        paths.extend((root).glob(f"*/benchmarks/{rule_dir}/*"))
        paths.extend((root / "benchmarks" / rule_dir).glob("*"))
    return sorted(path for path in paths if path.is_file())


def read_benchmark(path: Path) -> dict:
    benchmark = pd.read_csv(path, sep="\t").iloc[-1].to_dict()
    return {key: pd.NA if value == "NA" else value for key, value in benchmark.items()}


def collect_benchmarks(root: Path, solver_specs: list[dict]) -> pd.DataFrame:
    solvers = solver_by_label(solver_specs)
    rows = []

    for path in benchmark_files(root):
        relative = path.relative_to(root)
        parts = relative.parts
        if parts[0] == "benchmarks":
            case = ""
            benchmark_rule = parts[1]
        else:
            case = parts[0]
            benchmark_rule = parts[2]

        row = {
            "case": case,
            "benchmark_rule": benchmark_rule,
            "benchmark_file": path.as_posix(),
        }
        row.update(parse_benchmark_name(path.name, list(solvers)))
        row.update(read_benchmark(path))

        solver = row.get("solver")
        if solver in solvers:
            row["solver_name"] = solvers[solver]["name"]
            row["solver_options"] = solvers[solver]["options"]
        else:
            row["solver_name"] = pd.NA
            row["solver_options"] = pd.NA

        rows.append(row)

    if not rows:
        return pd.DataFrame(
            columns=[
                "case",
                "benchmark_rule",
                "case_result",
                "solver",
                "solver_name",
                "solver_options",
                "network_type",
                "clusters",
                "opts",
                "sector_opts",
                "planning_horizons",
                "benchmark_file",
            ]
        )

    df = pd.DataFrame(rows)
    leading_columns = [
        "case",
        "benchmark_rule",
        "case_result",
        "solver",
        "solver_name",
        "solver_options",
        "network_type",
        "clusters",
        "opts",
        "sector_opts",
        "planning_horizons",
        "benchmark_file",
    ]
    remaining_columns = [column for column in df.columns if column not in leading_columns]
    return df[leading_columns + remaining_columns].sort_values(
        ["case", "benchmark_rule", "case_result", "solver"], na_position="last"
    )


def main() -> None:
    args = parse_args()
    solver_specs = json.loads(args.solver_specs)
    df = collect_benchmarks(args.benchmark_root, solver_specs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    logger.info("Collected %s solve benchmark rows into %s", len(df), args.output)


if __name__ == "__main__":
    if "snakemake" in globals():
        configure_logging(snakemake)
        solver_specs = list(snakemake.params.solver_specs)
        df = collect_benchmarks(Path(snakemake.params.benchmark_root), solver_specs)
        output = Path(snakemake.output.benchmarks)
        output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output, index=False)
        logger.info("Collected %s solve benchmark rows into %s", len(df), output)
    else:
        logging.basicConfig(level=logging.INFO)
        main()
