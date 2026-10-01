"""Failure containment without running an expensive network optimization."""

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.collect_solve_benchmarks import benchmark_files, collect_benchmarks
from scripts.solve_network_supervisor import run_solve, supervise


@pytest.mark.parametrize(
    "code, condition",
    [
        ("raise MemoryError('test')", "exit_code_1"),
        ("import os, signal; os.kill(os.getpid(), signal.SIGKILL)", "SIGKILL"),
    ],
)
def test_failure_benchmark_and_collection(tmp_path, code, condition):
    root = tmp_path / "results"
    benchmark = root / "benchmarks/solve_network/base_s_2_elec__highs.failed"
    log = root / "logs/solve_network/base_s_2_elec__highs_python.log"
    log.parent.mkdir(parents=True)
    with pytest.raises(subprocess.CalledProcessError):
        supervise([sys.executable, "-c", code], benchmark, log)
    assert pd.read_csv(benchmark, sep="\t").iloc[0]["s"] >= 0
    frame = collect_benchmarks([root])
    assert len(frame) == 1
    assert frame.iloc[0].solve_status == "error"
    assert frame.iloc[0].termination_condition == condition
    assert pd.isna(frame.iloc[0].objective)


def test_context_and_successful_retry(tmp_path):
    benchmark = tmp_path / "solve.failed"
    benchmark.write_text("stale failure")
    output = tmp_path / "output"
    script = tmp_path / "solve.py"
    script.write_text(
        "from pathlib import Path\nPath(snakemake.output).write_text('ok')\n"
    )
    context = SimpleNamespace(
        output=str(output),
        log=SimpleNamespace(
            failure_benchmark=str(benchmark), python=str(tmp_path / "log")
        ),
    )
    run_solve(context, script)
    assert output.read_text() == "ok"
    assert not benchmark.exists()


def test_empty_failure_log_does_not_hide_successful_benchmark(tmp_path):
    benchmark = tmp_path / "benchmarks/solve_network/base_s_2_elec__highs"
    benchmark.parent.mkdir(parents=True)
    benchmark.write_text("s\n1\n")
    benchmark.with_name(benchmark.name + ".failed").touch()
    assert benchmark_files(tmp_path) == [benchmark]


@pytest.mark.parametrize("kill", [False, True])
def test_snakemake_continues_independent_jobs(tmp_path, kill):
    repository = Path(__file__).resolve().parents[1]
    shutil.copy(repository / "scripts/solve_network_supervisor.py", tmp_path)
    (tmp_path / "solve_network.py").write_text(
        "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"
        if kill
        else "raise MemoryError('simulated optimization failure')\n"
    )
    (tmp_path / "Snakefile").write_text("""
rule all:
    input: "failed.nc", "independent.nc"
rule failing:
    output: "failed.nc"
    log:
        python="failed.log",
        failure_benchmark="benchmarks/failed.failed"
    benchmark: "benchmarks/failed"
    priority: 10
    script: "solve_network_supervisor.py"
rule independent:
    output: "independent.nc"
    shell: "touch {output}"
rule dependent:
    input: "failed.nc"
    output: "dependent.nc"
    shell: "touch {output}"
""")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "snakemake",
            "--cores",
            "1",
            "--workflow-profile",
            str(repository / "profiles/default"),
            "all",
            "dependent.nc",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert (tmp_path / "independent.nc").exists(), result.stdout + result.stderr
    assert not (tmp_path / "failed.nc").exists()
    assert not (tmp_path / "dependent.nc").exists()
    assert (tmp_path / "benchmarks/failed.failed").exists(), (
        result.stdout + result.stderr
    )
