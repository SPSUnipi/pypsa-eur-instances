"""Plot memory and signed objective error side by side with one legend."""

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import LogFormatterSciNotation

from plot_solve_benchmarks import (
    configure_plot_style,
    draw_series,
    prepare_data,
    save_figure,
    solver_colors,
    solver_label,
    style_axis,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    configure_plot_style()
    plt.rcParams.update({
        "axes.labelsize": 21, "axes.titlesize": 23,
        "xtick.labelsize": 20, "ytick.labelsize": 20,
        "legend.fontsize": 20, "figure.titlesize": 24,
    })
    data = prepare_data(args.input)
    data = data.loc[data.clusters == args.nodes].copy()
    dimensions = data[["case_variant", "periods", "hours_per_period"]].drop_duplicates()
    if len(dimensions) != 1:
        raise ValueError("Select one time resolution and case variant")
    variant, periods, hours = dimensions.iloc[0]
    reference_solver = "gurobi-default" if "gurobi-default" in data.solver_options.values else "gurobi-32"
    reference = data.loc[
        (data.solver_options == reference_solver) & (data.outcome == "solved"),
        ["scenarios", "objective"],
    ].rename(columns={"objective": "reference_objective"})
    errors = data.loc[data.solver_options.str.startswith("smspp")].merge(
        reference, on="scenarios", how="left", validate="many_to_one"
    )
    errors["relative_error"] = (
        (errors.objective - errors.reference_objective)
        / errors.reference_objective.where(errors.reference_objective != 0)
    )
    errors = errors.dropna(subset=["relative_error"])
    if errors.empty:
        raise ValueError("No relative objective errors available")
    solvers = sorted(data.solver_options.unique())
    colors = solver_colors(solvers)
    fig, (memory_ax, error_ax) = plt.subplots(
        1, 2, figsize=(20, 8.5), constrained_layout=True,
    )
    draw_series(memory_ax, data, "scenarios", solvers, colors, "memory_gib")
    style_axis(memory_ax, False)
    memory_ax.set_ylabel("Peak resident memory [GiB]")
    memory_ax.set_title("Peak memory", loc="left", fontweight="semibold")
    for solver, subset in errors.groupby("solver_options"):
        subset = subset.sort_values("scenarios")
        error_ax.plot(subset.scenarios, subset.relative_error,
                      color=colors[solver], marker="o", linewidth=2)
    style_axis(error_ax, False)
    nonzero = errors.relative_error.abs().loc[errors.relative_error != 0]
    threshold = 10 ** math.floor(math.log10(nonzero.min())) if not nonzero.empty else 1e-8
    error_ax.set_yscale("symlog", linthresh=threshold)
    error_ax.yaxis.set_major_formatter(LogFormatterSciNotation())
    for bound in (-1e-5, 1e-5):
        error_ax.axhline(bound, color="#777777", linestyle="--", linewidth=1.2)
    error_ax.axhline(0, color="#777777", linewidth=0.8)
    lower, upper = error_ax.get_ylim()
    error_ax.set_ylim(min(lower, -1.5e-5), max(upper, 1.5e-5))
    error_ax.set_title("Objective error", loc="left", fontweight="semibold")
    error_ax.set_ylabel("(SMS++ − PyPSA) / PyPSA")
    for ax in (memory_ax, error_ax):
        ax.set_xticks(sorted(data.scenarios.unique()))
        ax.set_xlabel("Number of scenarios")
    handles = [Line2D([], [], color=colors[s], marker="o", linewidth=2,
                      label=solver_label(s)) for s in solvers]
    handles.append(Line2D([], [], color="#777777", linestyle="--",
                          label="Reference bounds ±1e−5"))
    fig.legend(handles=handles, loc="outside lower center", ncols=4, frameon=False)
    fig.suptitle(
        f"{args.nodes} nodes · {int(periods)} × {int(hours)} h · {variant}"
        f"\nObjective reference: {solver_label(reference_solver)}",
        fontweight="bold",
    )
    output = args.output_dir or args.input.parent
    output.mkdir(parents=True, exist_ok=True)
    save_figure(fig, output / f"benchmark_memory_and_relative_objective_error_{args.nodes}_nodes",
                ["png", "pdf"], 400)


if __name__ == "__main__":
    main()
