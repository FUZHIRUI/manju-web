from manju_web.backend.services import status_service


def test_visual_audio_cloth_changed_phase_complete() -> None:
    project = "demo"
    status_service.update_from_event(
        flow="visual_audio_assets",
        event="phase_complete",
        level="INFO",
        step="cloth_changed",
        phase=None,
        project=project,
    )
    state = status_service.get_flow_state(project)
    steps = state.get("flows", {}).get("visual_audio_assets", {}).get("steps", {})
    assert steps.get("cloth_changed") == "completed"


def test_reset_visual_audio_steps_except() -> None:
    project = "demo_reset"
    status_service.update_step_status(project, "visual_audio_assets", "download_assets", "running")
    status_service.update_step_status(project, "visual_audio_assets", "cloth_images", "running")
    status_service.update_step_status(project, "visual_audio_assets", "cloth_changed", "completed")
    status_service.reset_visual_audio_steps_except(project, ["cloth_changed"])
    state = status_service.get_flow_state(project)
    steps = state.get("flows", {}).get("visual_audio_assets", {}).get("steps", {})
    assert steps.get("cloth_changed") == "completed"
    assert steps.get("cloth_images") == "waiting"
    assert steps.get("download_assets") == "waiting"
