# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import yaml


def _stoch_cfg():
    """Return stochastic scenario config, if present."""
    return config.get("stochastic_scenarios", {}) or {}


def _stoch_enabled():
    """Whether stochastic network generation is enabled."""
    return bool(_stoch_cfg().get("enable", False))


def _stoch_file():
    """External stochastic scenario YAML file."""
    return _stoch_cfg().get("file", None)


def _stoch_export_expected():
    """Whether to export the probability-weighted expected deterministic view."""
    return bool((_stoch_cfg().get("export", {}) or {}).get("expected", True))


def _stoch_export_scenarios():
    """Whether to export deterministic views for each stochastic scenario."""
    return bool((_stoch_cfg().get("export", {}) or {}).get("scenarios", False))


def _stoch_scenario_names():
    """Read stochastic scenario names from the external YAML file at DAG construction time."""
    p = _stoch_file()
    if not p:
        return []

    p = Path(p)
    if not p.exists():
        raise FileNotFoundError(f"Stochastic scenarios file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    scenarios = data.get("scenarios", data) or {}
    if not isinstance(scenarios, dict):
        raise TypeError(f"Invalid stochastic scenario file format: {p}")

    return list(scenarios.keys())


STOCH_SCENARIOS = _stoch_scenario_names() if _stoch_enabled() else []


def input_sector_network(w):
    """Use the stochasticified pre-solve network only when stochastic mode is enabled."""
    if _stoch_enabled():
        return resources(
            "networks/base_s_stoch_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
        ).format(**dict(w))

    return resources(
        "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
    ).format(**dict(w))


if _stoch_enabled():

    rule stochasticify_sector_network:
        input:
            network=resources(
                "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
            ),
        output:
            network=resources(
                "networks/base_s_stoch_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
            ),
            config=RESULTS
            + "configs/config.base_s_stoch_{clusters}_{opts}_{sector_opts}_{planning_horizons}.yaml",
        log:
            python=RESULTS
            + "logs/stochasticify/base_s_stoch_{clusters}_{opts}_{sector_opts}_{planning_horizons}_python.log",
        benchmark:
            (
                RESULTS
                + "benchmarks/stochasticify_sector_network/base_s_stoch_{clusters}_{opts}_{sector_opts}_{planning_horizons}"
            )
        shadow:
            shadow_config
        threads: 1
        resources:
            mem_mb=config_provider("solving", "mem_mb"),
            runtime=config_provider("solving", "runtime", default="1h"),
        params:
            solving=config_provider("solving"),
            foresight=config_provider("foresight"),
            co2_sequestration_potential=config_provider(
                "sector", "co2_sequestration_potential", default=200
            ),
            stochastic_scenarios=config_provider(
                "stochastic_scenarios", default={"enable": False}
            ),
        message:
            "Creating stochastic pre-solve sector-coupled network"
        script:
            scripts("stochasticify_network.py")


rule solve_sector_network:
    input:
        network=input_sector_network,
    output:
        network=RESULTS
        + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc",
        config=RESULTS
        + "configs/config.base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.yaml",
        model=(
            RESULTS
            + "models/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
            if config["solving"]["options"]["store_model"]
            else []
        ),
    log:
        solver=RESULTS
        + "logs/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_solver.log",
        memory=RESULTS
        + "logs/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_memory.log",
        python=RESULTS
        + "logs/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_python.log",
    benchmark:
        (
            RESULTS
            + "benchmarks/solve_sector_network/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}"
        )
    shadow:
        shadow_config
    threads: solver_threads
    resources:
        mem_mb=config_provider("solving", "mem_mb"),
        runtime=config_provider("solving", "runtime", default="6h"),
    params:
        solving=config_provider("solving"),
        foresight=config_provider("foresight"),
        co2_sequestration_potential=config_provider(
            "sector", "co2_sequestration_potential", default=200
        ),
        custom_extra_functionality=input_custom_extra_functionality,
    message:
        "Solving sector-coupled network with overnight investment optimization for {wildcards.clusters} clusters, {wildcards.planning_horizons} planning horizons, {wildcards.opts} electric options and {wildcards.sector_opts} sector options"
    script:
        scripts("solve_network.py")


if _stoch_enabled() and _stoch_export_expected():

    rule export_stochastic_expected:
        input:
            network=RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc",
        output:
            expected=RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__exp.nc",
        log:
            python=RESULTS
            + "logs/export_stochastic_views/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__exp.log",
        benchmark:
            (
                RESULTS
                + "benchmarks/export_stochastic_views/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__exp"
            )
        threads: 1
        resources:
            mem_mb=8000,
        params:
            scenarios_file=lambda w: _stoch_file(),
            mode="expected",
        message:
            "Exporting expected deterministic view from stochastic solution"
        script:
            scripts("export_stochastic_views.py")


if _stoch_enabled() and _stoch_export_scenarios():

    rule export_stochastic_scenario:
        input:
            network=RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc",
        output:
            scenario=RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__sc-{stoch_scenario}.nc",
        log:
            python=RESULTS
            + "logs/export_stochastic_views/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__sc-{stoch_scenario}.log",
        benchmark:
            (
                RESULTS
                + "benchmarks/export_stochastic_views/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__sc-{stoch_scenario}"
            )
        threads: 1
        resources:
            mem_mb=8000,
        params:
            scenarios_file=lambda w: _stoch_file(),
            mode="scenario",
            scenario=lambda w: w.stoch_scenario,
        wildcard_constraints:
            stoch_scenario="|".join(STOCH_SCENARIOS) if STOCH_SCENARIOS else r"[^/]+",
        message:
            "Exporting deterministic view for stochastic scenario {wildcards.stoch_scenario}"
        script:
            scripts("export_stochastic_views.py")