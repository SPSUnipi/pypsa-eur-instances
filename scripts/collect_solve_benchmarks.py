# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Collect solve benchmarks and objectives below one or more results prefixes."""

import argparse
import json
import logging
import re
from pathlib import Path

import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        dest="prefixes",
        nargs="+",
        required=True,
        help="Prefixes below --results-root to scan (for example experiment/a experiment/b).",
    )
    parser.add_argument("--results-root", default=Path("results"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def parse_benchmark_name(stem: str, solver: str | None = None) -> dict:
    case_name = stem.removesuffix(f"_{solver}") if solver else stem
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
            {"network_type": "electricity", "clusters": clusters, "opts": opts}
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
        logger.warning("Results prefix does not exist: %s", root)
        return []
    paths: list[Path] = []
    for rule_dir in ["solve_network", "solve_sector_network"]:
        paths.extend(root.glob(f"**/benchmarks/{rule_dir}/*"))
    return sorted(path for path in paths if path.is_file())


def read_benchmark(path: Path) -> dict:
    benchmark = pd.read_csv(path, sep="\t").iloc[-1].to_dict()
    return {key: pd.NA if value == "NA" else value for key, value in benchmark.items()}


STATUS_RE = re.compile(
    r"Solving status ['\"](?P<status>[^'\"]+)['\"] "
    r"with termination condition ['\"](?P<condition>[^'\"]+)['\"]",
    re.IGNORECASE,
)
TERMINATION_RE = re.compile(
    r"(?:termination condition|termination status|model status)\s*[:=]\s*"
    r"(?P<condition>[A-Za-z_ -]+)", re.IGNORECASE
)
INFEASIBLE_RE = re.compile(r"\binfeasible\b", re.IGNORECASE)
TIME_LIMIT_RE = re.compile(
    r"\b(?:time[_ -]?limit|timelimit|max(?:imum)? time)\b", re.IGNORECASE
)


def result_directory(path: Path) -> Path:
    """Return the directory containing the benchmarks and networks folders."""
    benchmark_index = path.parts.index("benchmarks")
    return Path(*path.parts[:benchmark_index])


def solve_log_files(result_dir: Path, stem: str) -> list[Path]:
    logs = result_dir / "logs"
    return sorted({
        *logs.glob(f"**/{stem}_python.log"),
        *logs.glob(f"**/{stem}_solver.log"),
    })


def read_solve_status(result_dir: Path, stem: str, network_exists: bool) -> dict:
    """Infer solve outcome from Python/solver logs, including failed solves."""
    log_files = solve_log_files(result_dir, stem)
    text = "\n".join(p.read_text(errors="replace") for p in log_files)
    status_matches = list(STATUS_RE.finditer(text))
    status_match = status_matches[-1] if status_matches else None
    termination_matches = list(TERMINATION_RE.finditer(text))
    condition = (
        status_match.group("condition").strip()
        if status_match
        else (
            termination_matches[-1].group("condition").strip()
            if termination_matches
            else None
        )
    )
    infeasible = bool(INFEASIBLE_RE.search(condition or "")) or bool(
        re.search(r"Solving status ['\"]infeasible", text, re.IGNORECASE)
    )
    time_limit = bool(TIME_LIMIT_RE.search(condition or "")) or bool(
        re.search(
            r"(?:time limit reached|stopped on time|maximum time exceeded)",
            text,
            re.IGNORECASE,
        )
    )
    if status_match:
        status = status_match.group("status").strip()
    elif infeasible:
        status = "infeasible"
    elif time_limit:
        status = "warning"
    elif network_exists:
        status = "ok"
        condition = condition or "optimal"
    else:
        status = "failed"
        condition = condition or "unknown"
    return {
        "solve_status": status,
        "termination_condition": condition or pd.NA,
        "infeasible": infeasible,
        "time_limit_reached": time_limit,
        "solve_log_files": ";".join(p.as_posix() for p in log_files) or pd.NA,
    }


def read_network_metadata(path: Path) -> dict:
    """Read scalar result metadata without loading network component tables."""
    if not path.exists():
        logger.warning("No solved network found for %s", path)
        return {}

    with xr.open_dataset(path) as ds:
        metadata = {
            "network_file": path.as_posix(),
            "objective": ds.attrs.get("network__objective", pd.NA),
            "objective_constant": ds.attrs.get("network__objective_constant", pd.NA),
        }
        meta = ds.attrs.get("meta")

    if not meta:
        return metadata
    try:
        config = json.loads(meta)
        solver = config.get("solving", {}).get("solver", {})
        metadata.update(
            {
                "solver": config.get("wildcards", {}).get("solver"),
                "solver_name": solver.get("name", pd.NA),
                "solver_options": solver.get("options", pd.NA),
            }
        )
    except (TypeError, json.JSONDecodeError):
        logger.warning("Could not parse network metadata in %s", path)
    return metadata


def collect_benchmarks(roots: list[Path]) -> pd.DataFrame:
    rows = []
    for root in roots:
        for path in benchmark_files(root):
            result_dir = result_directory(path)
            network_path = result_dir / "networks" / f"{path.name}.nc"
            network_metadata = read_network_metadata(network_path)
            row = {
                "prefix": root.as_posix(),
                "case": result_dir.relative_to(root).as_posix(),
                "benchmark_rule": path.parent.name,
                "benchmark_file": path.as_posix(),
            }
            row.update(read_solve_status(result_dir, path.name, network_path.exists()))
            row.update(network_metadata)
            row.update(parse_benchmark_name(path.name, row.get("solver")))
            row.update(read_benchmark(path))
            rows.append(row)

    leading_columns = [
        "prefix",
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
        "network_file",
        "solve_status",
        "termination_condition",
        "infeasible",
        "time_limit_reached",
        "solve_log_files",
        "objective",
        "objective_constant",
    ]
    if not rows:
        return pd.DataFrame(columns=leading_columns)

    df = pd.DataFrame(rows)
    remaining_columns = [column for column in df.columns if column not in leading_columns]
    return df[leading_columns + remaining_columns].sort_values(
        ["prefix", "case", "benchmark_rule", "case_result", "solver"],
        na_position="last",
    )


def main() -> None:
    args = parse_args()
    roots = [args.results_root / prefix.strip("/") for prefix in args.prefixes]
    df = collect_benchmarks(roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    logger.info("Collected %s solve benchmark rows into %s", len(df), args.output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
