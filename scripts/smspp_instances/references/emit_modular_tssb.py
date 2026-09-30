"""Turn a network of gen_modular_tssb.py into a TwoStageStochasticBlock.

    python emit_modular_tssb.py mod_t168_s50_b1 [form] [outer]

The same network can be written in several forms, which SMS++ then solves in
different ways, and `form` chooses among them:

- `ucblock` (default): the design is a Variable of each unit, integer for the
  modular assets (the number of modules), replicated in every scenario and
  tied by the non-anticipativity Constraint; this is the extensive form, which
  a :MILPSolver solves as it is, a LagrangianDualSolver decomposes by
  scenario, and BendersDecompositionSolver takes in its Benders form;
- `design_cost_outside`: the same, with the cost of the design stated once
  outside the units, which is what a generic Benders solver reads the sign of
  its cuts from;
- `investment_outside`: the design stated once, in an InvestmentBlock over the
  whole stochastic Block, i.e., the ad hoc Benders form; the design of an
  InvestmentBlock is a capacity, so the modules are relaxed to a continuous
  capacity in this form;
- `mssb_ucblock` and `mssb_investment_outside`: the forms `ucblock` and
  `investment_outside` of a MultiStageStochasticBlock, whose scenarios are
  grouped, in their order, into `outer` outer realizations of the same size;
  the only here-and-now Variable being the design, the tree has the same
  extensive form as the flat network;
- `det_ucblock` and `det_investment`: the single scenario of the network as a
  deterministic capacity expansion, with the design in the units of the
  UCBlock or in an InvestmentBlock over it.

A name ending in `c` is the network of the name without it with the modules
turned off, i.e., with a continuous design, and is written next to it the
first time it is asked for. The file is written as
`output/modular_tssb/smspp/smspp_<name>_<form>.nc4`, or
`smspp_<name>_o<outer>_<form>.nc4` for a tree.
"""

import os
import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "output" / "modular_tssb"
sys.path.insert(0, str(HERE.parent))
from _pypsa2smspp import TEST  # noqa: E402
os.chdir(TEST)

import pypsa
from pypsa2smspp.transformation import Transformation

FORMS = ("ucblock", "design_cost_outside", "investment_outside",
         "mssb_ucblock", "mssb_investment_outside",
         "det_ucblock", "det_investment")

name = sys.argv[1] if len(sys.argv) > 1 else "mod_t168_s20_b1"
form = sys.argv[2] if len(sys.argv) > 2 else "ucblock"
outer = int(sys.argv[3]) if len(sys.argv) > 3 else 0
if form not in FORMS:
    raise SystemExit(f"form must be one of {FORMS}")

WORK = DATA / "smspp"
WORK.mkdir(parents=True, exist_ok=True)

flat = DATA / f"{name}_flat.nc"
if not flat.exists() and name.endswith("c"):
    n = pypsa.Network(str(DATA / f"{name[:-1]}_flat.nc"))
    for frame in (n.generators, n.storage_units):
        frame["p_nom_mod"] = 0.0
    n.export_to_netcdf(str(flat))
n = pypsa.Network(str(flat))
investment = form.endswith("investment_outside") or form == "det_investment"
if investment:
    # the InvestmentBlock has a continuous design: the modules are relaxed
    for frame in (n.generators, n.storage_units):
        frame["p_nom_mod"] = 0.0

stochastic = {
    "stochastic_type": "tssb",
    "parameters": ["demand", "renewable_maxpower"],
    "design_cost_outside": form == "design_cost_outside",
    # the cost stated outside the units is stated in an InvestmentBlock
    # above them, which the converter writes when either form is asked
    "investment_outside": investment or form == "design_cost_outside",
    }
tag = f"{name}_{form}"
if form.startswith("det"):
    n = n.get_scenario(list(n.scenarios)[0])
    stochastic = None
elif form.startswith("mssb"):
    weight = n.scenario_weightings["weight"]
    scenarios = list(weight.index)
    if outer < 1 or len(scenarios) % outer:
        raise SystemExit(f"{len(scenarios)} scenarios do not split into "
                         f"{outer} outer realizations")
    size = len(scenarios) // outer
    groups = {}
    for g in range(outer):
        chunk = scenarios[g * size:(g + 1) * size]
        p = float(weight[chunk].sum())
        groups[f"o{g}"] = {"probability": p,
                           "scenarios": {k: float(weight[k]) / p
                                         for k in chunk}}
    stochastic["stochastic_type"] = "mssb"
    stochastic["tree"] = {"groups": groups}
    tag = f"{name}_o{outer}_{form}"

t = Transformation(
    name=tag,
    configfile="TSSBlock/TSSBSCfg.txt",
    capacity_expansion_ucblock=not investment,
    intermittent_carriers=["solar", "wind"],
    workdir=str(WORK),
    stochastic_parameters=stochastic,
    overwrite=True,
    fp_temp="smspp_{name}_temp.nc",
)
t.create_model(n, verbose=False)
target = WORK / f"smspp_{tag}.nc4"
t.sms_network.to_netcdf(str(target), force=True)
print("[written]", target)
