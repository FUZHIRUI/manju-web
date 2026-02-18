#!/usr/bin/env python3
"""
日志分析脚本 - 自动扫描和分析项目日志文件
"""

import os
import re
import sys
import glob
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import argparse


@dataclass
class LogError:
    timestamp: str
    level: str
    message: str
    file_path: str
    line_number: int
    stack_trace: Optional[str] = None


class LogAnalyzer:
    def __init__(self, logs_dir: str):
        self.logs_dir = logs_dir
        self.errors: List[LogError] = []
        self.warnings: List[LogError] = []

    def find_log_files(self) -> List[str]:
        """查找所有日志文件"""
        log_patterns = [
            os.path.join(self.logs_dir, "*.log"),
            os.path.join(self.logs_dir, "**", "*.log"),
        ]
        
        log_files = []
        for pattern in log_patterns:
            log_files.extend(glob.glob(pattern, recursive=True))
        
        log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return log_files

    def parse_log_file(self, file_path: str) -> Tuple[List[LogError], List[LogError]]:
        """解析单个日志文件"""
        errors = []
        warnings = []
        
        if not os.path.exists(file_path):
            return errors, warnings
        
        error_pattern = re.compile(
            r'(ERROR|EXCEPTION|FATAL|CRITICAL).*?(?=\n(?:\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}|INFO|DEBUG|WARNING|$))',
            re.DOTALL | re.IGNORECASE
        )
        warning_pattern = re.compile(
            r'(WARNING|WARN).*?(?=\n(?:\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}|INFO|DEBUG|ERROR|$))',
            re.DOTALL | re.IGNORECASE
        )
        
        timestamp_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)'
        )
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                
                for match in error_pattern.finditer(content):
                    error_text = match.group(0)
                    line_num = content[:match.start()].count('\n') + 1
                    
                    timestamp_match = timestamp_pattern.search(error_text)
                    timestamp = timestamp_match.group(1) if timestamp_match else "unknown"
                    
                    errors.append(LogError(
                        timestamp=timestamp,
                        level="ERROR",
                        message=error_text[:500] if len(error_text) > 500 else error_text,
                        file_path=file_path,
                        line_number=line_num,
                        stack_trace=error_text if len(error_text) > 500 else None
                    ))
                
                for match in warning_pattern.finditer(content):
                    warning_text = match.group(0)
                    line_num = content[:match.start()].count('\n') + 1
                    
                    timestamp_match = timestamp_pattern.search(warning_text)
                    timestamp = timestamp_match.group(1) if timestamp_match else "unknown"
                    
                    warnings.append(LogError(
                        timestamp=timestamp,
                        level="WARNING",
                        message=warning_text[:300] if len(warning_text) > 300 else warning_text,
                        file_path=file_path,
                        line_number=line_num
                    ))
                    
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
        
        return errors, warnings

    def analyze(self, limit: int = 10):
        """执行完整分析"""
        log_files = self.find_log_files()
        
        if not log_files:
            print("No log files found.")
            return
        
        print(f"Found {len(log_files)} log files. Analyzing...\n")
        
        for i, log_file in enumerate(log_files[:limit]):
            mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            print(f"[{i+1}] {os.path.basename(log_file)}")
            print(f"    Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Path: {log_file}")
            
            errors, warnings = self.parse_log_file(log_file)
            self.errors.extend(errors)
            self.warnings.extend(warnings)
            
            print(f"    Errors: {len(errors)}, Warnings: {len(warnings)}\n")
        
        self.print_summary()

    def print_summary(self):
        """打印分析摘要"""
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        if self.errors:
            print(f"\nTOTAL ERRORS: {len(self.errors)}")
            print("\n--- TOP 5 ERRORS ---")
            for i, error in enumerate(sorted(self.errors, key=lambda x: x.timestamp, reverse=True)[:5]):
                print(f"\n[{i+1}] [{error.timestamp}] {os.path.basename(error.file_path)}:{error.line_number}")
                print(f"    {error.message}")
        else:
            print("\nNo errors found in analyzed logs.")
        
        if self.warnings:
            print(f"\nTOTAL WARNINGS: {len(self.warnings)}")
            print("\n--- TOP 5 WARNINGS ---")
            for i, warning in enumerate(sorted(self.warnings, key=lambda x: x.timestamp, reverse=True)[:5]):
                print(f"\n[{i+1}] [{warning.timestamp}] {os.path.basename(warning.file_path)}:{warning.line_number}")
                print(f"    {warning.message}")


def main():
    parser = argparse.ArgumentParser(description="Analyze log files for errors and warnings")
    parser.add_argument("--logs-dir", 
                       default="/Users/bytedance/Desktop/常见python/manju_web/backend/logs",
                       help="Directory containing log files")
    parser.add_argument("--limit", type=int, default=10,
                       help="Limit number of log files to analyze")
    parser.add_argument("--file", help="Analyze specific log file")
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer(args.logs_dir)
    
    if args.file:
        if os.path.exists(args.file):
            print(f"Analyzing specific file: {args.file}\n")
            errors, warnings = analyzer.parse_log_file(args.file)
            analyzer.errors = errors
            analyzer.warnings = warnings
            analyzer.print_summary()
        else:
            print(f"File not found: {args.file}")
    else:
        analyzer.analyze(limit=args.limit)


if __name__ == "__main__":
    main()
