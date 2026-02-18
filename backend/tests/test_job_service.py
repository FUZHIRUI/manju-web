from pathlib import Path
from typing import Dict

from manju_web.backend.repositories import job_repo
from manju_web.backend.services import job_service


def test_job_service_get_from_disk(
    project_output_dir: Path, job_repo_state: Path
) -> None:
    def runner(job_id: str) -> None:
        return None

    job = job_repo.start_job("auto_storyboard", "demo", runner, {})
    fetched = job_service.get_job(job["id"])
    assert fetched and fetched["id"] == job["id"]


def test_job_service_list(project_output_dir: Path, job_repo_state: Path) -> None:
    def runner(job_id: str) -> None:
        return None

    job_repo.start_job("video", "demo", runner, {})
    jobs = job_service.list_jobs("demo")
    # 边界：列表接口应返回非空结果
    assert jobs
