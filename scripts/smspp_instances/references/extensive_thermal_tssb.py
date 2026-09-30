"""The deterministic equivalent of a thermal instance, solved by PyPSA.

PyPSA cannot optimize a network that is at once stochastic and committable
(its committability constraints do not know about the scenario axis), so the
two-stage problem of gen_thermal_tssb.py is written out here as one ordinary
network: one copy of every scenario, on its own buses and over the same
snapshots, so that the minimum up and down times and the ramps of a unit see
the horizon they see in the scenario; every cost of a copy is multiplied by
the probability of its scenario, so that the objective is the expected cost,
and the capacities decided in the first stage are tied across the copies.
The capital cost is weighted as well, the weights summing to 1, so that a
capacity shared by every copy is paid once.

This is the monolithic reference against which a decomposition in SMS++ is
compared, i.e., the MILP that PyPSA would hand to its solver:

    python extensive_thermal_tssb.py tuc_u80_t168_s3_b1 [gurobi] [Key=value]

The options after the solver name are passed to it as they are, e.g.,
BestBdStop=<bound> asks Gurobi to stop as soon as its bound reaches the one a
Lagrangian dual has given, which makes the two runs deliver the same thing.
The word `relax` among them solves the continuous relaxation of the same
model instead (Gurobi only); it is weaker than the one of the model SMS++
writes, whose formulation of the commitment is tighter, so that an LP
solver such as PIPS-IPM++ is compared with Gurobi on the latter.
"""

import sys
import time
import warnings
from pathlib import Path

import pypsa

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _pypsa2smspp import TEST  # noqa: E402
# written by gen_thermal_tssb.py of the references of pypsa2smspp
DATA = TEST / "output" / "thermal_tssb"

COMPONENTS = ("Bus", "Link", "Generator", "Load", "StorageUnit")
WEIGHTED = ("marginal_cost", "start_up_cost", "shut_down_cost", "capital_cost")


def build(stochastic):
    """One network holding a copy of every scenario, and what they share."""
    weights = stochastic.scenario_weightings["weight"]
    n = None
    shared = {}
    for scenario in stochastic.scenarios:
        copy = stochastic.get_scenario(scenario)
        weight = float(weights.loc[scenario])
        for component in ("Generator", "StorageUnit"):
            static = copy.components[component].static
            for column in WEIGHTED:
                if column in static.columns:
                    static[column] = static[column] * weight
            if not static.empty:
                for name in static.index[static.p_nom_extendable]:
                    shared.setdefault((component, name), []).append(
                        f"{name} {scenario}")
        # every name of the copy, and every reference to a bus, gets the
        # scenario as a suffix, so that the copies are disjoint networks
        def suffix(name, scenario=scenario):
            return f"{name} {scenario}"
        for component in COMPONENTS:
            c = copy.components[component]
            if c.static.empty:
                continue
            c.static.rename(index=suffix, inplace=True)
            for column in ("bus", "bus0", "bus1"):
                if column in c.static.columns:
                    c.static[column] = c.static[column].map(suffix)
            for frame in c.dynamic.values():
                frame.rename(columns=suffix, inplace=True)
        n = copy if n is None else n.merge(copy,
                                           components_to_skip=["Carrier"])
    return n, shared


def tie(n, snapshots, shared):
    """Every copy of a first-stage capacity holds one value."""
    for (component, _), copies in shared.items():
        capacity = n.model[f"{component}-p_nom"]
        for other in copies[1:]:
            n.model.add_constraints(
                capacity.loc[copies[0]] - capacity.loc[other] == 0,
                name=f"tie {copies[0]} {other}")


def solve_relaxation(n, shared, options):
    """Solves the continuous relaxation of the model PyPSA writes."""
    start = time.perf_counter()
    n.optimize.create_model(linearized_unit_commitment=False)
    tie(n, n.snapshots, shared)
    model = n.model.to_gurobipy().relax()
    for key, value in options.items():
        model.setParam(key, value)
    model.optimize()
    wall = time.perf_counter() - start
    value = model.ObjVal + float(getattr(n, "objective_constant", 0.0) or 0.0)
    print(f"[status  ] relaxation {model.Status}")
    print(f"[value   ] {value:.10e}")
    print(f"[time    ] solver {model.Runtime:.2f} s, whole optimize {wall:.2f} s")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "tuc_u20_t48_s3_b1"
    solver = sys.argv[2] if len(sys.argv) > 2 else "gurobi"
    options = {}
    relax = "relax" in sys.argv[3:]
    for item in (a for a in sys.argv[3:] if a != "relax"):
        key, value = item.split("=", 1)
        try:
            options[key] = float(value) if "." in value or "e" in value \
                           else int(value)
        except ValueError:
            options[key] = value

    stochastic = pypsa.Network(str(DATA / f"{name}_flat.nc"))
    n, shared = build(stochastic)
    print(f"[instance] {name}: {len(stochastic.scenarios)} scenarios, "
          f"{int(n.generators.committable.sum())} committable copies, "
          f"{len(shared)} first-stage capacities tied")

    if relax:
        solve_relaxation(n, shared, options)
        return

    start = time.perf_counter()
    status = n.optimize(solver_name=solver, solver_options=options,
                        linearized_unit_commitment=False,
                        extra_functionality=lambda net, sns: tie(net, sns,
                                                                 shared))
    wall = time.perf_counter() - start

    solved = n.model.solver_model
    runtime = getattr(solved, "Runtime", float("nan"))
    bound = getattr(solved, "ObjBound", float("nan"))
    value = float(n.objective + n.objective_constant) \
        if n.objective is not None else float("nan")
    print(f"[status  ] {status}")
    print(f"[value   ] {value:.10e}")
    print(f"[bound   ] {bound:.10e}")
    print(f"[time    ] solver {runtime:.2f} s, whole optimize {wall:.2f} s")


if __name__ == "__main__":
    main()
