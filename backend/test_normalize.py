#!/usr/bin/env python3
import json
from copy import deepcopy

# 新的步骤定义
_FLOW_STEPS = {
    "auto_storyboard": [
        "step1",
        "step1_extract",
        "step2",
        "step2_storyboard",
        "step3_upload",
        "step3_upload_assets",
    ],
}

_STATUS_WAITING = "waiting"

def _default_flow_state(project):
    flows = {}
    for flow, steps in _FLOW_STEPS.items():
        flows[flow] = {
            "status": _STATUS_WAITING,
            "steps": {step: _STATUS_WAITING for step in steps},
        }
    return {"project": project, "updated_at": 1234567890, "flows": flows}

def _normalize_state(project, data):
    base = _default_flow_state(project)
    if not isinstance(data, dict):
        return base
    flows = data.get("flows") if isinstance(data.get("flows"), dict) else {}
    merged = deepcopy(base)
    merged["updated_at"] = data.get("updated_at", merged["updated_at"])
    
    for flow, flow_data in flows.items():
        if flow not in merged["flows"] or not isinstance(flow_data, dict):
            continue
        merged_flow = merged["flows"][flow]
        status = flow_data.get("status")
        if isinstance(status, str):
            merged_flow["status"] = status
        
        steps = flow_data.get("steps") if isinstance(flow_data.get("steps"), dict) else {}
        
        # 兼容旧状态：先将旧步骤名称映射为新步骤名称
        if flow == "auto_storyboard":
            step_mapping = {
                "phase1": ["step1", "step1_extract"],
                "phase2": ["step2", "step2_storyboard"],
                "upload": ["step3_upload", "step3_upload_assets"],
            }
            
            converted_steps = {}
            for old_step, new_steps in step_mapping.items():
                if old_step in steps:
                    for new_step in new_steps:
                        converted_steps[new_step] = steps[old_step]
            
            print(f"Converted steps: {converted_steps}")
            
            for step, step_status in converted_steps.items():
                if step in merged_flow["steps"] and isinstance(step_status, str):
                    merged_flow["steps"][step] = step_status
        
        for step, step_status in steps.items():
            if step in merged_flow["steps"] and isinstance(step_status, str):
                merged_flow["steps"][step] = step_status
    
    return merged

# 测试
old_state = {
    "project": "test",
    "updated_at": 1234567890,
    "flows": {
        "auto_storyboard": {
            "status": "completed",
            "steps": {
                "phase1": "completed",
                "phase2": "completed",
                "upload": "waiting"
            }
        }
    }
}

print("Old state steps:")
print(json.dumps(old_state["flows"]["auto_storyboard"]["steps"], indent=2))

result = _normalize_state("test", old_state)

print("\nNormalized state steps:")
print(json.dumps(result["flows"]["auto_storyboard"]["steps"], indent=2))

print("\nAre they equal?", old_state == result)
