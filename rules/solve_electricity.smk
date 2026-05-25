# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT


rule solve_network:
    input:
        network=resources("networks/base_s_{clusters}_elec_{opts}.nc"),
    output:
        network=RESULTS + "networks/base_s_{clusters}_elec_{opts}_{solver}.nc",
        config=RESULTS + "configs/config.base_s_{clusters}_elec_{opts}_{solver}.yaml",
        model=(
            RESULTS + "models/base_s_{clusters}_elec_{opts}_{solver}.nc"
            if config["solving"]["options"]["store_model"]
            else []
        ),
    log:
        solver=normpath(
            RESULTS + "logs/solve_network/base_s_{clusters}_elec_{opts}_{solver}_solver.log"
        ),
        memory=RESULTS
        + "logs/solve_network/base_s_{clusters}_elec_{opts}_{solver}_memory.log",
        python=RESULTS
        + "logs/solve_network/base_s_{clusters}_elec_{opts}_{solver}_python.log",
    benchmark:
        (RESULTS + "benchmarks/solve_network/base_s_{clusters}_elec_{opts}_{solver}")
    shadow:
        shadow_config
    threads: solver_threads
    resources:
        mem_mb=memory,
        runtime=config_provider("solving", "runtime", default="6h"),
    params:
        solving=solving_for_solver,
        foresight=config_provider("foresight"),
        co2_sequestration_potential=config_provider(
            "sector", "co2_sequestration_potential", default=200
        ),
        custom_extra_functionality=input_custom_extra_functionality,
    message:
        "Solving electricity network optimization with {wildcards.solver} for {wildcards.clusters} clusters and {wildcards.opts} electric options"
    script:
        scripts("solve_network.py")


rule solve_operations_network:
    input:
        network=RESULTS + "networks/base_s_{clusters}_elec_{opts}_{solver}.nc",
    output:
        network=RESULTS + "networks/base_s_{clusters}_elec_{opts}_{solver}_op.nc",
    log:
        solver=normpath(
            RESULTS
            + "logs/solve_operations_network/base_s_{clusters}_elec_{opts}_{solver}_op_solver.log"
        ),
        python=RESULTS
        + "logs/solve_operations_network/base_s_{clusters}_elec_{opts}_{solver}_op_python.log",
    benchmark:
        (
            RESULTS
            + "benchmarks/solve_operations_network/base_s_{clusters}_elec_{opts}_{solver}"
        )
    shadow:
        shadow_config
    threads: 4
    resources:
        mem_mb=memory,
        runtime=config_provider("solving", "runtime", default="6h"),
    params:
        options=config_provider("solving", "options"),
        solving=solving_for_solver,
        foresight=config_provider("foresight"),
        co2_sequestration_potential=config_provider(
            "sector", "co2_sequestration_potential", default=200
        ),
        custom_extra_functionality=input_custom_extra_functionality,
    message:
        "Solving electricity network operations optimization with {wildcards.solver} for {wildcards.clusters} clusters and {wildcards.opts} electric options"
    script:
        scripts("solve_operations_network.py")


rule make_solver_comparison:
    input:
        networks=lambda w: expand(
            RESULTS + "networks/base_s_{clusters}_elec_{opts}_{solver}.nc",
            clusters=w.clusters,
            opts=w.opts,
            solver=solver_names(w),
        ),
        benchmarks=lambda w: expand(
            RESULTS + "benchmarks/solve_network/base_s_{clusters}_elec_{opts}_{solver}",
            clusters=w.clusters,
            opts=w.opts,
            solver=solver_names(w),
        ),
    output:
        summary=RESULTS
        + "csvs/solver_comparison/summary_s_{clusters}_elec_{opts}.csv",
        optimal_capacity=RESULTS
        + "csvs/solver_comparison/optimal_capacity_s_{clusters}_elec_{opts}.csv",
        energy_balance=RESULTS
        + "csvs/solver_comparison/energy_balance_s_{clusters}_elec_{opts}.csv",
        benchmarks=RESULTS
        + "csvs/solver_comparison/benchmarks_s_{clusters}_elec_{opts}.csv",
    log:
        RESULTS + "logs/make_solver_comparison/base_s_{clusters}_elec_{opts}.log",
    benchmark:
        RESULTS + "benchmarks/make_solver_comparison/base_s_{clusters}_elec_{opts}"
    threads: 1
    resources:
        mem_mb=4000,
    params:
        solver_specs=solver_run_specs,
    message:
        "Comparing solved electricity networks across configured solvers for {wildcards.clusters} clusters and {wildcards.opts} electric options"
    script:
        scripts("compare_solver_results.py")
