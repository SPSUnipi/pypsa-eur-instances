# -*- coding: utf-8 -*-
"""
Generator of the SMS++ instances of the two-level scenario trees.

Each tree is the one `references/gen_resilient_tree.py` writes from a PyPSA
network, the outer stage being the climate year and the inner one the demand,
and comes with the equivalent flat network, whose objective value is the
reference of every form the tree is written in: as long as the only
here-and-now variables are the design ones, the flat network has the very same
extensive form as the tree.

Every tree is written as a MultiStageStochasticBlock, which is what the batch
`MultiStageStochasticBlock/batches/batch-pypsa` runs, and the trees that the
batch `InvestmentBlock/batches/batch-stochastic` runs are written again with
the investment stated once outside the scenarios, in an InvestmentBlock
wrapping the stochastic Block, in the two forms that batch holds: the tree
itself and its flat two-stage equivalent over the product of the scenarios.

Usage:
    python tree_instance_generator.py <MSSB output directory>
                                      <InvestmentBlock output directory>
                                      [tree ...]

with no tree, every tree of TREES is written.
"""

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _pypsa2smspp import TEST  # noqa: E402, the test networks of pypsa2smspp

import pypsa

from pypsa2smspp.transformation import Transformation

DATA = TEST / "output" / "mssb_tree"   # written by the references of pypsa2smspp
OUT = HERE / "output" / "trees"

SOLVER_NAME = "gurobi"

# the parameters the tree perturbs, i.e. the ones its nodes carry data for
PARAMETERS = ["demand", "renewable_maxpower"]

# name of the tree -> the file names of the forms it is written in: the
# MultiStageStochasticBlock one, and the ones with the investment outside,
# where "mssb" is the tree itself and "tssb" its flat equivalent
TREES = {
    "network_small_fewsectors__snap24__c3_d3_renewables": {
        "mssb": "smspp_network_small_fewsectors__snap24__c3_d3_renewables.nc",
        "investment_tssb": "smspp_stoch_tssb_c3_d3_renewables.nc",
    },
    "network_small_fewsectors__snap24__c3_d3_hydro": {
        "mssb": "smspp_network_small_fewsectors__snap24__c3_d3_hydro.nc",
    },
    "network_small_fewsectors__snap24__c3_d3_both": {
        "mssb": "smspp_network_small_fewsectors__snap24__c3_d3_both.nc",
        "investment_tssb": "smspp_stoch_tssb_c3_d3_both.nc",
        "investment_mssb": "smspp_stoch_mssb_c3_d3_both.nc",
    },
    "network_small_fewsectors__snap24__c4_d3_both": {
        "mssb": "smspp_network_small_fewsectors__snap24__c4_d3_both.nc",
    },
}


def write(network, tree, name, form, out_dir, file_name):
    """
    Writes one form of a tree, returning the file it has written.

    The forms are the three of TREES: the tree as a MultiStageStochasticBlock,
    and the tree and its flat equivalent with the investment outside.
    """
    stochastic = {"parameters": PARAMETERS}
    if form == "investment_tssb":
        stochastic["stochastic_type"] = "tssb"
        stochastic["investment_outside"] = True
    else:
        stochastic["stochastic_type"] = "mssb"
        stochastic["tree"] = {"groups": tree["groups"]}
        stochastic["investment_outside"] = ( form == "investment_mssb" )

    transformation = Transformation(
        name=f"{name}_{form}",
        configfile="TSSBlock/TSSBSCfg.txt",
        enable_thermal_units=False,
        # the design variables of the plain tree are those of the UCBlock of
        # each scenario; with the investment outside they are the ones of the
        # InvestmentBlock above it, and the UCBlock carries none
        capacity_expansion_ucblock=( form == "mssb" ),
        workdir=str(OUT),
        stochastic_parameters=stochastic,
        overwrite=True,
        fp_temp="smspp_{name}_temp.nc",
        fp_log="smspp_{name}_log.txt",
        fp_solution="smspp_{name}_solution.nc",
        pysmspp_options={"B": "TSSBCfg.txt"},
    )

    # the instance is the file the run hands to SMS++, and it is that path
    # that writes the inner Block inside each StochasticBlock: what
    # create_model() builds does not carry it, and a TwoStageStochasticBlock
    # without it cannot be read back. Whether the run then solves it is
    # another matter, the batch being what holds the instance to its
    # reference, so an answer SMS++ refuses to give is reported and no more
    value = None
    try:
        transformation.run(network.copy(), verbose=False)
        value = float(transformation.result.objective_value)
    except Exception as error:
        print(f"    [{form}] SMS++ gave no answer: {error}", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    temp = OUT / f"smspp_{name}_{form}_temp.nc"
    shutil.move(temp, out_dir / file_name)

    return out_dir / file_name, value


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1

    mssb_dir = Path(argv[1]).resolve()
    investment_dir = Path(argv[2]).resolve()
    wanted = set(argv[3:])

    OUT.mkdir(parents=True, exist_ok=True)
    mssb_refs, investment_refs = [], []

    for name, forms in TREES.items():
        if wanted and ( name not in wanted ):
            continue

        network = pypsa.Network(str(DATA / f"{name}_flat.nc"))
        tree = json.load(open(DATA / f"{name}_tree.json"))

        # the reference of every form is the objective value of the flat
        # network, which has the same extensive form as the tree
        start = time.time()
        reference = network.copy()
        reference.optimize(solver_name=SOLVER_NAME)
        obj_pypsa = float(reference.objective +
                          getattr(reference, "objective_constant", 0.0))
        print(f"{name}: PyPSA = {obj_pypsa:.9e}  "
              f"({time.time() - start:.1f} s, {len(network.scenarios)} leaves)",
              flush=True)

        for form, file_name in forms.items():
            out_dir = mssb_dir if form == "mssb" else investment_dir
            start = time.time()
            written, value = write(network, tree, name, form, out_dir,
                                   file_name)
            smspp = "no answer" if value is None else f"{value:.9e}"
            print(f"    {form}: {written.name}, SMS++ = {smspp} "
                  f"({time.time() - start:.1f} s)", flush=True)

            entry = f"REF_OBJ[{file_name}]={obj_pypsa:.9e}"
            ( mssb_refs if form == "mssb" else investment_refs ).append( entry )

    print("\n# MultiStageStochasticBlock/batches/batch-pypsa")
    print("\n".join(mssb_refs))
    print("\n# InvestmentBlock/batches/batch-stochastic")
    print("\n".join(investment_refs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
