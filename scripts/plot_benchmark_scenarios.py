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
    configure_plot_style,
    draw_series,
    figure_legend,
    prepare_data,
    save_figure,
    solver_colors,
    solver_label,
    style_axis,
)


def annotate_ratio(ax, data, metric, colors, mode):
    """Annotate percentage changes, using only solved observations."""
    solved = data.loc[data.outcome == "solved"]
    pairs = []
    if mode == "growth":
        for solver, group in solved.groupby("solver_options"):
            group = group.sort_values("scenarios")
            if group.scenarios.nunique() > 1:
                first, last = group.iloc[0], group.iloc[-1]
                pairs.append((first.scenarios, first[metric], last.scenarios,
                              last[metric], last[metric] / first[metric], colors[solver]))
    else:
        reference = solved.loc[solved.solver_options == "gurobi-default", ["scenarios", metric]]
        for solver, group in solved.loc[solved.solver_options.str.startswith("smspp")].groupby("solver_options"):
            matched = group.merge(reference, on="scenarios", suffixes=("", "_ref"))
            if matched.empty:
                continue
            row = matched.loc[(matched[metric + "_ref"] - matched[metric]).abs().idxmax()]
            pairs.append((row.scenarios, row[metric], row.scenarios,
                          row[metric + "_ref"], row[metric + "_ref"] / row[metric], colors[solver]))
    for x0, y0, x1, y1, ratio, color in pairs:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="<->", linestyle="--", color="black",
                                    linewidth=1.6, connectionstyle="arc3,rad=0.12"))
        midpoint = math.sqrt(y0 * y1) if ax.get_yscale() == "log" else (y0 + y1) / 2
        change = 100 * (ratio - 1) if mode == "growth" else 100 * (1 / ratio - 1)
        ax.annotate(f"{change:+.1f}%", xy=((x0 + x1) / 2, midpoint),
                    xytext=(12, 8), textcoords="offset points", color="black",
                    fontweight="bold", bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))


def plot_relative_objective_error(data, output, nodes, periods, hours, variant, colors):
    """Compare total objectives against the matching PyPSA/Gurobi run."""
    reference_solver = "gurobi-default" if "gurobi-default" in data.solver_options.values else "gurobi-32"
    reference = data.loc[
        (data.solver_options == reference_solver) & (data.outcome == "solved"),
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
        fig, ax = plt.subplots(figsize=(10, 3.5 if signed else 7), constrained_layout=True)
        for solver, subset in valid.groupby("solver_options"):
            subset = subset.sort_values("scenarios")
            values = subset.relative_error
            if not signed:
                values = values.abs().where(values != 0)
            ax.plot(subset.scenarios, values, marker="o", linewidth=2,
                    color=colors[solver], label=solver_label(solver))
        style_axis(ax, False)
        if signed:
            # Keep the sign; only a small neighbourhood of zero is linear.
            nonzero = valid.relative_error.abs().loc[valid.relative_error != 0]
            threshold = (
                10 ** math.floor(math.log10(nonzero.min()))
                if not nonzero.empty else 1e-8
            )
            ax.set_yscale("symlog", linthresh=threshold)
            tolerance = 1e-5
            for bound in (-tolerance, tolerance):
                ax.axhline(
                    bound, color="#777777", linestyle="--", linewidth=1,
                    label="Reference bounds ±1e−5" if bound > 0 else None,
                )
            lower, upper = ax.get_ylim()
            ax.set_ylim(min(lower, -1.5 * tolerance), max(upper, 1.5 * tolerance))
            ax.axhline(0, color="#777777", linewidth=0.8)
            ax.set_ylabel("Relative error")
        else:
            ax.set_yscale("log")
            ax.set_ylabel("Absolute relative objective error |(SMS++ − PyPSA) / PyPSA|")
            ax.set_title("Absolute error · logarithmic y-axis", loc="left")
        ax.yaxis.set_major_formatter(LogFormatterSciNotation())
        ax.set_xticks(sorted(data.scenarios.unique()))
        ax.set_xlabel("Number of scenarios")
        reference_note = " · reference: PyPSA-gurobi-32" if reference_solver == "gurobi-32" else ""
        fig.suptitle(
            "Objective error" if signed else f"{nodes} nodes · {int(periods)} × {int(hours)} h · {variant}{reference_note}",
            fontweight="bold",
        )
        if signed:
            handles, labels = ax.get_legend_handles_labels()
            fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False, fontsize=14)
        else:
            ax.legend(frameon=False)
        save_figure(fig, output / (stem + ("_signed" if signed else "")), ["png", "pdf"], 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ratio-arrows", choices=["comparison", "growth"])
    parser.add_argument("--ratio-solver", help="Restrict comparison arrows to this solver option set.")
    parser.add_argument("--total-time-only", action="store_true", help="Hide compute-time curves and legend entries.")
    parser.add_argument("--dpi", type=int, default=400)
    args = parser.parse_args()
    configure_plot_style()
    if args.total_time_only:
        for setting in (
            "font.size", "axes.titlesize", "axes.labelsize",
            "xtick.labelsize", "ytick.labelsize", "figure.titlesize",
        ):
            plt.rcParams[setting] += 2
        plt.rcParams["legend.fontsize"] -= 1
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
        if metric == "memory_gib" or args.total_time_only:
            subset[list(SMSPP_TIMING_STYLES)] = float("nan")
        fig, ax = plt.subplots(figsize=(10, 5.2 if args.total_time_only else 7), constrained_layout=True)
        draw_series(ax, subset, "scenarios", solvers, colors, metric)
        if args.total_time_only:
            for annotation in ax.texts:
                annotation.set_fontsize(annotation.get_fontsize() + 2)
        style_axis(ax, log_scale)
        if metric == "runtime_s":
            for family in ("gurobi", "smspp-tssb-ib"):
                family_data = subset.loc[subset.solver_options.isin([f"{family}-16", f"{family}-64"])]
                for scenarios, points in family_data.groupby("scenarios"):
                    if scenarios not in (10, 100, 200):
                        continue
                    low, high = points.runtime_s.min(), points.runtime_s.max()
                    divisor, unit = (3600, "h") if low >= 3600 else ((60, "min") if low >= 60 else (1, "s"))
                    text = f"{low / divisor:.1f}–{high / divisor:.1f} {unit}"
                    above = family == "gurobi"
                    anchor = high if above else low
                    ax.annotate(
                        text, xy=(scenarios, anchor),
                        xytext=(0, 15 if above else -27),
                        textcoords="offset points", ha="center", fontsize=14,
                        color=colors[f"{family}-64"],
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1),
                        annotation_clip=False,
                    )
        if args.ratio_arrows and metric == "runtime_s":
            ratio_data = subset
            if args.ratio_solver:
                ratio_data = subset.loc[subset.solver_options.isin(["gurobi-default", args.ratio_solver])]
            annotate_ratio(ax, ratio_data, metric, colors, args.ratio_arrows)
        ax.set_xticks(sorted(data.scenarios.unique()))
        ax.set_xlabel("Number of scenarios")
        ax.set_ylabel(ylabel)
        ax.set_title(
            f"{args.nodes} nodes · {int(periods)} × {int(hours)} h · {variant}",
            loc="left",
        )
        fig.suptitle("Computational time" if metric == "runtime_s" else "Peak memory", fontweight="bold")
        legend_columns = 3 if len(solvers) > 3 else 2
        figure_legend(fig, subset, solvers, colors, ncols=legend_columns if args.total_time_only else 3)
        save_figure(fig, output / f"{stem}_{args.nodes}_nodes", ["png", "pdf"], args.dpi)
    print(data[["scenarios", "solver_options", "runtime_s", "memory_gib", "outcome"]].to_string(index=False))


if __name__ == "__main__":
    main()
