# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Compare solved electricity networks across configured solver runs.
"""

import logging
from pathlib import Path

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)

NETWORK_SIZE_COLUMNS = [
    "snapshots",
    "buses",
    "generators",
    "links",
    "lines",
    "storage_units",
    "stores",
]

BENCHMARK_VALUE_COLUMNS = [
    "s",
    "max_rss",
    "max_vms",
    "max_uss",
    "max_pss",
    "io_in",
    "io_out",
    "mean_load",
    "cpu_time",
    "speedup_vs_reference",
    "cpu_time_per_wall_second",
]


def normalize_index(series: pd.Series) -> pd.Series:
    """Ensure stable, named index levels for CSV export."""
    if isinstance(series.index, pd.MultiIndex):
        names = [
            name if name is not None else f"level_{i}"
            for i, name in enumerate(series.index.names)
        ]
        series.index = series.index.set_names(names)
    else:
        series.index.name = series.index.name or "item"
    return series


def compare_series(
    series_by_solver: dict[str, pd.Series],
    reference_solver: str,
    sort_index: bool = True,
) -> pd.DataFrame:
    values = pd.concat(series_by_solver, axis=1)
    if sort_index:
        values = values.sort_index()
    values.columns.name = "solver"
    reference = values[reference_solver]
    denominator = reference.abs()

    comparisons = {}
    for solver in values.columns:
        if solver == reference_solver:
            continue
        difference = values[solver] - reference
        comparisons[f"{solver}_difference_vs_{reference_solver}"] = difference
        comparisons[f"{solver}_relative_difference_vs_{reference_solver}"] = (
            difference / denominator.where(denominator != 0)
        )

    comparison_values = pd.DataFrame(comparisons, index=values.index)
    return pd.concat([values, comparison_values], axis=1).reset_index()


def compare_benchmarks(
    benchmarks: pd.DataFrame, solver_labels: list[str], reference_solver: str
) -> pd.DataFrame:
    benchmarks_by_solver = benchmarks.set_index("solver")
    benchmark_metrics = {}
    for solver in solver_labels:
        benchmark_metrics[solver] = pd.to_numeric(
            benchmarks_by_solver.loc[solver, BENCHMARK_VALUE_COLUMNS],
            errors="coerce",
        ).rename_axis("metric")
    return compare_series(benchmark_metrics, reference_solver, sort_index=False)


def move_columns_to_end(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    trailing = [column for column in columns if column in df.columns]
    leading = [column for column in df.columns if column not in trailing]
    return df[leading + trailing]


def read_benchmark(path: str, solver: dict, reference_seconds: float | None) -> dict:
    benchmark = pd.read_csv(path, sep="\t").iloc[-1].to_dict()
    seconds = benchmark.get("s")
    cpu_time = benchmark.get("cpu_time")
    benchmark.update(
        {
            "solver": solver["label"],
            "solver_name": solver["name"],
            "solver_options": solver["options"],
            "benchmark_file": path,
            "speedup_vs_reference": (
                reference_seconds / seconds
                if reference_seconds and seconds and seconds > 0
                else pd.NA
            ),
            "cpu_time_per_wall_second": (
                cpu_time / seconds if cpu_time and seconds and seconds > 0 else pd.NA
            ),
        }
    )
    return benchmark


def summarize_stat_differences(
    compared: pd.DataFrame,
    statistic: str,
    solver_labels: list[str],
    reference_solver: str,
) -> pd.DataFrame:
    rows = []
    for solver in solver_labels:
        if solver == reference_solver:
            diff = pd.Series(0.0, index=compared.index)
            rel_diff = pd.Series(0.0, index=compared.index)
        else:
            diff = compared[f"{solver}_difference_vs_{reference_solver}"].abs()
            rel_diff = compared[
                f"{solver}_relative_difference_vs_{reference_solver}"
            ].abs()

        rel_diff = rel_diff.replace([float("inf")], pd.NA)
        rows.append(
            {
                "solver": solver,
                f"{statistic}_max_abs_difference": diff.max(skipna=True),
                f"{statistic}_max_abs_relative_difference": rel_diff.max(skipna=True),
                f"{statistic}_missing_vs_reference": int(
                    compared[solver]
                    .isna()
                    .where(compared[reference_solver].notna(), False)
                    .sum()
                ),
                f"{statistic}_extra_vs_reference": int(
                    compared[reference_solver]
                    .isna()
                    .where(compared[solver].notna(), False)
                    .sum()
                ),
                "is_reference": solver == reference_solver,
            }
        )
    return pd.DataFrame(rows)


def solve_network_metadata(n: pypsa.Network, solver: dict, network_path: str) -> dict:
    return {
        "solver": solver["label"],
        "solver_name": solver["name"],
        "solver_options": solver["options"],
        "network_file": network_path,
        "objective": getattr(n, "objective", pd.NA),
        "objective_constant": getattr(n, "objective_constant", pd.NA),
        "snapshots": len(n.snapshots),
        "buses": len(n.buses),
        "generators": len(n.generators),
        "links": len(n.links),
        "lines": len(n.lines),
        "storage_units": len(n.storage_units),
        "stores": len(n.stores),
    }


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "make_solver_comparison",
            clusters="2",
            opts="",
            configfiles="config/smspp.yaml",
        )

    configure_logging(snakemake)
    set_scenario_config(snakemake)

    solver_specs = list(snakemake.params.solver_specs)
    if len(solver_specs) != len(snakemake.input.networks) or len(
        solver_specs
    ) != len(snakemake.input.benchmarks):
        raise ValueError(
            "Solver specs, solved networks and benchmark files must have matching lengths."
        )
    reference_solver = solver_specs[0]["label"]

    pypsa.set_option("params.statistics.nice_names", False)
    pypsa.set_option("params.statistics.drop_zero", False)

    optimal_capacity = {}
    energy_balance = {}
    metadata = []

    for solver, network_path in zip(solver_specs, snakemake.input.networks):
        logger.info("Loading solved network for solver %s", solver["label"])
        n = pypsa.Network(network_path)
        if "carrier" not in n.lines:
            n.lines["carrier"] = "AC"

        optimal_capacity[solver["label"]] = normalize_index(
            n.statistics.optimal_capacity().sort_index()
        )
        energy_balance[solver["label"]] = normalize_index(
            n.statistics.energy_balance().sort_index()
        )
        metadata.append(solve_network_metadata(n, solver, network_path))

    optimal_capacity_compared = compare_series(optimal_capacity, reference_solver)
    energy_balance_compared = compare_series(energy_balance, reference_solver)

    reference_benchmark = pd.read_csv(snakemake.input.benchmarks[0], sep="\t").iloc[-1]
    reference_seconds = reference_benchmark.get("s")
    benchmarks = pd.DataFrame(
        [
            read_benchmark(path, solver, reference_seconds)
            for solver, path in zip(solver_specs, snakemake.input.benchmarks)
        ]
    )
    benchmark_compared = compare_benchmarks(
        benchmarks, [solver["label"] for solver in solver_specs], reference_solver
    )

    summary = pd.DataFrame(metadata)
    for stat_summary in [
        summarize_stat_differences(
            optimal_capacity_compared,
            "optimal_capacity",
            [solver["label"] for solver in solver_specs],
            reference_solver,
        ),
        summarize_stat_differences(
            energy_balance_compared,
            "energy_balance",
            [solver["label"] for solver in solver_specs],
            reference_solver,
        ),
    ]:
        summary = summary.merge(
            stat_summary.drop(columns=["is_reference"]),
            on="solver",
            how="left",
        )
    summary = summary.merge(
        benchmarks[
            [
                "solver",
                "s",
                "max_rss",
                "mean_load",
                "cpu_time",
                "speedup_vs_reference",
                "cpu_time_per_wall_second",
            ]
        ],
        on="solver",
        how="left",
    )
    summary = move_columns_to_end(summary, NETWORK_SIZE_COLUMNS)

    for output in snakemake.output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)

    optimal_capacity_compared.to_csv(snakemake.output.optimal_capacity, index=False)
    energy_balance_compared.to_csv(snakemake.output.energy_balance, index=False)
    benchmark_compared.to_csv(snakemake.output.benchmarks, index=False)
    summary.to_csv(snakemake.output.summary, index=False)
