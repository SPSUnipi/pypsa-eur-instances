# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""Preserve failed solve benchmarks, including when the solver is SIGKILLed."""

import os
import pickle
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from snakemake.benchmark import benchmarked, write_benchmark_records


def supervise(command, failure_benchmark, python_log):
    """Run a solve in its own process group and retain measurements on failure."""
    failure_benchmark = Path(failure_benchmark)
    failure_benchmark.parent.mkdir(parents=True, exist_ok=True)
    failure_benchmark.unlink(missing_ok=True)
    process = None
    # Observe this lightweight supervisor and its descendants, so even an
    # immediately failing child cannot disappear before monitoring starts.
    with benchmarked(interval=1) as record:
        try:
            process = subprocess.Popen(command, start_new_session=True)
            returncode = process.wait()
        finally:
            if process is not None:
                # A killed solve can leave its memory monitor or solver behind.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()

    if returncode:
        write_benchmark_records([record], str(failure_benchmark), False)
        condition = (
            signal.Signals(-returncode).name
            if returncode < 0
            else f"exit_code_{returncode}"
        )
        message = (
            f"Solving status 'error' with termination condition '{condition}'. "
            f"Optimization failed; stopping this job. Benchmark: {failure_benchmark}. "
            "Independent jobs continue when Snakemake keep-going is enabled."
        )
        print(f"WARNING: {message}", file=sys.stderr, flush=True)
        with open(python_log, "a") as stream:
            print(f"WARNING: {message}", file=stream)
        raise subprocess.CalledProcessError(returncode, command)


def run_solve(context, script):
    """Pass the Snakemake script context to a separately killable Python process."""
    with tempfile.TemporaryDirectory(prefix="solve-network-") as directory:
        context_path = Path(directory) / "context.pkl"
        with context_path.open("wb") as stream:
            pickle.dump((context, sys.path), stream)
        bootstrap = (
            "import pickle, runpy, sys; "
            "context, paths = pickle.load(open(sys.argv[1], 'rb')); "
            "sys.path[:] = paths; "
            "runpy.run_path(sys.argv[2], run_name='__main__', "
            "init_globals={'snakemake': context})"
        )
        supervise(
            [sys.executable, "-c", bootstrap, str(context_path), str(script)],
            context.log.failure_benchmark,
            context.log.python,
        )


if __name__ == "__main__":
    context = globals()["snakemake"]
    run_solve(context, Path(context.scriptdir) / "solve_network.py")
