# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Stochastic scenarios configuration.

See docs in https://pypsa-eur.readthedocs.io/en/latest/configuration.html#stochastic-scenarios
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class StochasticScenariosExportConfig(BaseModel):
    """Configuration for exporting deterministic views of stochastic solutions."""

    expected: bool = Field(
        True,
        description=(
            "Export the probability-weighted deterministic network view from the "
            "stochastic solution."
        ),
    )

    scenarios: bool = Field(
        False,
        description=(
            "Export one deterministic network view for each stochastic scenario."
        ),
    )


class StochasticScenariosPostprocessConfig(BaseModel):
    """Configuration for post-processing stochastic solutions."""

    use_expected: bool = Field(
        True,
        description=(
            "Use the probability-weighted deterministic network view as input for "
            "standard post-processing rules when stochastic scenarios are enabled."
        ),
    )


class StochasticScenariosConfig(BaseModel):
    """Configuration for stochastic scenarios."""

    enable: bool = Field(
        False,
        description="Whether to build and solve a stochastic PyPSA network.",
    )

    file: Path = Field(
        Path("config/stochastic_scenarios.yaml"),
        description="Path to the external YAML file defining stochastic scenarios.",
    )

    export: StochasticScenariosExportConfig = Field(
        default_factory=StochasticScenariosExportConfig,
        description="Export options for stochastic solutions.",
    )

    postprocess: StochasticScenariosPostprocessConfig = Field(
        default_factory=StochasticScenariosPostprocessConfig,
        description="Post-processing options for stochastic solutions.",
    )

    @field_validator("file")
    @classmethod
    def file_must_be_yaml(cls, value: Path) -> Path:
        """Check that the stochastic scenario file has a YAML extension."""
        if value.suffix not in {".yaml", ".yml"}:
            raise ValueError("stochastic_scenarios.file must be a YAML file.")
        return value