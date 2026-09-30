"""Two-stage instances whose first stage builds whole modules, i.e. the family
on which a Benders decomposition has something to say.

A Benders decomposition pays when the first stage is integer and the second
one is a linear program repeated over many scenarios: the deterministic
equivalent is then a MILP whose every node is the whole stochastic linear
program, while the master of the decomposition only carries the integer
variables and the scenarios are solved apart. Here the first stage chooses how
many modules of solar and wind to build on each bus (`p_nom_mod`, so that
PyPSA writes an integer number of modules), the fleet already in place is a
set of thermal units dispatched without commitment and a storage, and the
uncertainty is the demand together with the availability of the renewables:

    python gen_modular_tssb.py --scenarios 50 --snapshots 168 --buses 1

It writes `<name>_flat.nc`, the PyPSA network carrying the scenario axis,
which PyPSA optimizes as it is (`solve_flat.py`) and which the converter turns
into a TwoStageStochasticBlock.
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "output" / "modular_tssb"

# the fleet in place, in merit order: cost per MWh and share of the peak
THERMAL = (("coal", 30.0, 0.35), ("ccgt", 55.0, 0.30), ("ocgt", 95.0, 0.20))

# what the first stage can build: capital cost per MW over the horizon of a
# week (an annuity cut to the horizon, so that building pays for itself), and
# the size of a module as a share of the peak
MODULAR = (
    # name      capital  module  max modules
    ("solar", 3000.0, 0.05, 20),
    ("wind", 3500.0, 0.05, 20),
    )
# name, capital cost, module, maximum number of modules, hours
STORAGE = ("battery", 3000.0, 0.04, 10, 4.0)

SLACK_COST = 3000.0


def load_profile(number_snapshots, rng):
    hour = np.arange(number_snapshots) % 24
    daily = (0.78
             + 0.13 * np.exp(-0.5 * ((hour - 9.0) / 2.5) ** 2)
             + 0.22 * np.exp(-0.5 * ((hour - 19.0) / 2.0) ** 2))
    weekly = 1.0 - 0.08 * (((np.arange(number_snapshots) // 24) % 7) >= 5)
    noise = 1.0 + 0.02 * rng.standard_normal(number_snapshots)
    return daily * weekly * noise


def solar_profile(number_snapshots):
    hour = np.arange(number_snapshots) % 24
    return np.clip(np.sin(np.pi * (hour - 6.0) / 12.0), 0.0, None)


def wind_profile(number_snapshots, rng):
    steps = rng.standard_normal(number_snapshots).cumsum()
    steps = steps / (np.abs(steps).max() + 1e-9)
    return np.clip(0.45 + 0.35 * steps, 0.02, 0.95)


def build(args):
    rng = np.random.default_rng(args.seed)
    snapshots = pd.RangeIndex(args.snapshots)
    peak = args.peak_load

    n = pypsa.Network()
    n.set_snapshots(snapshots)
    for carrier in [t[0] for t in THERMAL] + [m[0] for m in MODULAR] + \
                   [STORAGE[0], "slack"]:
        n.add("Carrier", carrier)

    for bus in range(args.buses):
        name = f"bus{bus}"
        n.add("Bus", name)
        if bus > 0:
            n.add("Link", f"link{bus - 1}", bus0=f"bus{bus - 1}", bus1=name,
                  p_nom=args.link_capacity * peak, p_min_pu=-1.0)

    for bus in range(args.buses):
        name = f"bus{bus}"
        for carrier, cost, share in THERMAL:
            n.add("Generator", f"{name} {carrier}", bus=name, carrier=carrier,
                  p_nom=share * peak / args.buses,
                  marginal_cost=cost * rng.uniform(0.95, 1.05))
        for carrier, capital, module, most in MODULAR:
            module = args.module_share or module
            most = args.max_modules or most
            size = module * peak / args.buses
            n.add("Generator", f"{name} {carrier}", bus=name, carrier=carrier,
                  p_nom=0.0, p_nom_extendable=True, p_nom_mod=size,
                  p_nom_max=most * size,
                  capital_cost=capital * args.capital_scale,
                  marginal_cost=0.0)
        carrier, capital, module, most, hours = STORAGE
        size = module * peak / args.buses
        # the storage is in place, as the thermal fleet: the first stage
        # decides the renewables alone
        n.add("StorageUnit", f"{name} {carrier}", bus=name, carrier=carrier,
              p_nom=most * size / 2, max_hours=hours,
              efficiency_store=0.95, efficiency_dispatch=0.95,
              cyclic_state_of_charge=True)
        n.add("Generator", f"{name} slack", bus=name, carrier="slack",
              p_nom=peak, marginal_cost=SLACK_COST)
        n.add("Load", f"{name} load", bus=name)

    share = np.array([1.0 + 0.15 * bus for bus in range(args.buses)])
    share /= share.sum()
    shape = load_profile(args.snapshots, rng)
    base_solar = solar_profile(args.snapshots)
    base_wind = wind_profile(args.snapshots, rng)

    # the scenarios: a demand level and a renewable year drawn independently,
    # so that the number of scenarios is a free parameter
    names = [f"s{index}" for index in range(args.scenarios)]
    demand = rng.uniform(0.90, 1.12, args.scenarios)
    availability = rng.uniform(0.70, 1.20, args.scenarios)
    noise = rng.normal(1.0, 0.05, (args.scenarios, args.snapshots))
    n.set_scenarios({name: 1.0 / args.scenarios for name in names})
    for index, scenario in enumerate(names):
        for bus in range(args.buses):
            n.loads_t.p_set[scenario, f"bus{bus} load"] = \
                shape * peak * share[bus] * demand[index] * noise[index]
            n.generators_t.p_max_pu[scenario, f"bus{bus} solar"] = \
                np.clip(base_solar * availability[index], 0.0, 1.0)
            n.generators_t.p_max_pu[scenario, f"bus{bus} wind"] = \
                np.clip(base_wind * availability[index] * noise[index][::-1],
                        0.0, 1.0)
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=int, default=20)
    parser.add_argument("--snapshots", type=int, default=168)
    parser.add_argument("--buses", type=int, default=1)
    parser.add_argument("--peak-load", type=float, default=10000.0)
    parser.add_argument("--link-capacity", type=float, default=0.10)
    parser.add_argument("--module-share", type=float, default=None,
                        help="size of a module as a share of the peak of a "
                             "bus (default: that of each technology)")
    parser.add_argument("--max-modules", type=int, default=None,
                        help="modules that can be built per technology and "
                             "bus (default: that of each technology)")
    parser.add_argument("--capital-scale", type=float, default=1.0,
                        help="factor on the capital costs")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    name = args.name or (f"mod_t{args.snapshots}_s{args.scenarios}"
                         f"_b{args.buses}")
    DATA.mkdir(parents=True, exist_ok=True)
    n = build(args)
    n.export_to_netcdf(str(DATA / f"{name}_flat.nc"))
    print(f"{name}: {args.scenarios} scenarios, {args.snapshots} snapshots, "
          f"{args.buses} buses")


if __name__ == "__main__":
    main()
