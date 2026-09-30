# InvestmentBlock with the BundleSolver 2.0

The configuration with which `scripts/smspp_instances/instance_generator.py`
solves the InvestmentBlock form of an instance, which needs an SMS++ whose
bundle is the 2.0: the master is a MasterProblemBlock solved by a :MILPSolver
(`strMPBSolverCfg` -> `MPBCfg.txt`), and the inner Block is solved by GUROBI
(`strInnerBSC` -> `BSCfg1.txt`), whose `intHomogeneousDirection 1` returns the
unbounded dual direction a feasibility cut is read off. It solves the
instances where the design of an asset sits at 0 and those whose inner Block
the design can starve, which the configuration of the BundleSolver 1.0 in
pySMSpp does not: its master refuses a feasibility cut, which reaches it as a
constraint. The presolve of the master is left at its default, since with it
off the master of a design over several extendable lines ends in
"Bundle::FormD: unrecoverable MP failure".

The same three files serve an InvestmentBlock whose inner Block is a whole
TwoStageStochasticBlock or MultiStageStochasticBlock, as the `investment_outside`
option of pypsa2smspp writes it, i.e., a Benders decomposition with the design
in the master and the scenarios, solved together by GUROBI, in the value
function.
