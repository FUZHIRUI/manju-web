from manju_web.backend.services.workflow_runtime import visual_audio_assets


def test_is_full_phase_run_true() -> None:
    phases = {
        "download_assets",
        "build_prompts",
        "generate_images",
        "generate_tts",
        "cloth_images",
        "cloth_changed",
        "upload_assets",
    }
    assert visual_audio_assets.is_full_phase_run(phases) is True


def test_is_full_phase_run_false_for_partial() -> None:
    phases = {"build_prompts"}
    assert visual_audio_assets.is_full_phase_run(phases) is False
