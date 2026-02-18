import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..repositories import asset_repo, media_repo, project_repo
from . import config_service


def _apply_project_runtime(project: str) -> None:
    """
    应用项目运行时配置（线程安全版本）
    
    【重要说明】
    不再修改全局环境变量 PROJECT_NAME，以避免线程安全问题
    """
    # 注意：不再设置 os.environ["PROJECT_NAME"]
    os.environ["MANJU_OUTPUT_DIR"] = str(project_repo.OUTPUT_DIR)
    config_service.apply_runtime(project)


def list_projects() -> List[str]:
    return project_repo.list_projects()


def ensure_project(project: str) -> Dict[str, Any]:
    return project_repo.ensure_project_dirs(project)


def list_project_assets(project: str) -> Dict[str, Any]:
    return asset_repo.list_project_assets(project)


def resolve_media_path(project: str, raw_path: str) -> Optional[Path]:
    return media_repo.resolve_media_path(project, raw_path)


def save_novel(project: str, novel_text: str, novel_path: Optional[str]) -> Dict[str, Any]:
    base_dir = project_repo.project_base_dir(project)
    if novel_path:
        path = Path(novel_path)
        if not path.is_absolute():
            path = base_dir / path
    else:
        path = base_dir / "novel.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(novel_text, encoding="utf-8")
    return {"ok": True, "path": str(path)}


def update_fenjing_prompt(project: str, chapter_name: str, fenjing_id: str, prompt_text: str) -> Dict[str, Any]:
    return asset_repo.update_fenjing_prompt(project, chapter_name, fenjing_id, prompt_text)


def update_video_prompt(project: str, chapter_name: str, fenjing_id: str, prompt_text: str) -> Dict[str, Any]:
    return asset_repo.update_video_prompt(project, chapter_name, fenjing_id, prompt_text)


def update_character_prompt(project: str, character_id: str, prompt_text: str) -> Dict[str, Any]:
    return asset_repo.update_character_prompt(project, character_id, prompt_text)


def update_cloth_changed_prompt(project: str, character_id: str, outfit_id: str, prompt_text: str) -> Dict[str, Any]:
    return asset_repo.update_cloth_changed_prompt(project, character_id, outfit_id, prompt_text)


def publish_character_candidate(project: str, character_id: str, candidate_rel: str) -> Dict[str, Any]:
    return asset_repo.publish_character_candidate(project, character_id, candidate_rel)


def publish_cloth_changed_candidate(project: str, character_id: str, outfit_id: str, candidate_rel: str) -> Dict[str, Any]:
    return asset_repo.publish_cloth_changed_candidate(project, character_id, outfit_id, candidate_rel)


def publish_fenjing_candidate(project: str, chapter_name: str, fenjing_id: str, candidate_rel: str) -> Dict[str, Any]:
    return asset_repo.publish_fenjing_candidate(project, chapter_name, fenjing_id, candidate_rel)


def publish_video_candidate(project: str, chapter_name: str, candidate_rel: str) -> Dict[str, Any]:
    return asset_repo.publish_video_candidate(project, chapter_name, candidate_rel)


def delete_candidate_file(project: str, candidate_rel: str, required_dir: str) -> Dict[str, Any]:
    return asset_repo.delete_candidate_file(project, candidate_rel, required_dir)


def delete_video_candidate(project: str, candidate_rel: str) -> Dict[str, Any]:
    return asset_repo.delete_video_candidate(project, candidate_rel)


def clean_stage_assets(project: str, flow: str) -> Dict[str, Any]:
    _apply_project_runtime(project)
    return asset_repo.clean_stage_assets(project, flow)


def clean_visual_audio_assets_by_phase(project: str, phase: str) -> Dict[str, Any]:
    _apply_project_runtime(project)
    return asset_repo.clean_visual_audio_assets_by_phase(project, phase)
