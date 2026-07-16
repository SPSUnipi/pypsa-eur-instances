# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT


localrules:
    all,
    cluster_networks,
    prepare_elec_networks,
    prepare_sector_networks,
    solve_elec_networks,
    compare_solver_elec_outputs,
    compare_solver_sector_outputs,
    collect_solve_benchmarks,
    solve_sector_networks,


rule process_costs:
    input:
        lambda w: (
            expand(
                resources(
                    f"costs_{config_provider('costs', 'year')(w)}_processed.csv"
                ),
                run=config["run"]["name"],
            )
            if config_provider("foresight")(w) == "overnight"
            else expand(
                resources("costs_{planning_horizons}_processed.csv"),
                **config["scenario"],
                run=config["run"]["name"],
            )
        ),


rule cluster_networks:
    input:
        expand(
            resources("networks/base_s_{clusters}.nc"),
            **config["scenario"],
            run=config["run"]["name"],
        ),
    message:
        "Collecting clustered network files"


rule prepare_elec_networks:
    input:
        expand(
            resources("networks/base_s_{clusters}_elec_{opts}.nc"),
            **config["scenario"],
            run=config["run"]["name"],
        ),
    message:
        "Collecting prepared electricity network files"


rule prepare_sector_networks:
    input:
        expand(
            resources(
                "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
            ),
            **config["scenario"],
            run=config["run"]["name"],
        ),
    message:
        "Collecting prepared sector-coupled network files"


rule solve_elec_networks:
    input:
        expand(
            RESULTS + "networks/base_s_{clusters}_elec_{opts}_{solver}.nc",
            **config["scenario"],
            run=config["run"]["name"],
            solver=solver_names(),
        ),
    message:
        "Collecting solved electricity network files"


def electricity_solver_comparison_paths(w):
    return expand(
        RESULTS + "csvs/solver_comparison/summary_s_{clusters}_elec_{opts}.csv",
        clusters=config_provider("scenario", "clusters")(w),
        opts=config_provider("scenario", "opts")(w),
        run=config["run"]["name"],
    )


def sector_solver_comparison_paths(w):
    if config_provider("foresight")(w) == "perfect":
        return expand(
            RESULTS
            + "csvs/solver_comparison/summary_s_{clusters}_{opts}_{sector_opts}_brownfield_all_years.csv",
            clusters=config_provider("scenario", "clusters")(w),
            opts=config_provider("scenario", "opts")(w),
            sector_opts=config_provider("scenario", "sector_opts")(w),
            run=config["run"]["name"],
        )

    return expand(
        RESULTS
        + "csvs/solver_comparison/summary_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.csv",
        clusters=config_provider("scenario", "clusters")(w),
        opts=config_provider("scenario", "opts")(w),
        sector_opts=config_provider("scenario", "sector_opts")(w),
        planning_horizons=config_provider("scenario", "planning_horizons")(w),
        run=config["run"]["name"],
    )


rule compare_solver_elec_outputs:
    input:
        electricity_solver_comparison_paths,
    message:
        "Collecting electricity solver comparison files"


rule compare_solver_sector_outputs:
    input:
        sector_solver_comparison_paths,
    message:
        "Collecting sector-coupled solver comparison files"


def benchmark_collection_root():
    prefix = config["run"].get("prefix", "").strip("/")
    if prefix:
        return f"results/{prefix}"
    return "results"


def collected_solve_benchmark_path():
    return benchmark_collection_root() + "/csvs/solve_benchmarks.csv"


rule collect_solve_benchmarks:
    output:
        benchmarks=collected_solve_benchmark_path(),
    log:
        benchmark_collection_root() + "/logs/collect_solve_benchmarks.log",
    benchmark:
        benchmark_collection_root() + "/benchmarks/collect_solve_benchmarks"
    threads: 1
    resources:
        mem_mb=1000,
    params:
        benchmark_root=benchmark_collection_root(),
        solver_specs=solver_run_specs,
    message:
        "Collecting solve benchmark files below {params.benchmark_root}"
    script:
        scripts("collect_solve_benchmarks.py")


rule solve_sector_networks:
    input:
        expand(
            RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_{solver}.nc",
            **config["scenario"],
            run=config["run"]["name"],
            solver=solver_names(),
        ),
    message:
        "Collecting solved sector-coupled network files"


rule solve_sector_networks_perfect:
    input:
        expand(
            RESULTS
            + "maps/static/base_s_{clusters}_{opts}_{sector_opts}-costs-all_{planning_horizons}.pdf",
            **config["scenario"],
            run=config["run"]["name"],
        ),
    message:
        "Collecting solved sector-coupled network files with perfect foresight"

rule solve_stochastic_networks:
    input:
        expand(
            RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}__sc-{stoch_scenario}.nc",
            **config["scenario"],
            stoch_scenario=STOCHASTIC_SCENARIOS,
            run=config["run"]["name"],
        ),
    message:
        "Solving stochastic network problems"

rule solve_stochastic_average_networks:
    input:
        expand(
            RESULTS
            + "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc",
            **config["scenario"],
            stoch_scenario=STOCHASTIC_SCENARIOS,
            run=config["run"]["name"],
        ),
    message:
        "Solving stochastic network problems"


def balance_map_paths(kind, w):
    """
    kind = "static" or "interactive"
    """
    cfg_key = "balance_map" if kind == "static" else "balance_map_interactive"

    return expand(
        RESULTS
        + f"maps/{kind}/base_s_{{clusters}}_{{opts}}_{{sector_opts}}_{{planning_horizons}}_{{solver}}"
        f"-balance_map_{{carrier}}.{'pdf'if kind== 'static' else 'html'}",
        **config["scenario"],
        run=config["run"]["name"],
        solver=solver_names(),
        carrier=config_provider("plotting", cfg_key, "bus_carriers")(w),
    )


rule plot_balance_maps:
    input:
        static=lambda w: balance_map_paths("static", w),
        interactive=lambda w: balance_map_paths("interactive", w),
    message:
        "Plotting energy balance maps"


rule plot_balance_maps_static:
    input:
        lambda w: balance_map_paths("static", w),


rule plot_balance_maps_interactive:
    input:
        lambda w: balance_map_paths("interactive", w),


rule plot_power_networks_clustered:
    input:
        expand(
            resources("maps/power-network-s-{clusters}.pdf"),
            **config["scenario"],
            run=config["run"]["name"],
        ),
    message:
        "Plotting clustered power network topology"
