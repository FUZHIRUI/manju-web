from pathlib import Path
from typing import List

from manju_web.backend.repositories import project_repo


def test_safe_project_name() -> None:
    # 边界：合法/非法/空项目名应被正确筛选
    assert project_repo.safe_project_name("demo_1") == "demo_1"
    assert project_repo.safe_project_name(" demo ") == "demo"
    assert project_repo.safe_project_name("invalid/name") is None
    assert project_repo.safe_project_name("") is None


def test_project_dirs(project_output_dir: Path) -> None:
    result = project_repo.ensure_project_dirs("demo")
    # 边界：创建项目目录应完整生成必要子目录
    assert Path(result["base"]).exists()
    assert Path(result["assets"]).exists()
    assert Path(result["storyboards"]).exists()


def test_list_files_and_relative(project_output_dir: Path) -> None:
    base = project_repo.project_base_dir("demo")
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.json").write_text("{}", encoding="utf-8")
    (base / "b.txt").write_text("ok", encoding="utf-8")
    files = project_repo.list_files(base, exts=(".json",))
    # 边界：文件过滤应仅返回指定后缀
    assert files and files[0].endswith("a.json")
    rel = project_repo.to_project_relative("demo", base / "a.json")
    # 边界：项目内路径应转换为相对路径
    assert rel == "a.json"
    outside = project_repo.to_project_relative("demo", Path("/tmp/not_in_project"))
    # 边界：项目外路径应返回空字符串
    assert outside == ""
