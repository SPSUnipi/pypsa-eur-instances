# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

# default number of cores to use for snakemake
CORES ?= 1

.PHONY: help
help:
	@printf "SMS++ workflow targets\n"
	@printf "  run-instances-elec: Generate SMS++ instances for electricity\n"
	@printf "  run-instances-sector: Generate SMS++ instances for sector-coupled\n"
	@printf "  run-instances-tssb: Generate SMS++ TSSB instances for electricity and sector-coupled\n"
	@printf "  run-instances: Generate SMS++ instances for both electricity and sector-coupled\n"
	@printf "\n"
	@printf "Overrides: CORES=%s \n" "$(CORES)"

.PHONY: run-instances-elec
run-instances-elec:
	pixi run snakemake --cores $(CORES) compare_solver_elec_outputs --configfile config/instances/instances-IT-elec.yaml

.PHONY: run-instances-sector
run-instances-sector:
	pixi run snakemake --cores $(CORES) compare_solver_sector_outputs --configfile config/instances/instances-IT-sector.yaml

.PHONY: run-instances-tssb-elec
run-instances-tssb-elec:
	pixi run snakemake --cores $(CORES) compare_solver_elec_tssb_outputs --configfile config/instances/tssb/power-IT-noUC.yaml

.PHONY: run-instances-tssb-sector
run-instances-tssb-sector:
	pixi run snakemake --cores $(CORES) compare_solver_sector_outputs --configfile config/instances/tssb/sector-EU-noUC.yaml

.PHONY: run-instances-tssb
run-instances-tssb:
	$(MAKE) run-instances-tssb-elec
	$(MAKE) run-instances-tssb-sector

.PHONY: run-instances
run-instances:
	$(MAKE) run-instances-elec
	$(MAKE) run-instances-sector
