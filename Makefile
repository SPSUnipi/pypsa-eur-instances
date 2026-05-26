# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

# default number of cores to use for snakemake
CORES ?= 1

.PHONY: help
help:
	@printf "SMS++ workflow targets\n"
	@printf "  smspp-instances-elec: Generate SMS++ instances for electricity\n"
	@printf "  smspp-instances-sector: Generate SMS++ instances for sector-coupled\n"
	@printf "  smspp-instances: Generate SMS++ instances for both electricity and sector-coupled\n"
	@printf "\n"
	@printf "Overrides: CORES=%s \n" "$(CORES)"

.PHONY: smspp-instances-elec
smspp-instances-elec:
	pixi run snakemake --cores $(CORES) compare_solver_elec_outputs --configfile config/smspp-IT-elec.yaml

.PHONY: smspp-instances-sector
smspp-instances-sector:
	pixi run snakemake --cores $(CORES) compare_solver_sector_outputs --configfile config/smspp-IT-sector.yaml

.PHONY: smspp-instances
smspp-instances:
	$(MAKE) smspp-instances-elec
	$(MAKE) smspp-instances-sector