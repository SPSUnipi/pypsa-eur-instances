"""The deterministic equivalent of a modular instance, solved by PyPSA.

The network written by gen_modular_tssb.py has no committable unit, so PyPSA
optimizes its scenario axis as it is: the capacities are one decision for all
the scenarios, the number of modules is integer, and the dispatch is per
scenario. This is the monolithic MILP against which a decomposition in SMS++
is compared:

    python solve_modular_tssb.py mod_t168_s50_b1 [gurobi] [Key=value ...]

The options after the solver name are passed to it as they are.
"""

import sys
import time
import warnings
from pathlib import Path

import pypsa

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "output" / "modular_tssb"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "mod_t168_s20_b1"
    solver = sys.argv[2] if len(sys.argv) > 2 else "gurobi"
    options = {}
    for item in sys.argv[3:]:
        key, value = item.split("=", 1)
        try:
            options[key] = float(value) if "." in value or "e" in value \
                           else int(value)
        except ValueError:
            options[key] = value

    n = pypsa.Network(str(DATA / f"{name}_flat.nc"))
    start = time.perf_counter()
    status = n.optimize(solver_name=solver, solver_options=options)
    wall = time.perf_counter() - start

    solved = n.model.solver_model
    runtime = getattr(solved, "Runtime", float("nan"))
    bound = getattr(solved, "ObjBound", float("nan"))
    generators = n.generators.groupby(level=-1).first()
    storage = n.storage_units.groupby(level=-1).first()
    modules = {**(generators.p_nom_opt / generators.p_nom_mod)[
                   generators.p_nom_extendable].round(3).to_dict(),
               **(storage.p_nom_opt / storage.p_nom_mod).round(3).to_dict()}
    print(f"[status  ] {status}")
    print(f"[value   ] {float(n.objective + n.objective_constant):.10e}")
    print(f"[bound   ] {bound:.10e}")
    print(f"[time    ] solver {runtime:.2f} s, whole optimize {wall:.2f} s")
    print(f"[modules ] {modules}")


if __name__ == "__main__":
    main()
