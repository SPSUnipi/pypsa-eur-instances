# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Build a stochastic electricity network with the generator of plan4res/resilient.

The generator is the notebook ``CreateElecNetwork.ipynb`` of the repository
retrieved by ``retrieve_resilient_generator``: a network of the European power
system in 2030 (ENVIS NECPEssentials), whose demand, renewable availability and
inflows come in scenarios. The code cells of the notebook that build the
deterministic network are run as they are, with the settings of the case written
into a settings file of their own, and the network is then made stochastic with
the first ``scenarios`` scenarios of the generator, all equally likely, on the
data that ``stochastic`` lists: the demand, the availability of the renewable
generators, or both.

With ``days`` only those days of the horizon are kept, e.g., the first day of
each month of a year, which the generator cannot build by itself since it takes
a continuous interval: the whole horizon is built, the hours of the other days
are dropped, and each hour kept weighs as many hours as the horizon has days
over the days kept, so that the operating costs stay on the scale of the yearly
investment costs. The days kept follow one another, so that a storage passes
from the end of a day to the beginning of the next one kept.

The inflows of the hydro reservoirs stay those of the deterministic network:
the SMS++ conversion of a stochastic network has no stochastic inflows, and the
two sides of a comparison have to solve the same problem.

Relevant settings
-----------------

.. code:: yaml

    resilient:
      cases:
        <case>:
          begin:        # first day of the horizon, dd/mm/yyyy
          end:          # last day of the horizon, dd/mm/yyyy
          scenarios:    # number of scenarios, at most 105
          extendable:   # capacity expansion of the generators
          committable:  # unit commitment of the thermal generators
          stochastic:   # what the scenarios change: [demand, renewables]
          days:         # optional, the days of the horizon kept, dd/mm/yyyy

Outputs
-------

- ``resources/networks/resilient_{case}.nc``: the stochastic network
"""

import json
import logging
import os
import sys

import pandas as pd
import yaml

from scripts._helpers import configure_logging

logger = logging.getLogger(__name__)

# the code cell of the notebook that exports the deterministic network: the
# cells before it build the network, those from it on convert and solve it
EXPORT_CELL = 'npypsa.export_to_netcdf("pypsaNetwork.nc")'


def notebook_source(notebook: str, settings: str) -> str:
    """The code cells of the notebook up to the export of the network, without
    the IPython magics, reading ``settings`` as their settings file."""
    cells = json.load(open(notebook))["cells"]
    lines = []
    for cell in cells:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        if EXPORT_CELL in source:
            break
        lines += [
            line
            for line in source.splitlines()
            if not line.lstrip().startswith(("%", "!"))
        ]
    else:
        raise RuntimeError(f"no cell of {notebook} exports the network")
    return "\n".join(lines).replace("settings_createElecNetwork.yml", settings)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_resilient_network", case="w1_s21")
    configure_logging(snakemake)

    case = snakemake.params.case
    generator = os.path.abspath(snakemake.input.generator)
    output = os.path.abspath(snakemake.output.network)

    # the settings of the case, next to those of the generator
    settings_dir = os.path.join(generator, "settings")
    cfg = yaml.safe_load(
        open(os.path.join(settings_dir, "settings_createElecNetwork.yml"))
    )
    cfg["Calendar"]["BeginDataset"] = case["begin"] + "  00:00:00"
    cfg["Calendar"]["EndDataset"] = case["end"] + "  23:00:00"
    cfg["Parameters"]["extendable"] = bool(case.get("extendable", True))
    cfg["Parameters"]["committable"] = bool(case.get("committable", False))
    settings = f"settings_{snakemake.wildcards.case}.yml"
    with open(os.path.join(settings_dir, settings), "w") as f:
        yaml.safe_dump(cfg, f)

    # the deterministic network, built by the notebook in its own directory
    source = notebook_source(
        os.path.join(generator, "CreateElecNetwork.ipynb"), settings
    )
    cwd = os.getcwd()
    os.chdir(generator)
    sys.path.insert(0, generator)
    g = {}
    exec(compile(source, "CreateElecNetwork.ipynb", "exec"), g)
    os.chdir(cwd)
    n = g["npypsa"].copy()

    # the stochastic network: the first scenarios of the generator
    scenarios = g["ListScenarios"][: int(case["scenarios"])]
    n.set_scenarios({sc: 1 / len(scenarios) for sc in scenarios})

    stochastic = case.get("stochastic", ["demand", "renewables"])
    unknown = set(stochastic) - {"demand", "renewables"}
    if unknown:
        raise ValueError(f"unknown stochastic data {sorted(unknown)}")

    if "renewables" in stochastic:
        zones = g["npypsa"].buses.index
        for sc in scenarios:
            for (name, zone), row in g["RES"].iterrows():
                if zone in zones and row["MaxPower"] > 0:
                    n.generators_t.p_max_pu.loc[:, (sc, f"{name}_{zone}")] = g[
                        "RESScenarios"
                    ].loc[(name, zone)][sc]

    if "demand" in stochastic:
        buses = g["npypsa"].buses.index
        loads = [f"Load_{b}" for b in buses]
        p_set = pd.DataFrame(
            index=g["DeterministicTimeSeries"]["One"].index,
            columns=pd.MultiIndex.from_product(
                [n.scenarios, loads], names=["scenario", "name"]
            ),
        )
        for b in buses:
            for sc in scenarios:
                p_set.loc[:, (sc, f"Load_{b}")] = g["DemandScenarios"][b][sc]
        n.c.loads.dynamic.p_set = p_set

    if case.get("days"):
        kept = pd.to_datetime(case["days"], dayfirst=True)
        day = n.snapshots.normalize()
        missing = kept.difference(day.unique())
        if not missing.empty:
            raise ValueError(
                f"days {[d.strftime('%d/%m/%Y') for d in missing]} are not in "
                f"the horizon {case['begin']} - {case['end']}"
            )
        weight = day.unique().size / kept.unique().size
        n.set_snapshots(n.snapshots[day.isin(kept)])
        n.snapshot_weightings.loc[:, :] = n.snapshot_weightings * weight

    os.makedirs(os.path.dirname(output), exist_ok=True)
    n.export_to_netcdf(output)
    logger.info(
        f"Written {output}: {len(n.snapshots)} snapshots, {len(scenarios)} scenarios"
    )
