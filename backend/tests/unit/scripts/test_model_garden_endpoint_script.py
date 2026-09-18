"""The session endpoint script must only ever remove endpoints it created."""

from datetime import UTC, datetime

import pytest
from scripts.model_garden_endpoint import (
    SESSION_PREFIX,
    build_deploy_body,
    openai_base_url,
    parse_args,
    select_session_endpoints,
    session_display_name,
)


def test_down_without_an_endpoint_id_only_selects_session_endpoints() -> None:
    endpoints = [
        {"name": "e/1", "displayName": f"{SESSION_PREFIX}medgemma-15-4b-it-20260915-2010"},
        {"name": "e/2", "displayName": "production-triage"},
        {"name": "e/3"},
    ]

    assert [e["name"] for e in select_session_endpoints(endpoints)] == ["e/1"]


def test_deploy_body_pins_one_replica_on_the_requested_hardware() -> None:
    body = build_deploy_body(
        model="publishers/google/models/medgemma@medgemma-1.5-4b-it",
        machine_type="g2-standard-24",
        accelerator_type="NVIDIA_L4",
        accelerator_count=2,
        display_name="session-x",
    )

    resources = body["deployConfig"]["dedicatedResources"]
    assert resources["machineSpec"] == {
        "machineType": "g2-standard-24",
        "acceleratorType": "NVIDIA_L4",
        "acceleratorCount": 2,
    }
    assert (resources["minReplicaCount"], resources["maxReplicaCount"]) == (1, 1)
    assert body["modelConfig"]["acceptEula"] is True


def test_session_names_carry_the_prefix_and_a_timestamp() -> None:
    name = session_display_name(
        "publishers/google/models/medgemma@medgemma-1.5-4b-it",
        datetime(2026, 9, 15, 20, 10, tzinfo=UTC),
    )

    assert name == "session-medgemma-medgemma-15-4b-it-20260915-2010"


def test_openai_base_url_uses_the_dedicated_dns() -> None:
    assert openai_base_url("123.us-central1-9.prediction.vertexai.goog") == (
        "https://123.us-central1-9.prediction.vertexai.goog/v1"
    )


def test_up_requires_the_hardware_to_be_named() -> None:
    with pytest.raises(SystemExit):
        parse_args(["up", "--model", "publishers/google/models/medgemma@medgemma-1.5-4b-it"])
