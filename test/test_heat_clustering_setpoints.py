"""Heat aggregation must not turn unspecified dispatch into a zero setpoint."""

import numpy as np
import pypsa
import pytest

from scripts.prepare_sector_network import cluster_heat_buses


@pytest.mark.parametrize("values, expected", [([np.nan, np.nan], np.nan), ([0, np.nan], 0), ([2, 3], 5)])
def test_clustered_heat_setpoints(values, expected):
    n = pypsa.Network()
    n.add("Bus", "electricity")
    for sector, value in zip(["residential", "services"], values):
        bus = f"node {sector} rural heat"
        n.add("Bus", bus, carrier=f"{sector} rural heat")
        n.add("Link", f"node {sector} rural heater", bus0="electricity", bus1=bus,
              carrier=f"{sector} rural heater", p_set=value)
        n.add("Generator", f"node {sector} rural solar", bus=bus,
              carrier=f"{sector} rural solar", p_set=value)

    cluster_heat_buses(n)

    for table, name in [(n.links, "node rural heater"), (n.generators, "node rural solar")]:
        actual = table.loc[name, "p_set"]
        if np.isnan(expected):
            assert np.isnan(actual)
        else:
            assert actual == expected
