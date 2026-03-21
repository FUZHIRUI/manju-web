# Video Workflow Phase Refactor

## Goal

Refactor the video workflow to support per-phase execution via `phase` parameter, matching the established fenjing pattern. Users should be able to independently trigger "prepare prompts" and "generate videos" steps from the frontend.

## Requirements

- Add `phase` parameter support to `run_video` workflow (tokens: `prepare_prompts`, `generate_videos`, `all`)
- Extract two new async functions from `run_video_workflow_multi` in video.py
- Update job_handler.py for phase routing, step resolution, and reset_steps logic
- Fix missing `_rollup_video_steps` call in `mark_step_completed`
- Replace single video button with two-button phase UI in frontend

## Step Mapping

| Step token (phase 参数值) | 内部 steps 标记 | 前端按钮 |
|---|---|---|
| `prepare_prompts` | `prepare` + `phase1_video_prompts` | "第一步：视频提示词生成" |
| `generate_videos` | `phase2_video_generation` | "第二步：视频生成" |
| `upload_videos` | `fenjing_video_upload` | "第三步：上传" |
| `all` (default) | All 4 steps | （顺序执行全部） |

## Acceptance Criteria

- [ ] `POST /run/video` with no body behaves identically to current (backward compat)
- [ ] `POST /run/video {"phase":"prepare_prompts"}` runs only prepare+prompts, marks first 2 steps completed
- [ ] `POST /run/video {"phase":"generate_videos"}` runs only generation (download to local, skip TOS upload), marks `phase2_video_generation` completed
- [ ] `POST /run/video {"phase":"upload_videos"}` uploads local MP4s to TOS, marks `fenjing_video_upload` completed
- [ ] Frontend shows three buttons with correct status per step
- [ ] `_rollup_video_steps` enforces sequential ordering after `mark_step_completed`
- [ ] Partial failure handling preserved for `phase2_video_generation`

## Technical Notes

- Keep existing step names in `_FLOW_STEPS` (no migration needed)
- Keep `run_video_workflow_multi` intact for `phase="all"` path
- `process_single_video_independent` 增加 `skip_upload` 参数，拆分下载与上传
- 新增 `run_video_upload_only` 扫描本地已下载 MP4 并上传 TOS
- For standalone `generate_videos` step, discover ready chapters by scanning for existing `shipin_prompts.jsonl` files
- Reference implementation: `run_fenjing` in workflow_service.py:337-415
