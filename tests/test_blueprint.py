"""Validate the shipped blueprint.

A blueprint is YAML that nothing compiles: a typo in a trigger key or an input
referenced but never declared is invisible until somebody imports it and their
automation silently never runs. So this puts it through the same validation Home
Assistant does at import time, with realistic inputs filled in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    async_validate_config_item,
)
from homeassistant.components.blueprint.errors import MissingInput
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml as yaml_util

BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "rover_client"
    / "access_code_reminder.yaml"
)

INPUTS = {
    "visit_calendar": "calendar.rover_visits",
    "lead_time": "-01:00:00",
    "code_entity": "input_text.fake_door_code",
    "access_sensor": "binary_sensor.rover_house_access_needed",
    "send_action": [
        {
            "action": "notify.persistent_notification",
            "data": {"message": "{{ message }}"},
        }
    ],
}


@pytest.fixture
def blueprint() -> Blueprint:
    """Load the blueprint the way Home Assistant loads it."""
    return Blueprint(
        yaml_util.parse_yaml(BLUEPRINT_PATH.read_text(encoding="utf-8")),
        path=str(BLUEPRINT_PATH),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


def test_the_blueprint_declares_every_input_it_uses(blueprint: Blueprint) -> None:
    """Blueprint() raises on an undeclared `!input`, so loading it is the test."""
    assert blueprint.domain == "automation"
    assert set(blueprint.inputs) == set(INPUTS) | {
        "require_access_sensor",
        "extra_note",
    }


def test_the_blueprint_runs_on_the_version_it_claims(blueprint: Blueprint) -> None:
    """The declared minimum must not be above what this integration supports."""
    assert blueprint.validate() is None


async def test_the_substituted_automation_is_valid(
    hass: HomeAssistant, blueprint: Blueprint
) -> None:
    """Fill the inputs in and validate the automation that comes out.

    This is the check that catches a misspelled trigger platform or an action that
    is not a real action, which are otherwise only discovered by a user whose
    reminder never arrives.
    """
    assert await async_setup_component(hass, "calendar", {})

    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "rover_client/access_code_reminder.yaml",
                "input": INPUTS,
            }
        },
    )
    inputs.validate()

    config = await async_validate_config_item(
        hass, "automation", inputs.async_substitute()
    )

    assert config is not None


async def test_optional_inputs_have_defaults(
    hass: HomeAssistant, blueprint: Blueprint
) -> None:
    """Everything the user is not asked for has to have a usable default.

    Otherwise importing the blueprint and pressing save produces a MissingInput
    error rather than a working automation.
    """
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "rover_client/access_code_reminder.yaml",
                "input": {
                    key: value
                    for key, value in INPUTS.items()
                    if key not in ("lead_time", "access_sensor")
                },
            }
        },
    )

    inputs.validate()

    assert inputs.inputs_with_default["lead_time"] == "-01:00:00"
    assert (
        inputs.inputs_with_default["access_sensor"]
        == "binary_sensor.rover_house_access_needed"
    )


async def test_a_missing_required_input_is_refused(
    hass: HomeAssistant, blueprint: Blueprint
) -> None:
    """The inputs with no sensible default must be asked for."""
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "rover_client/access_code_reminder.yaml",
                "input": {"lead_time": "-01:00:00"},
            }
        },
    )

    with pytest.raises(MissingInput):
        inputs.validate()
