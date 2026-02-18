from pathlib import Path

from manju_web.backend.services.workflow_runtime import visual_audio_assets


def write_jsonl(path: Path, items) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(f"{item}\n")


def test_has_cloth_changed_targets_empty(tmp_path: Path) -> None:
    chars = tmp_path / "characters.jsonl"
    write_jsonl(chars, ["{}"])
    defaults = {}
    assert visual_audio_assets.has_cloth_changed_targets(chars, defaults) is False


def test_has_cloth_changed_targets_detects_change(tmp_path: Path) -> None:
    chars = tmp_path / "characters.jsonl"
    write_jsonl(
        chars,
        [
            '{"Character_Id":"C1","Plot_Costume_Change":[{"Outfit_id":"O2"}]}'
        ],
    )
    defaults = {"C1": "O1"}
    assert visual_audio_assets.has_cloth_changed_targets(chars, defaults) is True


def test_has_cloth_changed_targets_ignores_default(tmp_path: Path) -> None:
    chars = tmp_path / "characters.jsonl"
    write_jsonl(
        chars,
        [
            '{"Character_Id":"C1","Plot_Costume_Change":[{"Outfit_id":"O1"}]}'
        ],
    )
    defaults = {"C1": "O1"}
    assert visual_audio_assets.has_cloth_changed_targets(chars, defaults) is False
