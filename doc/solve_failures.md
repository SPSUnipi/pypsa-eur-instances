# Continuing independent optimizations after a failure

The default workflow profile enables Snakemake `keep-going`. Failed solves stop
their own job and dependent jobs, while independent jobs continue. Snakemake
still exits with a nonzero status after those jobs finish.

If using another profile, pass `--keep-going` explicitly:

```sh
conda run -n pypsa-eur-smspp-instances snakemake --cores 16 --keep-going solve_elec_networks --configfile config/test/config.electricity.yaml
```

Electricity and sector rules using `solve_network.py` run through a lightweight
supervisor. Python exceptions, solver crashes, and signals such as SIGKILL produce
a warning in the terminal and Python log. Non-OK solver statuses are rejected
before exporting the solution.

Failed attempts retain a Snakemake-format benchmark next to the usual benchmark,
with a `.failed` suffix. `scripts/collect_solve_benchmarks.py` includes these
attempts, with missing objective/network data and the failure recorded in the
status columns. A retry clears the previous failure benchmark; successful jobs
retain the normal Snakemake benchmark. Failed measurements cover the supervised
Python process and its descendants, including the small supervisor overhead.
Memory peaks are sampled and may miss brief spikes.

The supervisor must remain alive to save the benchmark. Killing the entire job
process group, scheduler allocation, container, or machine can prevent this;
SIGKILL alone does not establish that an out-of-memory event occurred. This
setting also does not make a shell or Makefile continue to its next separate
Snakemake invocation after a nonzero exit.
