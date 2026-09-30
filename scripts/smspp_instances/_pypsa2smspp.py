"""
The test directory of a pypsa2smspp checkout, which the generators read.

Some generators build their networks from the Excel test networks of
pypsa2smspp (through its conftest.py and network_definition.py), and some read
the networks that its references write under test/output; PYPSA2SMSPP_TEST
names that directory, and importing this module puts it on the path.
"""

import os
import sys
from pathlib import Path

TEST = Path(os.environ.get("PYPSA2SMSPP_TEST", "")).expanduser().resolve()
if not (TEST / "conftest.py").is_file():
    raise SystemExit("set PYPSA2SMSPP_TEST to the test directory of a "
                     "pypsa2smspp checkout")
if str(TEST) not in sys.path:
    sys.path.insert(0, str(TEST))
