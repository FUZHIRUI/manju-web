# E2E Testing Guide

> End-to-end testing guidelines for Manju Web workflow using Playwright and VLM verification.

---

## Overview

This guide documents the E2E testing approach for the Manju Web application, which uses:
- **Playwright** for browser automation
- **VLM (Vision Language Model)** for screenshot verification
- **18-step workflow** covering the complete pipeline from project creation to video generation

---

## Test Architecture

### Workflow Overview

The E2E test covers 18 steps across 6 phases:

```
Phase 1: Project Creation & Storyboard Setup (Steps 1-2)
├── Step 1: Create new project
└── Step 2: Upload novel and execute storyboard analysis (step1)

Phase 2: Storyboard Generation (Steps 3-4)
├── Step 3: Execute storyboard generation (step2)
└── Step 4: Confirm storyboard files generated

Phase 3: Asset Upload (Step 5)
└── Step 5: Upload assets to TOS (step3_upload)

Phase 4: Character & Asset Generation (Steps 6-10)
├── Step 6: Generate prompts (character_prompts, location_prompts, fenjing_prompts)
├── Step 7: Generate images (character_images, location_images)
├── Step 8: Generate TTS audio
├── Step 9: Costume change (cloth_images, cloth_changed)
└── Step 10: Upload assets (visual_audio_assets)

Phase 5: Fenjing Image Generation (Steps 11-13)
├── Step 11: Click "Generate Storyboard Images" button
├── Step 12: Click task card to execute Fenjing
└── Step 13: Wait for Fenjing generation to complete

Phase 6: Video Generation (Steps 14-19)
├── Step 14: Click "Generate Video" button
├── Step 15: Click task card to execute video generation
├── Step 16: Navigate to Videos page to observe generation process
├── Step 17: Observe video product generation
├── Step 18: Verify task completion
└── Step 19: Refresh and verify state consistency
```

### Core Components

#### 1. e2e_test.py (VLM Validator)

**Purpose**: Execute a single step and validate results using VLM.

**Key Features**:
- Launch Playwright browser
- Execute frontend operations (click buttons, fill forms)
- Capture before/execution/after screenshots
- Call VLM model to analyze screenshots
- Output validation results

**Usage**:
```bash
python scripts/e2e_test.py \
    --mode vlm \
    --project "e2e_test_$(date +%Y%m%d_%H%M%S)" \
    --base-url http://127.0.0.1:8086 \
    --vlm-base-url https://ark.cn-beijing.volces.com/api/v3 \
    --api-key YOUR_API_KEY \
    --model ep-20260215001006-86n7g \
    --flow auto_storyboard \
    --phase step1 \
    --action-label "步骤 1" \
    --wait-steps step1 \
    --novel-path /path/to/novel.txt \
    --chapter-size 2500 \
    --vlm-task extract
```

#### 2. PlaywrightController

**Purpose**: Frontend simulation controller that simulates user click operations.

**Key Features**:
- Click "Generate Storyboard Images" button
- Click "Generate Video" button
- Click task card execute button
- Screenshot validation for page state

#### 3. Screenshot Collection

**Screenshot Save Path**:
```
manju_output/{project_name}/screenshots/
├── {action_name}_before_{timestamp}.png      # Before execution
├── {action_name}_after_{timestamp}.png       # After execution
└── {action_name}_refresh_{timestamp}.png     # After refresh
```

---

## VLM Verification Modes

### VLM Task Types

#### 1. extract Mode

Extract task card information:

```bash
--vlm-task extract
```

Output JSON format:
```json
{
  "flow": "auto_storyboard",
  "project": "e2e_test_project",
  "steps": [
    {"label": "阶段 1", "status": "completed", "progress": ""},
    {"label": "阶段 2", "status": "waiting", "progress": ""}
  ]
}
```

#### 2. check Mode

Verify if page state matches expected:

```bash
--vlm-task check
```

Output JSON format:
```json
{
  "passed": true,
  "details": "阶段1已完成，阶段2等待中，符合预期",
  "evidence": "截图显示阶段1按钮为'重生'，阶段2按钮可点击"
}
```

### VLM Fallback Mechanism

When conventional Playwright click operations fail (e.g., button text changes, layout adjustments), the skill automatically enables the **VLM fallback mechanism**:

```
Conventional click fails → Screenshot → VLM analysis → Get button position → Execute click
```

**Workflow**:
1. Try to click using preset button text
2. If failed, capture current page screenshot
3. Call VLM to analyze screenshot, identify target button's accurate text and position
4. Try to click according to VLM guidance (supports alternative buttons)
5. Return click result and VLM analysis details

**VLM Return Format**:
```json
{
  "analysis": "Page analysis summary",
  "target_button_text": "Button accurate text",
  "target_button_location": "Button position description",
  "alternative_buttons": ["Alternative 1", "Alternative 2"],
  "confidence": "high/medium/low",
  "reasoning": "Reason for selecting this button"
}
```

**Advantages**:
- Adapt to frontend UI changes without modifying skills
- Automatically handle button text and position changes
- Support alternative solutions, improving success rate
- Disable thinking mode for faster response

### VLM Verification Points

| Step | VLM Verification Content |
|------|-------------------------|
| Step 2 | Step 1 button becomes "重生", Step 2 button is clickable |
| Step 3 | Step 1 and 2 buttons become "重生", Step 3 button is clickable |
| Step 5 | Step 1/2/3 buttons are grayed out, upload asset status is completed |
| Step 6 | Prompt button is grayed out, prepare asset/character prompt/location prompt/fenjing prompt are completed |
| Step 7 | Prompt and generate buttons are grayed out, character image/location image are completed |
| Step 8 | Prompt/generate/TTS buttons are grayed out, TTS audio is completed |
| Step 9 | Costume change button is grayed out, costume and change are completed |
| Step 10 | Upload button is grayed out, upload asset is completed |
| Step 11-12 | Task card status changes from waiting to running |
| Step 13 | Storyboard generation task status is completed |
| Step 14-15 | Video generation task card status changes from waiting to running |
| Step 16 | Videos page left side shows storyboard prompts |
| Step 17 | Videos page right side shows video thumbnails |
| Step 18 | Batch page video generation task status is completed |
| Step 19 | State remains consistent after refresh |

---

## Error Handling

### Automatic Recovery (Handled Automatically by Skill)

| Issue | What Skill Does Automatically |
|-------|--------------------------------|
| Browser opens but accessing link fails | Service crash, call bug repair sub-agent and skill for deep problem location |
| After a step, page is accessible but status is failed | Retry 2 times, if still fail, call bug repair sub-agent skill to locate problem first, then confirm with user whether to fix |
| Service not running (Connection refused) | Automatically restart service |
| Timeout | Retry with doubled timeout |
| TOS Presign failed | Check TOS configuration |

### Manual Intervention (Call bug-fixer)

| Issue | What Skill Does Automatically |
|-------|--------------------------------|
| Print I/O error (I/O operation on closed file) | Generate bug report, suggest calling bug-fixer |
| State reset error (completed becomes running) | Generate bug report, suggest calling bug-fixer |
| After code fix | Manual confirmation of subsequent operations |

### Bug Report Contents

- Problem type and severity
- Diagnostic details (logs, screenshots, API responses)
- Suggested operations
- Related file list
- Report save path

---

## Configuration Options

### Command Line Parameters

```python
# e2e_test.py parameter description
--mode vlm                    # Use VLM verification mode
--project PROJECT_NAME        # Project name
--base-url URL               # Backend service address
--vlm-base-url URL           # VLM service address
--api-key KEY                # API key
--model MODEL                # VLM model name
--flow FLOW                  # Flow name (auto_storyboard/visual_audio_assets/fenjing/video)
--phase PHASE                # Phase name (step1/step2/step3_upload/build_prompts/generate_images/generate_tts/cloth_changed/upload_assets)
--action-label LABEL         # Operation button label (步骤 1/步骤 2/步骤 3/第一步：提示词/第二步：生成/第二步：TTS语音/第三步：换装/第四步：上传)
--wait-steps STEPS           # Steps to wait for completion, comma separated
--wait-timeout SECONDS       # Wait timeout (default 120 seconds)
--novel-path PATH            # Novel file path
--chapter-size SIZE          # Chapter word count (used by phase1)
--per-chapter-shots NUM      # Shots per chapter (used by phase2)
--vlm-task TASK              # VLM task type (extract/check)
--headless                   # Run in headless mode
```

### Authentication Configuration

VLM service requires the following environment variables or parameters:
- `ARK_API_KEY`: API key
- `ARK_VLM_MODEL`: VLM model name
- `ARK_VLM_BASE_URL`: VLM service base URL

Default configuration:
- API Key: `58556eed-a35b-4e01-a30c-6736894afb42`
- Model: `ep-20260215001006-86n7g`
- Base URL: `https://ark.cn-beijing.volces.com/api/v3`

---

## Best Practices

### 1. Service Startup

Always ensure the service is running before starting tests:

```bash
# Kill any existing service on port 8086
kill -9 $(lsof -t -i :8086)

# Start the service
cd /Users/bytedance/Desktop/常见python/manju_web/backend && python server.py > logs/server_latest.log 2>&1 &
```

### 2. Create New Project for Each Test Run

Always create a new project with timestamp when starting from step 1:

```bash
--project "e2e_test_$(date +%Y%m%d_%H%M%S)"
```

### 3. Screenshot Verification

Always use VLM to verify screenshots at key steps:
- Before and after clicking buttons
- After waiting for steps to complete
- When verifying page state changes

### 4. Timeout Handling

Set appropriate timeouts based on operation:
- Simple API calls: 30 seconds
- Storyboard generation: 5 minutes
- Image generation: 10 minutes
- Video generation: 20 minutes

### 5. Debugging Failed Tests

When a test fails:
1. Check the screenshot in `manju_output/{project}/screenshots/`
2. Review the API response and logs
3. Use VLM to analyze the screenshot for issues
4. Check if the service is still running

---

## Reference Documents

- [Full Test Plan](/Users/bytedance/Desktop/常见python/manju_web/requirments_doc/full_workflow_e2e_test_plan.md) - Original requirements document
- [e2e_test.py](/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/scripts/e2e_test.py) - VLM validation execution script
- [playwright_controller.py](/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/scripts/playwright_controller.py) - Frontend controller

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Reusing projects across test runs | State pollution, unpredictable results | Create new project with timestamp for each test run |
| Not waiting for `networkidle` | DOM not fully loaded, selectors fail | Always wait for `networkidle` before inspecting DOM |
| Hardcoded timeouts | Flaky tests due to network variability | Use progressive timeouts (30s → 5min → 20min based on operation) |
| Not capturing screenshots | Hard to debug failures | Always capture before/after/refresh screenshots |
| Running without service check | Tests fail immediately with connection refused | Verify service health before starting tests |
| Manual verification only | Slow, inconsistent, human error prone | Use VLM for automated screenshot verification |

---

## Common Mistakes

1. **Forgetting to wait for networkidle** - DOM might not be fully rendered
2. **Using hardcoded project names** - Causes conflicts between test runs
3. **Not handling timeouts properly** - Network latency causes test flakiness
4. **Skipping screenshot verification** - Hard to debug when tests fail
5. **Not checking service status first** - Wastes time if service isn't running
6. **Using wrong flow/phase names** - Causes API errors
7. **Not verifying file existence** - Tests pass even when outputs are missing
8. **Hardcoding API keys in scripts** - Security risk, use environment variables

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Frontend organization
- [Component Guidelines](./component-guidelines.md) - UI component patterns
- [Quality Guidelines](./quality-guidelines.md) - Code quality standards
- [Backend Testing Guide](../backend/testing-guide.md) - Backend testing patterns
