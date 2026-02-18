from pathlib import Path
from typing import Dict, List

from manju_web.backend.repositories import asset_repo, project_repo
from manju_web.backend.services.workflow_runtime.io_jsonl import write_jsonl


def test_build_tables(project_output_dir: Path) -> None:
    assets = project_repo.storyboard_assets_dir("demo")
    assets.mkdir(parents=True, exist_ok=True)
    chars = [
        {
            "Character_Id": "char_1",
            "Character_name": "A",
            "Alias": "AA",
            "attribute": "human",
            "Age_group": "adult",
            "Sex": "M",
            "Appearance Description": "desc",
            "Default_Outfit (Clothing)": {"Outfit_id": "o1", "Outfit_Description": "cloth"},
            "Default_Shoes": "shoe",
        }
    ]
    locs = [{"Location_ID": "loc_1", "Location": "place", "Location_description": "desc"}]
    write_jsonl(str(assets / "characters.jsonl"), chars)
    write_jsonl(str(assets / "locations.jsonl"), locs)
    character_table = asset_repo.build_character_table(assets)
    location_table = asset_repo.build_location_table(assets)
    # 边界：基础表构建应容错缺失字段并返回结构化数据
    assert character_table and character_table[0]["Character_Id"] == "char_1"
    assert location_table and location_table[0]["Location_ID"] == "loc_1"


def test_update_fenjing_prompt(project_output_dir: Path) -> None:
    assets = project_repo.storyboard_assets_dir("demo")
    chapter_dir = assets / "storyboards" / "storyboard_chapter_1"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    prompts_path = chapter_dir / "fenjing_prompts.jsonl"
    prompts = [{"fenjing_id": "1", "prompt": "old"}]
    write_jsonl(str(prompts_path), prompts)
    result = asset_repo.update_fenjing_prompt("demo", "storyboard_chapter_1", "1", "new")
    # 边界：存在目标分镜时应更新提示词
    assert result["ok"] is True
    updated = asset_repo.safe_read_jsonl(prompts_path)
    assert updated and updated[0]["prompt"] == "new"


def test_update_fenjing_prompt_missing(project_output_dir: Path) -> None:
    # 边界：prompts 文件不存在时应返回明确错误
    result = asset_repo.update_fenjing_prompt("demo", "storyboard_chapter_1", "1", "new")
    assert result["ok"] is False
    assert result["error"] == "prompts_missing"


def test_delete_candidate_file_edge(project_output_dir: Path) -> None:
    # 边界：空路径直接返回缺失错误
    result = asset_repo.delete_candidate_file("demo", "", "fenjing_candidates")
    assert result["ok"] is False
    assert result["error"] == "candidate_missing"
    base = project_repo.project_base_dir("demo")
    candidate_dir = base / "other_candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / "a.png"
    candidate_path.write_text("x", encoding="utf-8")
    # 边界：路径存在但不在指定目录下应拒绝
    result = asset_repo.delete_candidate_file("demo", "other_candidates/a.png", "fenjing_candidates")
    assert result["ok"] is False
    assert result["error"] == "candidate_invalid"


def test_visual_audio_results_skip_missing_output_when_no_scope(project_output_dir: Path) -> None:
    assets = project_repo.storyboard_assets_dir("demo")
    assets.mkdir(parents=True, exist_ok=True)
    write_jsonl(str(assets / "character_prompts.jsonl"), [{"Character_Id": "char_1", "st_prompt": "x", "name": "A"}])
    write_jsonl(str(assets / "characters.jsonl"), [{"Character_Id": "char_1", "Character_name": "A"}])
    results = asset_repo.build_visual_audio_asset_results("job_1", "demo", set())
    assert results == []
