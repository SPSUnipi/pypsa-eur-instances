# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Plot computational scaling from a collected solve benchmark CSV.

Examples
--------
python scripts/plot_solve_benchmarks.py \
    results/dispatch-power-IT-noUC/benchmarks.csv

python scripts/plot_solve_benchmarks.py benchmarks.csv \
    --output-dir plots --formats png pdf --log-scale
"""

import argparse
import logging
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

logger = logging.getLogger(__name__)

TIME_RESOLUTION_RE = re.compile(r"(?:^|/)th_(?P<periods>\d+)c(?P<hours>\d+)(?:$|/)")
REQUIRED_COLUMNS = {"case", "clusters", "solver_options", "s"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Collected benchmark CSV.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: <input directory>/plots).",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf"],
        choices=["png", "pdf", "svg"],
        help="Output formats (default: png pdf).",
    )
    parser.add_argument(
        "--log-scale",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use a logarithmic runtime axis (default: enabled).",
    )
    parser.add_argument(
        "--title",
        default="Solver computational performance",
        help="Figure title.",
    )
    parser.add_argument(
        "--dpi", type=int, default=220, help="Raster output resolution (default: 220)."
    )
    return parser.parse_args()


def parse_time_resolution(case: object) -> tuple[int, int] | None:
    """Extract ``(number of periods, hours per period)`` from a case path."""
    match = TIME_RESOLUTION_RE.search(str(case))
    if match is None:
        return None
    return int(match["periods"]), int(match["hours"])


def prepare_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {', '.join(sorted(missing))}"
        )

    parsed = data["case"].map(parse_time_resolution)
    unparsed_cases = sorted(data.loc[parsed.isna(), "case"].astype(str).unique())
    if unparsed_cases:
        logger.warning(
            "Ignoring %d row(s) whose case does not contain th_<periods>c<hours>: %s",
            int(parsed.isna().sum()),
            ", ".join(unparsed_cases),
        )
    data = data.loc[parsed.notna()].copy()
    if data.empty:
        raise ValueError("No time resolutions like 'th_24c24' were found in case.")

    data[["periods", "hours_per_period"]] = pd.DataFrame(
        parsed.dropna().tolist(), index=data.index
    )
    data["modeled_hours"] = data["periods"] * data["hours_per_period"]
    data["clusters"] = pd.to_numeric(data["clusters"], errors="coerce")
    data["runtime_s"] = pd.to_numeric(data["s"], errors="coerce")
    data["solver_options"] = data["solver_options"].fillna(data.get("solver"))
    data["solver_options"] = data["solver_options"].fillna("unspecified").astype(str)

    valid = (
        data["clusters"].notna()
        & data["runtime_s"].notna()
        & (data["runtime_s"] > 0)
    )
    if not valid.all():
        logger.warning("Ignoring %d row(s) with invalid clusters/runtime.", (~valid).sum())
    data = data.loc[valid].copy()
    if data.empty:
        raise ValueError("No rows have valid clusters and positive runtime in column 's'.")

    # Repeated runs of the same configuration are summarized robustly.
    group_columns = [
        "solver_options",
        "clusters",
        "periods",
        "hours_per_period",
        "modeled_hours",
    ]
    return (
        data.groupby(group_columns, as_index=False, dropna=False)["runtime_s"]
        .median()
        .sort_values(["periods", "hours_per_period", "clusters", "solver_options"])
    )


def resolution_label(periods: int, hours: int) -> str:
    unit = "day" if periods == 1 else "days"
    return f"{periods} × {hours} h ({periods} {unit})"


def duration_label(seconds: float, _position: float = 0) -> str:
    if seconds < 60:
        return f"{seconds:g} s"
    if seconds < 3600:
        return f"{seconds / 60:g} min"
    return f"{seconds / 3600:g} h"


def solver_colors(solvers: list[str]) -> dict[str, object]:
    palette = plt.get_cmap("tab10")
    return {solver: palette(index % 10) for index, solver in enumerate(solvers)}


def style_axis(ax: plt.Axes, log_scale: bool) -> None:
    ax.grid(axis="y", color="#D9DEE7", linewidth=0.8)
    ax.grid(axis="x", color="#EDF0F4", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#AAB2BF")
    if log_scale:
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(LogLocator(base=10, numticks=8))
        ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(duration_label))


def draw_series(
    ax: plt.Axes,
    data: pd.DataFrame,
    x: str,
    solvers: list[str],
    colors: dict[str, object],
) -> None:
    for solver in solvers:
        subset = data.loc[data["solver_options"] == solver].sort_values(x)
        if subset.empty:
            continue
        ax.plot(
            subset[x],
            subset["runtime_s"],
            color=colors[solver],
            marker="o",
            markersize=5.5,
            markeredgecolor="white",
            markeredgewidth=0.8,
            linewidth=2,
            label=solver,
        )


def make_node_scaling_figure(
    data: pd.DataFrame,
    solvers: list[str],
    colors: dict[str, object],
    title: str,
    log_scale: bool,
) -> plt.Figure:
    resolutions = (
        data[["periods", "hours_per_period"]]
        .drop_duplicates()
        .sort_values(["periods", "hours_per_period"])
        .itertuples(index=False, name=None)
    )
    resolutions = list(resolutions)
    columns = min(3, len(resolutions))
    rows = math.ceil(len(resolutions) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(5.1 * columns, 3.8 * rows),
        sharey=True,
        squeeze=False,
        constrained_layout=True,
    )
    for ax, (periods, hours) in zip(axes.flat, resolutions):
        subset = data.loc[
            (data["periods"] == periods) & (data["hours_per_period"] == hours)
        ]
        draw_series(ax, subset, "clusters", solvers, colors)
        style_axis(ax, log_scale)
        ax.set_title(resolution_label(periods, hours), loc="left", fontweight="semibold")
        ax.set_xlabel("Network nodes (clusters)")
        ax.set_xticks(sorted(subset["clusters"].unique()))
    for ax in axes[:, 0]:
        ax.set_ylabel("Wall-clock runtime")
    for ax in axes.flat[len(resolutions) :]:
        ax.set_visible(False)
    figure.suptitle(f"{title}\nScaling with network size", fontweight="bold", fontsize=15)
    handles = [
        plt.Line2D([], [], color=colors[s], marker="o", linewidth=2, label=s)
        for s in solvers
    ]
    figure.legend(
        handles=handles,
        loc="outside lower center",
        ncols=min(len(solvers), 4),
        frameon=False,
        title="Solver options",
    )
    return figure


def make_time_scaling_figure(
    data: pd.DataFrame,
    solvers: list[str],
    colors: dict[str, object],
    title: str,
    log_scale: bool,
) -> plt.Figure:
    clusters = sorted(data["clusters"].unique())
    columns = min(3, len(clusters))
    rows = math.ceil(len(clusters) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(5.1 * columns, 3.8 * rows),
        sharey=True,
        squeeze=False,
        constrained_layout=True,
    )
    ordered_resolutions = (
        data[["modeled_hours", "periods", "hours_per_period"]]
        .drop_duplicates()
        .sort_values("modeled_hours")
    )
    ticks = ordered_resolutions["modeled_hours"].tolist()
    tick_labels = [
        f"{periods}c{hours}"
        for _, periods, hours in ordered_resolutions.itertuples(index=False, name=None)
    ]
    for ax, cluster in zip(axes.flat, clusters):
        subset = data.loc[data["clusters"] == cluster]
        draw_series(ax, subset, "modeled_hours", solvers, colors)
        style_axis(ax, log_scale)
        ax.set_title(f"{cluster:g} nodes", loc="left", fontweight="semibold")
        ax.set_xlabel("Time resolution (periods × hours)")
        ax.set_xticks(ticks, tick_labels, rotation=35, ha="right")
    for ax in axes[:, 0]:
        ax.set_ylabel("Wall-clock runtime")
    for ax in axes.flat[len(clusters) :]:
        ax.set_visible(False)
    figure.suptitle(f"{title}\nScaling with modeled time", fontweight="bold", fontsize=15)
    handles = [
        plt.Line2D([], [], color=colors[s], marker="o", linewidth=2, label=s)
        for s in solvers
    ]
    figure.legend(
        handles=handles,
        loc="outside lower center",
        ncols=min(len(solvers), 4),
        frameon=False,
        title="Solver options",
    )
    return figure


def save_figure(
    figure: plt.Figure, output_stem: Path, formats: list[str], dpi: int
) -> None:
    for extension in formats:
        path = output_stem.with_suffix(f".{extension}")
        figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        logger.info("Wrote %s", path)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.input.parent / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    data = prepare_data(args.input)
    solvers = sorted(data["solver_options"].unique())
    colors = solver_colors(solvers)

    node_figure = make_node_scaling_figure(
        data, solvers, colors, args.title, args.log_scale
    )
    save_figure(
        node_figure, output_dir / "benchmark_node_scaling", args.formats, args.dpi
    )
    time_figure = make_time_scaling_figure(
        data, solvers, colors, args.title, args.log_scale
    )
    save_figure(
        time_figure, output_dir / "benchmark_time_scaling", args.formats, args.dpi
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
