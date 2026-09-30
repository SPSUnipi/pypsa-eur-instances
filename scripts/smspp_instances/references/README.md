# references

Families of two-stage instances written to compare a decomposition of SMS++ with
the deterministic equivalent. The thermal family is written by `gen_thermal_tssb.py`
and `emit_thermal_tssb.py` of the references of pypsa2smspp, and
`extensive_thermal_tssb.py` here solves its deterministic equivalent with PyPSA;
the modular family is written by the scripts of this folder.

## A family on which the Lagrangian dual pays

The TSSB instances written from the PyPSA-Eur networks carry few thermal units, so their deterministic equivalent is close to an LP and a MILP solver closes it before a decomposition has read the file. `gen_thermal_tssb.py` writes instead a family in which the fleet is the point: its size, the length of the horizon, the number of scenarios and of buses are parameters, the fleet is heterogeneous (4 technologies with minimum up and down times from 2 to 12 periods, minimum powers from 0.30 to 0.50 of the maximum one, start-up costs proportional to the size), the here-and-now decision is the capacity of the expandable solar, and the uncertainty is the demand together with the availability of the renewables. Every unit becomes a ThermalUnitBlock, so the Lagrangian dual can be taken down to the units (see the templates `TSSBlock/TSSBSCfg-LDLD.txt` and `TSSBlock/TSSBSCfg-LDrec.txt` of pySMSpp, which need the BundleSolver 2.0):

```
python gen_thermal_tssb.py --units 80 --snapshots 168 --scenarios 3 --buses 1
python emit_thermal_tssb.py tuc_u80_t168_s3_b1
```

The first command writes `output/thermal_tssb/tuc_u80_t168_s3_b1_flat.nc`, the second one `output/thermal_tssb/smspp/smspp_tuc_u80_t168_s3_b1.nc4`; the seed is fixed, so the same values give the same instance.

The values worth generating are those of the table below, which compares the dual taken down to the units (a LagrangianDualSolver per scenario inside the one over the scenarios) with Gurobi on the deterministic equivalent. Since the two answer different questions (a bound against an integer optimum), Gurobi is asked the same thing, i.e., to prove the bound the dual gives (`BestBdStop`), and the time is that of doing so; the gaps are those of the bound of the dual and of the continuous relaxation with respect to the integer optimum, in percent. One run per row on the same machine, the units of the dual being solved by the dynamic programming of the ThermalUnitBlock.

| units | periods | scenarios | buses | binaries | dual (s) | MILP (s) | ratio | gap dual | gap LP |
|---|---|---|---|---|---|---|---|---|---|
| 10 | 24 | 3 | 1 | 720 | 0.30 | 0.18 | 0.6 | -0.557 | -0.724 |
| 40 | 48 | 3 | 1 | 5760 | 2.00 | 6.85 | 3.4 | -0.051 | -0.127 |
| 80 | 48 | 3 | 1 | 11520 | 3.27 | 9.11 | 2.8 | -0.012 | -0.093 |
| 80 | 96 | 3 | 1 | 23040 | 12.74 | 27.15 | 2.1 | -0.024 | -0.072 |
| 80 | 96 | 3 | 4 | 23040 | 65.24 | 29.87 | 0.5 | -0.037 | -0.041 |
| 80 | 96 | 5 | 1 | 38400 | 24.90 | 47.31 | 1.9 | -0.026 | -0.072 |
| 40 | 96 | 20 | 1 | 76800 | 99.94 | 105.73 | 1.1 | -0.066 | -0.102 |
| 80 | 168 | 3 | 1 | 40320 | 84.16 | 384.56 | 4.6 | -0.045 | -0.076 |
| 80 | 168 | 5 | 1 | 67200 | 162.78 | 431.55 | 2.7 | -0.034 | -0.064 |

The dual is ahead by 2 to 4.6 times on the large instances with one bus, it is behind on the smallest ones, and it is behind by 2 times on the one with 4 buses, where the multipliers of the network are many. Its memory stays between 163 MB and 2.7 GB, whereas the MILP on the integer problem reaches 73 GB and, on a machine with less memory, does not solve the last 4 rows at all. The bound improves as the fleet grows (from -0.56% at 10 units to -0.012% at 80), which is the duality gap of the unit commitment closing.

The same dual can also be solved by one LagrangianDualSolver that decomposes the whole tree at once (`intRecursive`), and the two give the same bound to 10 or 11 digits; which of them is faster depends on where the instance is large (outer iterations in parentheses):

| instance | chain | recursive |
|---|---|---|
| u80_t48_s3 | 9.31 s (2) | 4.72 s (46) |
| u80_t168_s3 | 80.76 s (19) | 29.23 s (143) |
| u80_t336_s3 | 600.24 s (27) | 132.45 s (192) |
| u80_t720_s3 | 2939.99 s (21) | does not close in 3600 s |
| u40_t96_s10 | 39.57 s (2) | 48.08 s (202) |

i.e., the recursive dual pays on the units and on horizons up to 2 weeks, while the chain pays on the scenarios and on horizons of a month, where the master of the recursive dual (one multiplier per node and period of every scenario) becomes the bottleneck.

PyPSA 1.2.3 cannot optimize a network that is at once stochastic and committable (its committability constraints do not know about the scenario axis), so on this family the monolithic reference is Gurobi on the deterministic equivalent SMS++ writes, and PyPSA gives a reference value only with `--no-design`, where the scenarios decouple (`crosscheck_thermal_tssb.py`).

## A family on which the Benders decomposition pays

A Benders decomposition pays when the first stage is integer and the second one is a linear program repeated over many scenarios: the deterministic equivalent is then a MILP whose every node is the whole stochastic linear program, while the master of the decomposition carries the integer Variable alone and the scenarios are solved apart, and in parallel. `gen_modular_tssb.py` writes such a family: on every bus the first stage builds whole modules of solar and wind (`p_nom_mod`, so that PyPSA writes an integer number of modules), the thermal fleet and a storage are in place and dispatched without commitment, and the scenarios draw the demand and the availability of the renewables independently, so that their number is a free parameter. The converter writes a modular asset of UCBlock as an integer design, the number of its modules (`MaxCapacityDesign` = minus the largest number of modules), and `emit_modular_tssb.py` writes the network in the form BendersDecompositionSolver is attached to by `smspp_tssb_solver -k`:

```
python gen_modular_tssb.py --snapshots 168 --scenarios 200 --buses 10
python emit_modular_tssb.py mod_t168_s200_b10 ucblock
python solve_modular_tssb.py mod_t168_s200_b10 gurobi MIPGap=1e-6
smspp_tssb_solver -k -c <pySMSpp>/pysmspp/data/configs/TSSBlock/ -S TSSBSCfg-BDS.txt output/modular_tssb/smspp/smspp_mod_t168_s200_b10_ucblock.nc4
```

The third command is the PyPSA reference, the network being solved as a stochastic one, and the fourth one the Benders decomposition, whose template evaluates the scenarios of a round by 8 threads (`intMaxThread`, which changes the time and not the run). The values worth generating have 168 periods, from 10 to 20 buses and from 50 to 200 scenarios: there the Benders decomposition reaches the optimum PyPSA reaches, with about half its memory, it is faster than Gurobi given the same number of threads, and with more threads it is faster than Gurobi given all of them, whose branch and bound closes these instances at the root and whose time is therefore that of the linear program. The capital costs are those of a week, of the order of the saving a MW of each technology buys over it, so that the decisions are neither all zero nor all at their bound; `--capital-scale`, `--module-share` and `--max-modules` change them.

The same networks with the modules turned off, i.e., with a continuous design (a name ending in `c`), are where every way SMS++ has of solving a stochastic investment can be put side by side, the InvestmentBlock over the stochastic Block (the ad hoc Benders decomposition, whose design is a capacity) included; each of them can also be written as a MultiStageStochasticBlock whose scenarios are grouped into outer realizations, which has the same extensive form as the flat network and whose leaves are the subproblems of the Benders form that `smspp_tssb_solver -k` builds:

```
python emit_modular_tssb.py mod_t168_s50_b10c ucblock
python emit_modular_tssb.py mod_t168_s50_b10c investment_outside
python emit_modular_tssb.py mod_t168_s50_b10c mssb_ucblock 5
python emit_modular_tssb.py mod_t168_s50_b10c mssb_investment_outside 5
```

The forms `det_ucblock` and `det_investment` write the single scenario of a network as a deterministic capacity expansion, with the design in the units of the UCBlock or in an InvestmentBlock over it, the latter being again the ad hoc Benders decomposition. The forms `ucblock` are solved by `TSSBSCfg-IP.txt` and by `TSSBSCfg-BDS.txt` with `-k`, the forms `investment_outside` by `smspp_investmentblock_solver` with `TSSBSCfg-IB.txt`, all templates of the `TSSBlock` folder of pySMSpp.
