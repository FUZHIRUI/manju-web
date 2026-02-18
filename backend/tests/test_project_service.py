from pathlib import Path

from manju_web.backend.services import project_service


def test_project_service_ensure(project_output_dir: Path) -> None:
    result = project_service.ensure_project("demo")
    # 边界：服务层创建项目应确保目录存在
    assert Path(result["base"]).exists()


def test_project_service_list(project_output_dir: Path) -> None:
    project_service.ensure_project("demo")
    projects = project_service.list_projects()
    # 边界：列表接口应包含已创建的项目
    assert "demo" in projects
