#!/usr/bin/env python3
"""
异常处理器

负责处理执行过程中的异常，包括：
1. 诊断问题原因
2. 尝试自动恢复
3. 与bug fix技能联动进行深度排查
4. 生成bug报告
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests


class ExceptionHandler:
    """异常处理器"""
    
    # 已知问题及其恢复策略
    KNOWN_ISSUES = {
        "service_not_running": {
            "patterns": ["Connection refused", "ConnectionError"],
            "recoverable": True,
            "recovery_action": "restart_service"
        },
        "timeout": {
            "patterns": ["Timeout", "timeout"],
            "recoverable": True,
            "recovery_action": "increase_timeout"
        },
        "authentication_error": {
            "patterns": ["401", "Unauthorized", "鉴权失败"],
            "recoverable": False,
            "recovery_action": None
        },
        "tos_presign_failed": {
            "patterns": ["Failed to get presigned URL", "presign"],
            "recoverable": True,
            "recovery_action": "check_tos_config"
        },
        "print_io_error": {
            "patterns": ["I/O operation on closed file", "ValueError.*closed"],
            "recoverable": False,
            "recovery_action": None,
            "requires_bug_fix": True
        },
        "state_reset_error": {
            "patterns": ["状态重置", "completed.*running"],
            "recoverable": False,
            "recovery_action": None,
            "requires_bug_fix": True
        }
    }
    
    def __init__(self, config):
        self.config = config
        self.diagnosis_history: List[Dict] = []
        
    def diagnose(self, step: Dict[str, Any], result: Any) -> Dict[str, Any]:
        """
        诊断问题原因
        
        Returns:
            {
                "issue_type": str,
                "recoverable": bool,
                "recovery_action": Optional[Callable],
                "requires_bug_fix": bool,
                "diagnosis_details": Dict
            }
        """
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "step": step.get("name", "unknown"),
            "issue_type": "unknown",
            "recoverable": False,
            "recovery_action": None,
            "requires_bug_fix": False,
            "diagnosis_details": {}
        }
        
        # 收集错误信息
        errors = result.errors if hasattr(result, "errors") else []
        error_text = " ".join(errors) if errors else ""
        
        # 检查日志
        logs = self._collect_relevant_logs(step, error_text)
        diagnosis["diagnosis_details"]["logs"] = logs
        
        # 匹配已知问题
        for issue_type, issue_config in self.KNOWN_ISSUES.items():
            if self._match_patterns(error_text, issue_config["patterns"]):
                diagnosis["issue_type"] = issue_type
                diagnosis["recoverable"] = issue_config["recoverable"]
                diagnosis["requires_bug_fix"] = issue_config.get("requires_bug_fix", False)
                
                # 获取恢复动作
                recovery_action_name = issue_config.get("recovery_action")
                if recovery_action_name:
                    diagnosis["recovery_action"] = getattr(self, recovery_action_name, None)
                
                break
        
        # 如果无法识别，进行深度分析
        if diagnosis["issue_type"] == "unknown":
            diagnosis = self._deep_analysis(step, result, diagnosis)
        
        self.diagnosis_history.append(diagnosis)
        return diagnosis
    
    def _match_patterns(self, text: str, patterns: List[str]) -> bool:
        """匹配错误模式"""
        text_lower = text.lower()
        for pattern in patterns:
            if pattern.lower() in text_lower:
                return True
        return False
    
    def _collect_relevant_logs(self, step: Dict[str, Any], error_text: str) -> List[str]:
        """收集相关日志"""
        logs = []
        log_dir = Path("logs")
        
        if not log_dir.exists():
            return logs
        
        # 获取最新的日志文件
        log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        for log_file in log_files[:3]:  # 最近3个日志文件
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                    # 查找包含错误信息的行
                    if any(pattern in content for pattern in ["ERROR", "Exception", "Traceback"]):
                        lines = content.splitlines()
                        relevant_lines = []
                        
                        for i, line in enumerate(lines):
                            if "ERROR" in line or "Exception" in line or "Traceback" in line:
                                # 提取上下文
                                start = max(0, i - 3)
                                end = min(len(lines), i + 10)
                                relevant_lines.extend(lines[start:end])
                                relevant_lines.append("---")
                        
                        if relevant_lines:
                            logs.append({
                                "file": str(log_file.name),
                                "content": "\n".join(relevant_lines[-50:])  # 最多50行
                            })
                            
            except Exception:
                pass
        
        return logs
    
    def _deep_analysis(self, step: Dict[str, Any], result: Any, diagnosis: Dict) -> Dict:
        """深度分析问题"""
        # 检查服务状态
        service_status = self._check_service_status()
        diagnosis["diagnosis_details"]["service_status"] = service_status
        
        # 检查磁盘空间
        disk_status = self._check_disk_space()
        diagnosis["diagnosis_details"]["disk_status"] = disk_status
        
        # 检查网络连接
        network_status = self._check_network()
        diagnosis["diagnosis_details"]["network_status"] = network_status
        
        return diagnosis
    
    def _check_service_status(self) -> Dict:
        """检查服务状态"""
        try:
            response = requests.get(f"{self.config.base_url}/api/projects", timeout=5)
            return {
                "running": response.status_code == 200,
                "status_code": response.status_code
            }
        except Exception as e:
            return {
                "running": False,
                "error": str(e)
            }
    
    def _check_disk_space(self) -> Dict:
        """检查磁盘空间"""
        try:
            result = subprocess.run(
                ["df", "-h", "."],
                capture_output=True,
                text=True
            )
            return {
                "output": result.stdout,
                "available": "available" in result.stdout.lower()
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _check_network(self) -> Dict:
        """检查网络连接"""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "127.0.0.1"],
                capture_output=True,
                text=True
            )
            return {
                "reachable": result.returncode == 0
            }
        except Exception as e:
            return {"error": str(e)}
    
    # ========== 恢复动作 ==========
    
    def restart_service(self) -> bool:
        """重启服务"""
        try:
            print("🔄 尝试重启服务...")
            
            # 从base_url解析端口
            import urllib.parse
            parsed = urllib.parse.urlparse(self.config.base_url)
            port = parsed.port or 8086
            
            # 查找并杀死现有进程
            subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True
            )
            subprocess.run(
                ["kill", "-9"],
                capture_output=True
            )
            
            # 等待进程终止
            import time
            time.sleep(2)
            
            # 尝试从配置或环境变量获取backend路径
            backend_path = getattr(self.config, 'backend_path', None)
            if not backend_path:
                # 尝试从当前工作目录推断
                cwd = Path.cwd()
                if (cwd / "backend" / "server.py").exists():
                    backend_path = cwd / "backend"
                elif (cwd.parent / "backend" / "server.py").exists():
                    backend_path = cwd.parent / "backend"
                else:
                    print("❌ 无法找到backend目录，请配置backend_path")
                    return False
            
            # 启动新进程
            subprocess.Popen(
                ["python", "server.py"],
                cwd=str(backend_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # 等待服务启动
            time.sleep(3)
            
            # 验证服务是否启动
            response = requests.get(f"{self.config.base_url}/api/projects", timeout=5)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ 重启服务失败: {e}")
            return False
    
    def increase_timeout(self) -> bool:
        """增加超时时间"""
        print("🔄 增加超时时间...")
        self.config.timeout_seconds *= 2
        return True
    
    def check_tos_config(self) -> bool:
        """检查TOS配置"""
        print("🔄 检查TOS配置...")
        # 这里可以添加检查TOS配置的代码
        return True
    
    # ========== Bug Fix 联动 ==========
    
    def invoke_bug_fix_skill(self, diagnosis: Dict) -> Dict:
        """
        调用bug fix技能进行深度排查
        
        这会触发bug-fixer技能，进行：
        1. 日志深度分析
        2. 代码审查
        3. 状态监控
        4. 根因定位
        """
        print("🔍 调用bug fix技能进行深度排查...")
        
        # 生成bug报告
        bug_report = self._generate_bug_report(diagnosis)
        
        # 保存报告
        report_path = Path(f"manju_output/{self.config.project_name}/bug_reports")
        report_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_path / f"bug_report_{timestamp}.json"
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(bug_report, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Bug报告已保存: {report_file}")
        
        return {
            "report_path": str(report_file),
            "report": bug_report,
            "recommendation": "请使用bug-fixer技能进行进一步排查"
        }
    
    def _generate_bug_report(self, diagnosis: Dict) -> Dict:
        """生成bug报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "project": self.config.project_name,
            "issue_type": diagnosis["issue_type"],
            "step": diagnosis["step"],
            "recoverable": diagnosis["recoverable"],
            "diagnosis_details": diagnosis["diagnosis_details"],
            "suggested_actions": self._get_suggested_actions(diagnosis),
            "related_files": self._get_related_files(diagnosis),
            "severity": self._assess_severity(diagnosis)
        }
    
    def _get_suggested_actions(self, diagnosis: Dict) -> List[str]:
        """获取建议操作"""
        actions = []
        
        if diagnosis["issue_type"] == "service_not_running":
            actions.append("重启后端服务")
            actions.append("检查端口占用")
        elif diagnosis["issue_type"] == "timeout":
            actions.append("增加超时时间")
            actions.append("检查网络连接")
        elif diagnosis["issue_type"] == "print_io_error":
            actions.append("检查thread_safe_logging.py")
            actions.append("检查所有print语句是否有保护")
        elif diagnosis["issue_type"] == "state_reset_error":
            actions.append("检查status_service.py中的update_from_event")
            actions.append("检查flow_start事件处理逻辑")
        else:
            actions.append("查看日志文件")
            actions.append("检查服务状态")
            actions.append("使用bug-fixer技能深度排查")
        
        return actions
    
    def _get_related_files(self, diagnosis: Dict) -> List[str]:
        """获取相关文件"""
        files = []
        
        if diagnosis["issue_type"] == "print_io_error":
            files.append("backend/services/workflow_runtime/thread_safe_logging.py")
            files.append("backend/services/workflow_runtime/provider_runtime.py")
            files.append("backend/repositories/job_repo.py")
        elif diagnosis["issue_type"] == "state_reset_error":
            files.append("backend/services/status_service.py")
        elif diagnosis["issue_type"] == "tos_presign_failed":
            files.append("backend/services/workflow_runtime/provider_runtime.py")
        
        return files
    
    def _assess_severity(self, diagnosis: Dict) -> str:
        """评估严重程度"""
        if diagnosis["issue_type"] in ["print_io_error", "state_reset_error"]:
            return "high"
        elif diagnosis["issue_type"] in ["service_not_running", "authentication_error"]:
            return "medium"
        else:
            return "low"
