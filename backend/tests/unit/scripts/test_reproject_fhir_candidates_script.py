"""Safety checks for the audited FHIR candidate reprojection CLI."""

import pytest
from scripts.reproject_fhir_candidates import parse_args


def test_dry_run_can_be_scoped_to_one_fact_type() -> None:
    args = parse_args(["--dry-run", "--fact-type", "care_plan"])

    assert args.dry_run is True
    assert args.fact_type == "care_plan"


def test_apply_requires_an_explicit_fact_type_scope() -> None:
    with pytest.raises(SystemExit, match="2"):
        parse_args(
            [
                "--apply",
                "--actor-id",
                "00000000-0000-0000-0000-000000000001",
                "--report-sha256",
                "a" * 64,
            ]
        )
