"""UCBlock instances with nuclear units from a PyPSA-Eur electricity network.

PyPSA-Eur aggregates the nuclear capacity of a cluster into one generator,
whose unit commitment makes little sense; here it is split into modules of a
realistic size before the translation. The network is cut to a window of
snapshots, a slack generator is added to every bus with a load, and the PyPSA
optimum is computed once; then the network is translated three times:

- `tub`: the nuclear units are ThermalUnitBlocks, as without `nuclear_units`;
- `nub-free`: they are NuclearUnitBlocks whose rules do not bind (the full
  ramps outside the modulations and no other rule), i.e., the same problem;
- `nub-modulation`, `nub-daily`, `nub-bands`, `nub-deep`: one family of the
  rules at a time on top of the modulations, which says what each of them
  costs;
- `nub-rules`: they are NuclearUnitBlocks with `nuclear_rules_default`.

The inflow of the hydro units is cut at their largest outflow, since a
HydroUnitBlock cannot spill, and the networks carry Kirchhoff's voltage law, as
those of PyPSA do.
The first two must match the PyPSA objective; the third can only be above it,
since PyPSA has no such rules. For each variant it writes
`<name>_<variant>.nc` (the SMS++ input) in `--outdir`, and a line per variant
in `<name>.csv` with both objectives and their relative difference:

    python gen_pypsaeur_nuclear.py --network base_s_11_elec_.nc \\
        --snapshots 24 --start 0 --outdir out --name fr11_d0

It needs `smspp_ucblock_solver` in the PATH, built with the NuclearUnitBlock rules.
"""

import argparse
import csv
import logging
import warnings
from pathlib import Path

import pypsa

from pypsa2smspp.constants import nuclear_rules_default
from pypsa2smspp.network_correction import (
    add_slack_unit,
    clean_dispatch_setpoints,
    clean_global_constraints,
    split_traditional_generators_into_modules,
)
from pypsa2smspp.transformation import Transformation

warnings.filterwarnings("ignore")

NON_BINDING_RULES = {key: None for key in nuclear_rules_default}
NON_BINDING_RULES.update(modulation_ramp_fraction=1.0, modulation_time=2.0)

def with_rules(*names):
    """The non-binding rules, with the named ones as nuclear_rules_default has
    them."""
    merged = dict(NON_BINDING_RULES)
    merged.update({name: nuclear_rules_default[name] for name in names})
    return merged


VARIANTS = {
    "tub": None,
    "nub-free": NON_BINDING_RULES,
    # one family of rules at a time, to see what each of them costs
    "nub-modulation": with_rules("modulation_ramp_fraction", "modulation_time",
                                 "max_modulation_length"),
    "nub-daily": with_rules("modulation_ramp_fraction", "modulation_time",
                            "max_modulation_length", "day_length",
                            "modulations_per_day", "start_ups_per_day"),
    "nub-bands": with_rules("modulation_ramp_fraction", "modulation_time",
                            "power_bands"),
    "nub-deep": with_rules("modulation_ramp_fraction", "modulation_time",
                           "day_length", "deep_decrease_threshold",
                           "deep_decrease_gradient", "deep_decreases_per_day",
                           "deep_decrease_cost"),
    "nub-rules": True,
}


def prepare(args):
    n = pypsa.Network(str(args.network))

    # the load shedding of PyPSA-Eur has an infinite capacity: use ours
    n.remove("Generator", n.generators.index[n.generators.carrier == "load"])

    n.set_snapshots(n.snapshots[args.start:args.start + args.snapshots])
    n = clean_dispatch_setpoints(n)
    n = clean_global_constraints(n)
    n = add_slack_unit(n, exclude_suffixes=())
    # a HydroUnitBlock cannot spill: an inflow above the largest outflow makes
    # a cyclic reservoir infeasible, so it is cut there for both models
    inflow = n.storage_units_t.inflow
    if not inflow.empty:
        su = n.storage_units.loc[inflow.columns]
        largest = su.p_nom * su.p_max_pu / su.efficiency_dispatch
        n.storage_units_t.inflow = inflow.clip(upper=largest, axis=1)
    n = split_traditional_generators_into_modules(
        n,
        module_sizes={"nuclear": args.module_size},
        n_modules={"nuclear": args.max_modules},
        verbose=False,
    )
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--snapshots", type=int, default=24)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--module-size", type=float, default=1300.0)
    parser.add_argument("--max-modules", type=int, default=100)
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--solver", default="gurobi")
    parser.add_argument("--mip-gap", type=float, default=1e-7)
    parser.add_argument("--configfile", default="auto")
    # a BlockConfig, e.g., the network formulation, relative to the directory
    # of --configfile
    parser.add_argument("--blockconfig", default=None)
    parser.add_argument("--outdir", type=Path, default=Path("."))
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    name = args.name or f"{args.network.stem}_{args.start}_{args.snapshots}"
    args.outdir.mkdir(parents=True, exist_ok=True)

    reference = prepare(args)
    options = {"MIPGap": args.mip_gap} if args.solver == "gurobi" else {
        "mip_rel_gap": args.mip_gap}
    reference.optimize(solver_name=args.solver, solver_options=options)
    obj_pypsa = float(reference.objective + reference.objective_constant)
    nuclear = int((reference.generators.carrier == "nuclear").sum())
    print(f"{name}: PyPSA {obj_pypsa:.10g}, {nuclear} nuclear units")

    rows = []
    for variant in args.variants.split(","):
        rules = VARIANTS[variant]
        transformation = Transformation(
            capacity_expansion_ucblock=True,
            enable_thermal_units=True,
            kirchhoff_voltage_law=True,
            nuclear_units=None if rules is None else {"nuclear": rules},
            workdir=args.outdir,
            name=f"{name}_{variant}",
            overwrite=True,
            fp_temp="{name}.nc",
            fp_log="{name}_log.txt",
            fp_solution="{name}_solution.nc",
            configfile=args.configfile,
            pysmspp_options=None if args.blockconfig is None else {
                "B": args.blockconfig},
        )
        # the objective is all we need, not the solution mapped back to PyPSA
        transformation.create_model(prepare(args), verbose=False)
        transformation.optimize(verbose=False)
        obj_smspp = float(transformation.result.objective_value)
        # a rule-bearing instance is a hard MILP: what the solver gives may be
        # a pair of bounds rather than an optimum, hence the bound and the
        # status go with the value
        bound = getattr(transformation.result, "lower_bound", None)
        bound = None if bound is None else float(bound)
        status = str(transformation.result.status)
        rel = (obj_smspp - obj_pypsa) / abs(obj_pypsa)
        gap = ("" if bound is None or not obj_smspp
               else f"  gap {abs(obj_smspp - bound) / abs(obj_smspp):.1e}")
        print(f"  {variant:15s} SMS++ {obj_smspp:.10g}  rel {rel:+.3e}{gap}"
              f"  [{status}]")
        rows.append({"name": name, "variant": variant,
                     "snapshots": args.snapshots, "start": args.start,
                     "nuclear_units": nuclear, "obj_pypsa": obj_pypsa,
                     "obj_smspp": obj_smspp, "rel_diff": rel,
                     "lower_bound": bound, "status": status})

    with open(args.outdir / f"{name}.csv", "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
