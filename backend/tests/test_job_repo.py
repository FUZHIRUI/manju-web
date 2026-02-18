from pathlib import Path
from typing import Dict

from manju_web.backend.repositories import job_repo


def test_start_update_and_list_jobs(
    project_output_dir: Path, job_repo_state: Path
) -> None:
    def runner(job_id: str) -> None:
        return None

    job = job_repo.start_job("auto_storyboard", "demo", runner, {"k": "v"})
    assert job["status"] == "running"
    job_repo.update_job(job["id"], status="success")
    listed = job_repo.list_jobs_for_project("demo")
    assert listed and listed[0]["status"] == "success"
    assert "log_tail" in listed[0]


def test_find_job_on_disk(project_output_dir: Path, job_repo_state: Path) -> None:
    def runner(job_id: str) -> None:
        return None

    job = job_repo.start_job("video", "demo", runner, {})
    job_id = job["id"]
    found = job_repo.find_job_on_disk(job_id)
    assert found and found["id"] == job_id


def test_log_path_resolution(job_repo_state: Path) -> None:
    log_path = job_repo.build_log_path("abc")
    resolved = job_repo.resolve_log_path(log_path)
    # 边界：相对路径应被规范化为绝对路径
    assert resolved.is_absolute()


def test_update_job_missing(job_repo_state: Path) -> None:
    # 边界：更新不存在作业应为无副作用
    job_repo.update_job("missing", status="failed")
    assert job_repo.get_job("missing") is None
