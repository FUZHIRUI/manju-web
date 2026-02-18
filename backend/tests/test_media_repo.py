from pathlib import Path

from manju_web.backend.repositories import media_repo, project_repo


def test_resolve_media_path(project_output_dir: Path) -> None:
    base = project_repo.project_base_dir("demo")
    base.mkdir(parents=True, exist_ok=True)
    file_path = base / "a.txt"
    file_path.write_text("ok", encoding="utf-8")
    resolved = media_repo.resolve_media_path("demo", "a.txt")
    # 边界：合法相对路径应解析为项目内绝对路径
    assert resolved == file_path
    blocked = media_repo.resolve_media_path("demo", "../outside.txt")
    # 边界：目录穿越路径应被拒绝
    assert blocked is None
