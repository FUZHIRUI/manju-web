#!/usr/bin/env python3
"""
结果收集器

负责收集前端/服务端执行时的各种结果，包括：
- API响应数据
- 日志文件
- 产物文件
- 截图
- 性能指标
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class ResultCollector:
    """结果收集器"""
    
    def __init__(self, config):
        self.config = config
        self.collected_data: Dict[str, Any] = {
            "api_responses": [],
            "logs": [],
            "artifacts": [],
            "screenshots": [],
            "performance": []
        }
        
    def collect_api_response(self, endpoint: str, response: requests.Response, step_name: str):
        """收集API响应"""
        self.collected_data["api_responses"].append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "endpoint": endpoint,
            "status_code": response.status_code,
            "response_body": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:1000],
            "response_time_ms": response.elapsed.total_seconds() * 1000
        })
    
    def collect_logs(self, step_name: str, log_patterns: List[str] = None) -> List[str]:
        """收集相关日志"""
        logs = []
        log_dir = Path("logs")
        
        if not log_dir.exists():
            return logs
        
        # 获取最新的日志文件
        log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        for log_file in log_files[:5]:  # 最近5个日志文件
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                    # 如果指定了模式，只收集匹配的日志
                    if log_patterns:
                        for pattern in log_patterns:
                            if pattern in content:
                                logs.append({
                                    "file": str(log_file.name),
                                    "pattern": pattern,
                                    "content": self._extract_relevant_lines(content, pattern)
                                })
                    else:
                        # 收集最后100行
                        lines = content.splitlines()
                        logs.append({
                            "file": str(log_file.name),
                            "content": "\n".join(lines[-100:])
                        })
                        
            except Exception as e:
                logs.append({
                    "file": str(log_file.name),
                    "error": str(e)
                })
        
        self.collected_data["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "logs": logs
        })
        
        return logs
    
    def collect_artifacts(self, step_name: str, artifact_paths: List[str]):
        """收集产物文件信息"""
        artifacts = []
        
        for path_pattern in artifact_paths:
            full_path = Path(f"manju_output/{self.config.project_name}/{path_pattern}")
            
            if full_path.is_file():
                artifacts.append({
                    "path": str(full_path),
                    "type": "file",
                    "size": full_path.stat().st_size,
                    "modified": datetime.fromtimestamp(full_path.stat().st_mtime).isoformat()
                })
            elif full_path.is_dir():
                files = list(full_path.glob("*"))
                artifacts.append({
                    "path": str(full_path),
                    "type": "directory",
                    "file_count": len(files),
                    "files": [str(f.name) for f in files[:10]]  # 前10个文件
                })
            else:
                artifacts.append({
                    "path": str(full_path),
                    "type": "missing",
                    "error": "File or directory not found"
                })
        
        self.collected_data["artifacts"].append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "artifacts": artifacts
        })
        
        return artifacts
    
    def collect_screenshot(self, step_name: str, screenshot_path: str):
        """收集截图"""
        self.collected_data["screenshots"].append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "path": screenshot_path
        })
    
    def collect_performance_metrics(self, step_name: str, metrics: Dict[str, Any]):
        """收集性能指标"""
        self.collected_data["performance"].append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "metrics": metrics
        })
    
    def get_flow_status(self) -> Dict:
        """获取当前flow状态"""
        try:
            response = requests.get(
                f"{self.config.base_url}/api/projects/{self.config.project_name}/flow-status"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_job_status(self, job_id: str) -> Dict:
        """获取job状态"""
        try:
            response = requests.get(
                f"{self.config.base_url}/api/jobs/{job_id}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """生成执行报告"""
        report = {
            "project": self.config.project_name,
            "generated_at": datetime.now().isoformat(),
            "summary": self._generate_summary(),
            "data": self.collected_data
        }
        
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return str(output_file)
        
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    def _generate_summary(self) -> Dict:
        """生成摘要"""
        api_count = len(self.collected_data["api_responses"])
        error_count = sum(
            1 for r in self.collected_data["api_responses"]
            if r.get("status_code", 200) >= 400
        )
        
        artifact_count = len(self.collected_data["artifacts"])
        screenshot_count = len(self.collected_data["screenshots"])
        
        return {
            "total_api_calls": api_count,
            "failed_api_calls": error_count,
            "total_artifacts_checked": artifact_count,
            "total_screenshots": screenshot_count
        }
    
    def _extract_relevant_lines(self, content: str, pattern: str, context_lines: int = 5) -> str:
        """提取包含模式的行及其上下文"""
        lines = content.splitlines()
        result = []
        
        for i, line in enumerate(lines):
            if pattern in line:
                # 添加上下文
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                result.extend(lines[start:end])
                result.append("---")
        
        return "\n".join(result[-100:])  # 最多返回100行
