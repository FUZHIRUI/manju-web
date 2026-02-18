#!/usr/bin/env python3
"""
代码质量检查脚本 - 检查常见的代码问题
"""

import os
import re
import sys
import subprocess
from typing import List, Dict, Tuple
import argparse


class CodeQualityChecker:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.issues: List[Dict] = []

    def find_python_files(self) -> List[str]:
        """查找所有Python文件"""
        python_files = []
        for root, dirs, files in os.walk(self.project_dir):
            for file in files:
                if file.endswith('.py') and not file.startswith('_'):
                    python_files.append(os.path.join(root, file))
        return python_files

    def check_hardcoded_secrets(self, file_path: str) -> List[Dict]:
        """检查硬编码的密钥"""
        issues = []
        secret_patterns = [
            (r'(?i)api[_-]?key\s*[=:]\s*[\'"]([^\'"]{16,})[\'"]', "API key"),
            (r'(?i)password\s*[=:]\s*[\'"]([^\'"]{4,})[\'"]', "Password"),
            (r'(?i)secret\s*[=:]\s*[\'"]([^\'"]{8,})[\'"]', "Secret"),
            (r'(?i)token\s*[=:]\s*[\'"]([^\'"]{16,})[\'"]', "Token"),
        ]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                
                for pattern, secret_type in secret_patterns:
                    for i, line in enumerate(lines, 1):
                        if re.search(pattern, line):
                            issues.append({
                                'file': file_path,
                                'line': i,
                                'type': 'security',
                                'severity': 'high',
                                'message': f"Potential hardcoded {secret_type} found"
                            })
        except Exception as e:
            pass
        
        return issues

    def check_print_statements(self, file_path: str) -> List[Dict]:
        """检查print语句"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith('print(') and not stripped.startswith('#'):
                        issues.append({
                            'file': file_path,
                            'line': i,
                            'type': 'style',
                            'severity': 'low',
                            'message': "Print statement found (consider using logging)"
                        })
        except Exception as e:
            pass
        
        return issues

    def check_empty_except(self, file_path: str) -> List[Dict]:
        """检查裸except语句"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped == 'except:' and not stripped.startswith('#'):
                        issues.append({
                            'file': file_path,
                            'line': i,
                            'type': 'error_handling',
                            'severity': 'medium',
                            'message': "Bare except clause found (specify exception type)"
                        })
        except Exception as e:
            pass
        
        return issues

    def check_long_functions(self, file_path: str, max_lines: int = 50) -> List[Dict]:
        """检查过长的函数"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                func_pattern = re.compile(r'^def\s+\w+\s*\([^)]*\)\s*:', re.MULTILINE)
                matches = list(func_pattern.finditer(content))
                
                for i, match in enumerate(matches):
                    start_line = content[:match.start()].count('\n') + 1
                    
                    if i + 1 < len(matches):
                        end_pos = matches[i + 1].start()
                    else:
                        end_pos = len(content)
                    
                    func_content = content[match.start():end_pos]
                    func_lines = func_content.count('\n') + 1
                    
                    if func_lines > max_lines:
                        issues.append({
                            'file': file_path,
                            'line': start_line,
                            'type': 'complexity',
                            'severity': 'medium',
                            'message': f"Function too long ({func_lines} lines, max {max_lines})"
                        })
        except Exception as e:
            pass
        
        return issues

    def run_pylint(self, file_path: str) -> List[Dict]:
        """运行pylint检查"""
        issues = []
        
        try:
            result = subprocess.run(
                ['pylint', '--errors-only', file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0 and result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip() and ':' in line:
                        issues.append({
                            'file': file_path,
                            'line': 'unknown',
                            'type': 'lint',
                            'severity': 'medium',
                            'message': line.strip()
                        })
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return issues

    def check_file(self, file_path: str):
        """检查单个文件"""
        self.issues.extend(self.check_hardcoded_secrets(file_path))
        self.issues.extend(self.check_print_statements(file_path))
        self.issues.extend(self.check_empty_except(file_path))
        self.issues.extend(self.check_long_functions(file_path))

    def check_all(self):
        """检查所有文件"""
        python_files = self.find_python_files()
        print(f"Checking {len(python_files)} Python files...\n")
        
        for file_path in python_files:
            self.check_file(file_path)
        
        self.print_report()

    def print_report(self):
        """打印检查报告"""
        print("=" * 80)
        print("CODE QUALITY REPORT")
        print("=" * 80)
        
        if not self.issues:
            print("\n✅ No issues found!")
            return
        
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        sorted_issues = sorted(self.issues, key=lambda x: severity_order.get(x['severity'], 999))
        
        high_count = sum(1 for i in self.issues if i['severity'] == 'high')
        medium_count = sum(1 for i in self.issues if i['severity'] == 'medium')
        low_count = sum(1 for i in self.issues if i['severity'] == 'low')
        
        print(f"\nSummary: {high_count} HIGH, {medium_count} MEDIUM, {low_count} LOW issues\n")
        
        for issue in sorted_issues[:20]:
            severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            icon = severity_icon.get(issue['severity'], '⚪')
            print(f"{icon} [{issue['severity'].upper()}] {os.path.basename(issue['file'])}:{issue['line']}")
            print(f"   {issue['message']}\n")
        
        if len(self.issues) > 20:
            print(f"... and {len(self.issues) - 20} more issues")


def main():
    parser = argparse.ArgumentParser(description="Code quality checker")
    parser.add_argument("--project-dir", 
                       default="/Users/bytedance/Desktop/常见python/manju_web/backend",
                       help="Project directory to check")
    parser.add_argument("--file", help="Check specific file")
    
    args = parser.parse_args()
    
    checker = CodeQualityChecker(args.project_dir)
    
    if args.file:
        if os.path.exists(args.file):
            print(f"Checking specific file: {args.file}\n")
            checker.check_file(args.file)
            checker.print_report()
        else:
            print(f"File not found: {args.file}")
    else:
        checker.check_all()


if __name__ == "__main__":
    main()
