from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.patch_unity_only_skills import patch_unity_only_skills


def test_patch_unity_only_skills_adds_missing_flash_rows(tmp_path: Path) -> None:
    source = tmp_path / "source"
    unity = source / "unity"
    flash = source / "flash"
    unity.mkdir(parents=True)
    flash.mkdir(parents=True)

    (unity / "moves.json").write_text(
        json.dumps(
            {
                "root": {
                    "moves": {
                        "move": [
                            {
                                "id": 10001,
                                "name": "existing",
                                "accuracy": 95,
                                "category": 1,
                                "max_pp": 35,
                                "power": 35,
                                "type": 8,
                            },
                            {
                                "id": 29403,
                                "name": "unity only",
                                "accuracy": 100,
                                "category": 4,
                                "max_pp": 40,
                                "power": 0,
                                "type": 8,
                                "side_effect": [972],
                                "side_effect_arg": [1],
                            },
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (flash / "config.xml.SkillXMLInfo.xml").write_text(
        '<root><item Name="existing" Accuracy="95" ID="10001" '
        'Category="1" MaxPP="35" Power="35" Type="8" /></root>',
        encoding="utf-8",
    )

    patched = patch_unity_only_skills(source)

    assert patched == [29403]
    output = (flash / "config.xml.SkillXMLInfo.xml").read_text(encoding="utf-8")
    assert 'ID="29403"' in output
    assert 'Name="unity only"' in output
    assert 'SideEffect="972"' in output
    assert 'SideEffectArg="1"' in output
