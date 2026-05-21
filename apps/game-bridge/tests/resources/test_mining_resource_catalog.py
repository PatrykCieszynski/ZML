from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from zml_game_bridge.resources.mining_resources import (
    MiningResourceCatalog,
    normalize_resource_name,
)


def test_catalog_loads_seed_groups_and_user_overrides(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    user_path = tmp_path / "user.json"
    seed_path.write_text(
        json.dumps(
            {
                "ores": ["Lysterium Stone"],
                "enmatters": ["Blue Crystal"],
            }
        ),
        encoding="utf-8",
    )
    user_path.write_text(
        json.dumps(
            {
                "resources": [
                    {
                        "name": "Blue Crystal",
                        "type": "enmatter",
                        "track_as_loot": False,
                        "source": "user",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    catalog = MiningResourceCatalog(seed_path=seed_path, user_path=user_path)

    lysterium = catalog.get("lysterium   stone")
    assert lysterium is not None
    assert lysterium.resource_type == "ore"
    assert catalog.is_tracked_loot("Lysterium Stone")
    assert not catalog.is_tracked_loot("Blue Crystal")


def test_catalog_learns_resource_to_user_json(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    user_path = tmp_path / "user.json"
    seed_path.write_text("{}", encoding="utf-8")
    event_dt = datetime(2026, 5, 20, 18, 28, 18)

    catalog = MiningResourceCatalog(seed_path=seed_path, user_path=user_path)
    learned = catalog.learn_resource(
        name="  Narcanisum   Stone ",
        resource_type="ore",
        event_dt=event_dt,
    )

    assert learned.name == "Narcanisum Stone"
    assert learned.resource_type == "ore"
    assert learned.source == "learned"
    assert learned.first_seen_event_dt == "2026-05-20T18:28:18"
    assert learned.last_seen_event_dt == "2026-05-20T18:28:18"

    stored = json.loads(user_path.read_text(encoding="utf-8"))
    assert stored["resources"][0]["name"] == "Narcanisum Stone"
    assert stored["resources"][0]["type"] == "ore"
    assert stored["resources"][0]["source"] == "learned"


def test_catalog_preserves_user_override_when_learning(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    user_path = tmp_path / "user.json"
    seed_path.write_text("{}", encoding="utf-8")
    user_path.write_text(
        json.dumps(
            {
                "resources": [
                    {
                        "name": "Mining Strongbox 1",
                        "type": "other",
                        "track_as_loot": False,
                        "source": "user",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    catalog = MiningResourceCatalog(seed_path=seed_path, user_path=user_path)
    learned = catalog.learn_resource(
        name="Mining Strongbox 1",
        resource_type="ore",
        event_dt=datetime(2026, 5, 20, 18, 28, 18),
    )

    assert learned.resource_type == "other"
    assert learned.source == "user"
    assert not learned.track_as_loot


def test_normalize_resource_name_collapses_case_and_spacing() -> None:
    assert normalize_resource_name("  Blue   Crystal ") == "blue crystal"
