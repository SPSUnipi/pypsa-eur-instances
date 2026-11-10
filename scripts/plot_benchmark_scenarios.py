"""Plot runtime and memory against scenario count at a fixed network size."""

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import LogFormatterSciNotation

from plot_solve_benchmarks import (
    SMSPP_TIMING_STYLES,
    draw_series,
    figure_legend,
    prepare_data,
    save_figure,
    solver_colors,
    style_axis,
)


def plot_relative_objective_error(data, output, nodes, periods, hours, variant, colors):
    """Compare total objectives against the matching PyPSA/Gurobi run."""
    reference = data.loc[
        (data.solver_options == "gurobi-default") & (data.outcome == "solved"),
        ["scenarios", "objective"],
    ].rename(columns={"objective": "pypsa_objective"})
    errors = data.loc[data.solver_options.str.startswith("smspp")].merge(
        reference, on="scenarios", how="left", validate="many_to_one"
    )
    errors["relative_error"] = (
        (errors.objective - errors.pypsa_objective)
        / errors.pypsa_objective.where(errors.pypsa_objective != 0)
    )
    stem = f"benchmark_relative_objective_error_scenario_scaling_{nodes}_nodes"
    errors[["scenarios", "solver_options", "objective", "pypsa_objective", "relative_error"]].to_csv(
        output / f"{stem}.csv", index=False
    )
    valid = errors.dropna(subset=["relative_error"]).copy()
    if valid.empty:
        return
    for signed in (False, True):
        fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
        for solver, subset in valid.groupby("solver_options"):
            subset = subset.sort_values("scenarios")
            values = subset.relative_error
            if not signed:
                values = values.abs().where(values != 0)
            ax.plot(subset.scenarios, values, marker="o", linewidth=2,
                    color=colors[solver], label=solver)
        style_axis(ax, False)
        if signed:
            # Keep the sign; only a small neighbourhood of zero is linear.
            nonzero = valid.relative_error.abs().loc[valid.relative_error != 0]
            threshold = (
                10 ** math.floor(math.log10(nonzero.min()))
                if not nonzero.empty else 1e-8
            )
            ax.set_yscale("symlog", linthresh=threshold)
            ax.axhline(0, color="#777777", linewidth=0.8)
            ax.set_ylabel("Relative objective error (SMS++ − PyPSA) / PyPSA")
            ax.set_title(f"Signed error · symlog (linear within ±{threshold:g})", loc="left")
        else:
            ax.set_yscale("log")
            ax.set_ylabel("Absolute relative objective error |(SMS++ − PyPSA) / PyPSA|")
            ax.set_title("Absolute error · logarithmic y-axis", loc="left")
        ax.yaxis.set_major_formatter(LogFormatterSciNotation())
        ax.set_xticks(sorted(data.scenarios.unique()))
        ax.set_xlabel("Number of scenarios")
        fig.suptitle(f"{nodes} nodes · {int(periods)} × {int(hours)} h · {variant}", fontweight="bold")
        ax.legend(frameon=False)
        save_figure(fig, output / (stem + ("_signed" if signed else "")), ["png", "pdf"], 220)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    data = prepare_data(args.input)
    data = data.loc[data.clusters == args.nodes].copy()
    if data.empty:
        raise ValueError(f"No benchmarks for {args.nodes} nodes")
    dimensions = data[["case_variant", "periods", "hours_per_period"]].drop_duplicates()
    if len(dimensions) != 1:
        raise ValueError("Select a single case variant and time resolution")
    variant, periods, hours = dimensions.iloc[0]
    output = args.output_dir or args.input.parent / "plots"
    output.mkdir(parents=True, exist_ok=True)
    data.sort_values(["scenarios", "solver_options"]).to_csv(
        output / f"benchmark_scenario_scaling_{args.nodes}_nodes.csv", index=False
    )
    solvers = sorted(data.solver_options.unique())
    colors = solver_colors(solvers)
    plot_relative_objective_error(data, output, args.nodes, periods, hours, variant, colors)
    for metric, ylabel, stem, log_scale in (
        ("runtime_s", "Wall-clock runtime [s]", "benchmark_scenario_scaling", True),
        ("memory_gib", "Peak resident memory [GiB]", "benchmark_memory_scenario_scaling", False),
    ):
        subset = data.loc[data[metric].notna() & (data[metric] > 0)].copy()
        if subset.empty:
            raise ValueError(f"No positive observations for {metric}")
        if metric == "memory_gib":
            subset[list(SMSPP_TIMING_STYLES)] = float("nan")
        fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
        draw_series(ax, subset, "scenarios", solvers, colors, metric)
        style_axis(ax, log_scale)
        ax.set_xticks(sorted(data.scenarios.unique()))
        ax.set_xlabel("Number of scenarios")
        ax.set_ylabel(ylabel)
        ax.set_title(
            f"{args.nodes} nodes · {int(periods)} × {int(hours)} h · {variant}",
            loc="left",
        )
        fig.suptitle("Solver computational performance", fontweight="bold")
        figure_legend(fig, subset, solvers, colors)
        save_figure(fig, output / f"{stem}_{args.nodes}_nodes", ["png", "pdf"], 220)
    print(data[["scenarios", "solver_options", "runtime_s", "memory_gib", "outcome"]].to_string(index=False))


if __name__ == "__main__":
    main()
