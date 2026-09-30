# -*- coding: utf-8 -*-
"""
Generator of the UCBlock instances with nuclear units.

A single-bus network whose nuclear generator follows a daily load is written
once for each set of operating rules: as a ThermalUnitBlock, as a
NuclearUnitBlock whose rules do not bind, and then with one family of rules
added at a time, up to the whole `constants.nuclear_rules_default`. PyPSA has
no such rules, so its optimum is a relaxation of all but the first two, and
the reference value of each instance is the optimum of SMS++ itself, proven
optimal by the MILP solver; the two objectives are printed side by side, the
PyPSA one being a lower bound of the others.

The instance of a nuclear unit with the rules is a hard MILP, hence the
network has one nuclear unit over 24 snapshots: two units over 48 do not
close in 600 s, with Gurobi or with HiGHS.

Usage:
    python nuclear_generator.py <output directory>
"""

import sys
from pathlib import Path

import numpy as np
import pypsa

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pypsa2smspp.constants import nuclear_rules_default
from pypsa2smspp.transformation import Transformation


# =============================================================================
# INPUT PARAMETERS
# =============================================================================

SNAPSHOTS = 24

# the rules of nuclear_rules_default switched off, the modulation ramps being
# the full thermal ones: a NuclearUnitBlock that behaves as a ThermalUnitBlock
NON_BINDING = {key: None for key in nuclear_rules_default}
NON_BINDING.update(modulation_ramp_fraction=1.0, modulation_time=2.0)


def with_rules(*names):
    """The non-binding rules, with the named ones as nuclear_rules_default has
    them."""
    merged = dict(NON_BINDING)
    merged.update({name: nuclear_rules_default[name] for name in names})
    return merged


# name: the rules of the nuclear units, None for ThermalUnitBlocks
VARIANTS = {
    # the thermal unit and the nuclear one whose rules do not bind: the same
    # problem, and the only two whose optimum is that of PyPSA
    "tub": None,
    "free": NON_BINDING,
    # the modulations, then the daily limits on them and on the start-ups,
    # then the three bands of the output, then the deep decreases, then the
    # whole set of the rules
    "modulation": with_rules("modulation_ramp_fraction", "modulation_time",
                             "max_modulation_length"),
    "daily": with_rules("modulation_ramp_fraction", "modulation_time",
                        "max_modulation_length", "day_length",
                        "modulations_per_day", "start_ups_per_day"),
    "bands": with_rules("modulation_ramp_fraction", "modulation_time",
                        "power_bands"),
    "deep": with_rules("modulation_ramp_fraction", "modulation_time",
                       "day_length", "deep_decrease_threshold",
                       "deep_decrease_gradient", "deep_decreases_per_day",
                       "deep_decrease_cost"),
    "rules": True,
}


def nuclear_network():
    """
    One bus, one committable nuclear unit that starts on, a peaking unit that
    starts off, and a load shedding generator; the load follows a daily cycle
    whose peak is at the first snapshot, and is low enough that the unit has
    to modulate its output to follow it.
    """
    n = pypsa.Network()
    n.set_snapshots(range(SNAPSHOTS))
    n.add("Bus", "bus")
    n.add("Carrier", ["nuclear", "ocgt", "slack"])

    t = np.arange(SNAPSHOTS)
    n.add("Load", "load", bus="bus",
          p_set=0.35 * (3000.0 + 1200.0 * np.cos(2.0 * np.pi * t / 24.0)))

    n.add("Generator", "nuclear0", bus="bus", carrier="nuclear", p_nom=1300.0,
          marginal_cost=9.0, committable=True, p_min_pu=0.5, ramp_limit_up=0.3,
          ramp_limit_down=0.3, ramp_limit_start_up=0.5,
          ramp_limit_shut_down=0.5, min_up_time=4, min_down_time=4,
          start_up_cost=250.0 * 1300.0, up_time_before=10)

    n.add("Generator", "ocgt", bus="bus", carrier="ocgt", p_nom=2000.0,
          marginal_cost=80.0, committable=True, p_min_pu=0.2,
          start_up_cost=20000.0, up_time_before=0, down_time_before=10)

    n.add("Generator", "shedding", bus="bus", carrier="slack", p_nom=1e5,
          marginal_cost=3000.0)

    return n


def generate(name, rules, out_dir):
    """Write the instance of one variant and return its reference objective."""
    reference = nuclear_network()
    reference.optimize(solver_name="highs")
    obj_pypsa = float(reference.objective +
                      getattr(reference, "objective_constant", 0.0))

    file_name = f"smspp_nuclear_{name}"
    transformation = Transformation(
        capacity_expansion_ucblock=True,
        enable_thermal_units=True,
        intermittent_carriers=[],
        nuclear_units=None if rules is None else {"nuclear": rules},
        workdir=out_dir,
        name=file_name,
        overwrite=True,
        fp_temp="{name}.nc",
        fp_log="{name}_log.txt",
        fp_solution="{name}_solution.nc",
        configfile="auto",
    )
    transformation.create_model(nuclear_network(), verbose=False)
    transformation.optimize(verbose=False)

    status = str(transformation.result.status)
    if "Success" not in status:
        raise RuntimeError(f"{file_name}: SMS++ did not solve it ({status}), "
                           "so its optimum cannot be the reference value")

    return (f"{file_name}.nc", obj_pypsa,
            float(transformation.result.objective_value))


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rules in VARIANTS.items():
        file_name, obj_pypsa, obj_smspp = generate(name, rules, out_dir)
        print(f"REF_OBJ[{file_name}]={obj_smspp:.9e}"
              f"  # PyPSA {obj_pypsa:.9e}", flush=True)
