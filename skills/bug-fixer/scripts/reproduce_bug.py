#!/usr/bin/env python3
"""
状态监控与问题诊断工具 - 追踪状态机变化、Step执行前后对比、产物变化
"""

import requests
import json
import sys
import time
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import argparse
import copy


@dataclass
class StateSnapshot:
    timestamp: str
    project_id: str
    job_id: Optional[str]
    state: Dict[str, Any]
    artifacts: List[str]


class StateMonitor:
    def __init__(self, base_url: str = "http://127.0.0.1:8086", 
                 project_dir: str = "/Users/bytedance/Desktop/常见python/manju_web"):
        self.base_url = base_url
        self.project_dir = project_dir
        self.session = requests.Session()
        self.snapshots: List[StateSnapshot] = []

    def check_server_status(self) -> bool:
        """检查服务器状态"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"Server not reachable: {e}")
            return False

    def get_projects(self) -> Optional[Dict[str, Any]]:
        """获取项目列表"""
        try:
            response = self.session.get(f"{self.base_url}/api/projects")
            if response.status_code == 200:
                return response.json()
            print(f"Failed to get projects: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error getting projects: {e}")
            return None

    def get_project_status(self, project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目完整状态"""
        try:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}")
            if response.status_code == 200:
                return response.json()
            print(f"Failed to get project status: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error getting project status: {e}")
            return None

    def get_project_jobs(self, project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目的jobs"""
        try:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/jobs")
            if response.status_code == 200:
                return response.json()
            print(f"Failed to get jobs: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error getting jobs: {e}")
            return None

    def get_job_status(self, project_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        """获取job详细状态"""
        try:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/jobs/{job_id}")
            if response.status_code == 200:
                return response.json()
            print(f"Failed to get job status: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error getting job status: {e}")
            return None

    def list_artifacts(self, project_id: str) -> List[str]:
        """列出项目产物文件"""
        artifacts = []
        manju_output_dir = os.path.join(self.project_dir, "backend", "manju_output")
        
        if os.path.exists(manju_output_dir):
            for root, dirs, files in os.walk(manju_output_dir):
                for file in files:
                    if project_id in root or project_id in file:
                        artifacts.append(os.path.relpath(os.path.join(root, file), self.project_dir))
        
        return sorted(artifacts)

    def take_snapshot(self, project_id: str, job_id: Optional[str] = None, 
                     label: str = "") -> StateSnapshot:
        """拍摄状态快照"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        state = {
            "project": self.get_project_status(project_id),
            "jobs": self.get_project_jobs(project_id),
            "current_job": self.get_job_status(project_id, job_id) if job_id else None
        }
        
        artifacts = self.list_artifacts(project_id)
        
        snapshot = StateSnapshot(
            timestamp=timestamp,
            project_id=project_id,
            job_id=job_id,
            state=state,
            artifacts=artifacts
        )
        
        self.snapshots.append(snapshot)
        
        if label:
            print(f"\n📸 [{label}] Snapshot taken at {timestamp}")
        else:
            print(f"\n📸 Snapshot taken at {timestamp}")
        
        return snapshot

    def compare_snapshots(self, snapshot1: StateSnapshot, snapshot2: StateSnapshot):
        """对比两个状态快照"""
        print("\n" + "=" * 100)
        print(f"📊 STATE COMPARISON: {snapshot1.timestamp} → {snapshot2.timestamp}")
        print("=" * 100)
        
        print("\n[1] Job Status Changes:")
        job1 = snapshot1.state.get("current_job")
        job2 = snapshot2.state.get("current_job")
        
        if job1 and job2:
            self._compare_dict("Job", job1, job2)
        elif job2:
            print("  ✨ New job created:")
            print(json.dumps(job2, indent=4, ensure_ascii=False))
        
        print("\n[2] Artifact Changes:")
        artifacts1 = set(snapshot1.artifacts)
        artifacts2 = set(snapshot2.artifacts)
        
        added = artifacts2 - artifacts1
        removed = artifacts1 - artifacts2
        
        if added:
            print(f"  📁 New files ({len(added)}):")
            for f in sorted(added):
                print(f"    + {f}")
        
        if removed:
            print(f"  🗑️  Removed files ({len(removed)}):")
            for f in sorted(removed):
                print(f"    - {f}")
        
        if not added and not removed:
            print("  No artifact changes")

    def _compare_dict(self, prefix: str, d1: Dict, d2: Dict, indent: int = 2):
        """递归比较两个字典"""
        all_keys = set(d1.keys()) | set(d2.keys())
        
        for key in sorted(all_keys):
            v1 = d1.get(key)
            v2 = d2.get(key)
            
            if key not in d1:
                print(f"{' ' * indent}✨ {prefix}.{key}: (new) → {json.dumps(v2, ensure_ascii=False)}")
            elif key not in d2:
                print(f"{' ' * indent}🗑️  {prefix}.{key}: {json.dumps(v1, ensure_ascii=False)} → (removed)")
            elif v1 != v2:
                if isinstance(v1, dict) and isinstance(v2, dict):
                    self._compare_dict(f"{prefix}.{key}", v1, v2, indent + 2)
                elif isinstance(v1, list) and isinstance(v2, list):
                    self._compare_list(f"{prefix}.{key}", v1, v2, indent + 2)
                else:
                    print(f"{' ' * indent}🔄 {prefix}.{key}:")
                    print(f"{' ' * (indent + 2)}  FROM: {json.dumps(v1, ensure_ascii=False)}")
                    print(f"{' ' * (indent + 2)}  TO:   {json.dumps(v2, ensure_ascii=False)}")

    def _compare_list(self, prefix: str, l1: List, l2: List, indent: int = 2):
        """比较两个列表"""
        if len(l1) != len(l2):
            print(f"{' ' * indent}🔄 {prefix}: length {len(l1)} → {len(l2)}")
        
        max_len = max(len(l1), len(l2))
        for i in range(max_len):
            v1 = l1[i] if i < len(l1) else None
            v2 = l2[i] if i < len(l2) else None
            
            if v1 != v2:
                if isinstance(v1, dict) and isinstance(v2, dict):
                    self._compare_dict(f"{prefix}[{i}]", v1, v2, indent + 2)
                else:
                    print(f"{' ' * indent}🔄 {prefix}[{i}]:")
                    if v1 is not None:
                        print(f"{' ' * (indent + 2)}  FROM: {json.dumps(v1, ensure_ascii=False)}")
                    if v2 is not None:
                        print(f"{' ' * (indent + 2)}  TO:   {json.dumps(v2, ensure_ascii=False)}")

    def monitor_job_execution(self, project_id: str, job_id: str, 
                             interval: int = 2, timeout: int = 300):
        """监控Job执行，定期拍摄快照"""
        print(f"\n🔍 Monitoring job {job_id}...")
        print(f"   Interval: {interval}s, Timeout: {timeout}s")
        
        start_time = time.time()
        snapshot_count = 0
        
        self.take_snapshot(project_id, job_id, label=f"START-{snapshot_count}")
        snapshot_count += 1
        
        while time.time() - start_time < timeout:
            status = self.get_job_status(project_id, job_id)
            
            if status:
                current_status = status.get('status')
                print(f"\r   [{datetime.now().strftime('%H:%M:%S')}] Status: {current_status}", end="")
                
                if current_status in ['completed', 'failed', 'error']:
                    print("\n   Job finished!")
                    self.take_snapshot(project_id, job_id, label=f"END-{snapshot_count}")
                    
                    if len(self.snapshots) >= 2:
                        self.compare_snapshots(self.snapshots[-2], self.snapshots[-1])
                    
                    return status
                
                if (time.time() - start_time) % 10 < interval:
                    self.take_snapshot(project_id, job_id, label=f"STEP-{snapshot_count}")
                    snapshot_count += 1
            
            time.sleep(interval)
        
        print(f"\n⏱️  Timeout after {timeout}s")
        self.take_snapshot(project_id, job_id, label=f"TIMEOUT-{snapshot_count}")
        return None

    def print_current_state(self, project_id: str):
        """打印当前完整状态"""
        print("\n" + "=" * 100)
        print(f"📋 CURRENT STATE - Project: {project_id}")
        print("=" * 100)
        
        project_status = self.get_project_status(project_id)
        if project_status:
            print("\n[Project Info]")
            print(json.dumps(project_status, indent=2, ensure_ascii=False))
        
        jobs = self.get_project_jobs(project_id)
        if jobs:
            print("\n[Jobs]")
            print(json.dumps(jobs, indent=2, ensure_ascii=False))
        
        artifacts = self.list_artifacts(project_id)
        if artifacts:
            print(f"\n[Artifacts] ({len(artifacts)} files)")
            for f in artifacts:
                print(f"  - {f}")

    def export_snapshots(self, output_file: str):
        """导出所有快照到文件"""
        export_data = []
        for snapshot in self.snapshots:
            export_data.append({
                "timestamp": snapshot.timestamp,
                "project_id": snapshot.project_id,
                "job_id": snapshot.job_id,
                "state": snapshot.state,
                "artifacts": snapshot.artifacts
            })
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Snapshots exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="State Monitor & Debug Tool")
    parser.add_argument("--base-url", default="http://127.0.0.1:8086",
                       help="Backend API base URL")
    parser.add_argument("--project-id", required=True,
                       help="Project ID to monitor")
    parser.add_argument("--job-id", help="Job ID to monitor")
    parser.add_argument("--snapshot", action="store_true",
                       help="Take a single state snapshot")
    parser.add_argument("--monitor", action="store_true",
                       help="Monitor job execution with periodic snapshots")
    parser.add_argument("--current-state", action="store_true",
                       help="Show current complete state")
    parser.add_argument("--list-projects", action="store_true",
                       help="List all projects")
    parser.add_argument("--interval", type=int, default=2,
                       help="Snapshot interval in seconds (default: 2)")
    parser.add_argument("--timeout", type=int, default=300,
                       help="Monitor timeout in seconds (default: 300)")
    parser.add_argument("--export", help="Export snapshots to JSON file")
    
    args = parser.parse_args()
    
    monitor = StateMonitor(args.base_url)
    
    print("Checking server status...")
    if not monitor.check_server_status():
        print("❌ Server is not running!")
        print("Please start the backend server first.")
        sys.exit(1)
    
    print("✅ Server is running\n")
    
    if args.list_projects:
        print("Fetching projects...")
        projects = monitor.get_projects()
        if projects:
            print("\nAvailable projects:")
            for proj in projects.get('projects', []):
                print(f"  - ID: {proj.get('id')}, Name: {proj.get('name')}")
    
    if args.current_state:
        monitor.print_current_state(args.project_id)
    
    if args.snapshot:
        monitor.take_snapshot(args.project_id, args.job_id, label="MANUAL")
        
        if args.export:
            monitor.export_snapshots(args.export)
    
    if args.monitor and args.job_id:
        final_status = monitor.monitor_job_execution(
            args.project_id, 
            args.job_id,
            interval=args.interval,
            timeout=args.timeout
        )
        
        if args.export:
            monitor.export_snapshots(args.export)
    
    elif args.monitor and not args.job_id:
        print("\n⚠️  Please specify --job-id for monitoring")


if __name__ == "__main__":
    main()
