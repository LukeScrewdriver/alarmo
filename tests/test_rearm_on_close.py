"""Test including bypassed sensors again once they close (rearm_on_close)."""

from typing import Any

import pytest

from tests.helpers import (
    advance_time,
    setup_alarmo_entry,
    patch_alarmo_integration_dependencies,
)
from tests.factories import AreaFactory, SensorFactory

ALARM_ENTITY = "alarm_control_panel.test_area_1"
DOOR = "binary_sensor.generic_area_1_door_sensor"
REARM_TIME = 10  # const.SENSOR_REARM_TIME


def _setup(hass: Any, rearm_on_close: bool, entry_id: str) -> tuple[Any, Any]:
    """Create one area with an auto-bypassed door sensor."""
    area_1 = AreaFactory.create_area(area_id="area_1", name="Test Area 1")
    sensors = [
        {
            **SensorFactory.create_door_sensor(
                entity_id=DOOR,
                area="area_1",
                modes=["armed_away"],
                auto_bypass=True,
                auto_bypass_modes=["armed_away"],
            ),
            "rearm_on_close": rearm_on_close,
        }
    ]
    return setup_alarmo_entry(hass, areas=[area_1], sensors=sensors, entry_id=entry_id)


async def _arm_with_open_door(hass: Any, entry: Any) -> None:
    """Arm while the door is open, so that it gets bypassed."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await hass.services.async_call(
        "alarmo",
        "arm",
        {"entity_id": ALARM_ENTITY, "code": "1234"},
        blocking=True,
    )
    await hass.async_block_till_done()
    exit_time = AreaFactory.create_area(area_id="area_1")["modes"]["armed_away"][
        "exit_time"
    ]
    await advance_time(hass, exit_time + 1)

    state = hass.states.get(ALARM_ENTITY)
    assert state.state == "armed_away"
    assert DOOR in (state.attributes.get("bypassed_sensors") or [])


@pytest.mark.asyncio
async def test_bypassed_sensor_is_included_after_closing(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """A bypassed sensor that stays closed is included again and can trigger."""
    storage, entry = _setup(hass, True, "test_rearm_on_close_included")
    with patch_alarmo_integration_dependencies(storage):
        await _arm_with_open_door(hass, entry)

        hass.states.async_set(DOOR, "off")
        await hass.async_block_till_done()
        await advance_time(hass, REARM_TIME + 1)

        state = hass.states.get(ALARM_ENTITY)
        assert state.state == "armed_away"
        assert not state.attributes.get("bypassed_sensors")

        hass.states.async_set(DOOR, "on")
        await hass.async_block_till_done()
        assert hass.states.get(ALARM_ENTITY).state in ("pending", "triggered")


@pytest.mark.asyncio
async def test_short_close_keeps_sensor_bypassed(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """Closing and reopening within the rearm time keeps the sensor bypassed."""
    storage, entry = _setup(hass, True, "test_rearm_on_close_bounce")
    with patch_alarmo_integration_dependencies(storage):
        await _arm_with_open_door(hass, entry)

        hass.states.async_set(DOOR, "off")
        await hass.async_block_till_done()
        await advance_time(hass, REARM_TIME // 2)
        hass.states.async_set(DOOR, "on")
        await hass.async_block_till_done()
        await advance_time(hass, REARM_TIME + 1)

        state = hass.states.get(ALARM_ENTITY)
        assert state.state == "armed_away"
        assert DOOR in (state.attributes.get("bypassed_sensors") or [])


@pytest.mark.asyncio
async def test_without_option_sensor_stays_bypassed(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """Default behaviour is unchanged: the sensor stays bypassed until disarm."""
    storage, entry = _setup(hass, False, "test_rearm_on_close_disabled")
    with patch_alarmo_integration_dependencies(storage):
        await _arm_with_open_door(hass, entry)

        hass.states.async_set(DOOR, "off")
        await hass.async_block_till_done()
        await advance_time(hass, REARM_TIME + 1)
        hass.states.async_set(DOOR, "on")
        await hass.async_block_till_done()

        state = hass.states.get(ALARM_ENTITY)
        assert state.state == "armed_away"
        assert DOOR in (state.attributes.get("bypassed_sensors") or [])
