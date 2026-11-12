"""Plot relative objective errors against network size, matching Gurobi cases."""

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot_solve_benchmarks import prepare_data, save_figure, style_axis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    data = prepare_data(args.input)
    keys = ["case_variant", "scenarios", "clusters", "periods", "hours_per_period"]
    solved = data.loc[data.outcome == "solved"]
    reference = solved.loc[solved.solver_options == "gurobi-default", keys + ["objective"]]
    reference = reference.rename(columns={"objective": "gurobi_objective"})
    errors = solved.loc[solved.solver_options.str.startswith("smspp")].merge(
        reference, on=keys, how="left", validate="many_to_one"
    )
    errors["relative_error"] = (errors.objective - errors.gurobi_objective) / errors.gurobi_objective.where(errors.gurobi_objective != 0)
    output = args.output_dir or args.input.parent / "plots"
    output.mkdir(parents=True, exist_ok=True)
    stem = "benchmark_relative_objective_error_node_scaling"
    errors.to_csv(output / f"{stem}.csv", index=False)
    valid = errors.dropna(subset=["relative_error"])
    if valid.empty:
        raise ValueError("No solved SMS++ cases with matching nonzero Gurobi objectives")
    for signed in (False, True):
        fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
        for (solver, variant, scenarios, periods, hours), subset in valid.groupby(
            ["solver_options", "case_variant", "scenarios", "periods", "hours_per_period"]
        ):
            subset = subset.sort_values("clusters")
            values = subset.relative_error if signed else subset.relative_error.abs().where(subset.relative_error != 0)
            label = f"{solver} · {periods:g} × {hours:g} h"
            if variant or scenarios != 1:
                label += f" · {variant} · {scenarios:g} scenarios"
            ax.plot(subset.clusters, values, marker="o", linewidth=2, label=label)
        style_axis(ax, False)
        if signed:
            nonzero = valid.relative_error.abs().loc[valid.relative_error != 0]
            threshold = 10 ** math.floor(math.log10(nonzero.min())) if not nonzero.empty else 1e-8
            ax.set_yscale("symlog", linthresh=threshold)
            ax.axhline(0, color="#777777", linewidth=0.8)
            ax.set_ylabel("Relative objective error (SMS++ − Gurobi) / Gurobi")
            ax.set_title(f"Signed error · symlog (linear within ±{threshold:g})", loc="left")
        else:
            ax.set_yscale("log")
            ax.set_ylabel("Absolute relative objective error |(SMS++ − Gurobi) / Gurobi|")
            ax.set_title("Absolute error · logarithmic y-axis", loc="left")
        ax.set_xticks(sorted(data.clusters.unique()))
        ax.set_xlabel("Network nodes (clusters)")
        ax.legend(frameon=False)
        fig.suptitle("Objective accuracy · Network size", fontweight="bold")
        save_figure(fig, output / (stem + ("_signed" if signed else "")), ["png", "pdf"], 220)
    print(errors[keys + ["solver_options", "relative_error"]].to_string(index=False))


if __name__ == "__main__":
    main()
