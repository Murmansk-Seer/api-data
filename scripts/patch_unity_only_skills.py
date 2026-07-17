from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _first_int(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    return str(values[0])


def patch_unity_only_skills(source_dir: Path) -> list[int]:
    unity_moves_file = source_dir / "unity" / "moves.json"
    flash_skills_file = source_dir / "flash" / "config.xml.SkillXMLInfo.xml"

    unity_moves = json.loads(unity_moves_file.read_text(encoding="utf-8"))["root"][
        "moves"
    ]["move"]
    tree = ET.parse(flash_skills_file)
    root = tree.getroot()

    flash_ids = {
        int(item.attrib["ID"])
        for item in root.findall("item")
        if item.attrib.get("ID")
    }
    missing_moves = [move for move in unity_moves if int(move["id"]) not in flash_ids]

    for move in missing_moves:
        attrs = {
            "Name": str(move.get("name") or ""),
            "Accuracy": str(move.get("accuracy", 100)),
            "ID": str(move["id"]),
            "Category": str(move.get("category", 4)),
            "MaxPP": str(move.get("max_pp", 0)),
            "Power": str(move.get("power", 0)),
            "Type": str(move.get("type", 8)),
            "CritRate": str(move.get("crit_rate", 1) or 1),
        }
        if side_effect := _first_int(move.get("side_effect")):
            attrs["SideEffect"] = side_effect
        if side_effect_arg := _first_int(move.get("side_effect_arg")):
            attrs["SideEffectArg"] = side_effect_arg
        ET.SubElement(root, "item", attrs)

    if missing_moves:
        tree.write(flash_skills_file, encoding="utf-8", xml_declaration=False)

    return [int(move["id"]) for move in missing_moves]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source_dir",
        nargs="?",
        default="source",
        type=Path,
        help="config-sources checkout directory",
    )
    args = parser.parse_args()

    patched_ids = patch_unity_only_skills(args.source_dir)
    if patched_ids:
        print(
            "Added Flash skill placeholder rows for Unity-only skills: "
            + ", ".join(str(skill_id) for skill_id in patched_ids)
        )
    else:
        print("No Unity-only skills missing Flash rows.")


if __name__ == "__main__":
    main()
