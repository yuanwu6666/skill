"""
task_cleanup_scheduler.py
MARVIS V2.1 — 30天过期素材 & 日志自动清理定时任务

清理范围：
- 渲染成品素材（render_output 目录下 .mp4/.png/.jpg）
- 互动日志（interaction_log_*.json）
- 计价日志（pricing_log_*.json / settlement_*.json）
- Demo 缓存文件（demo_*.py 产生的 .json/.png 临时文件）

执行时机：每日凌晨低负载运行（建议通过 create_scheduled_task 编排）
输出：清理归档日志 cleanup_log_*.json，记录删除路径、时间戳
"""

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ==================== 配置 ====================

BASE_DIR = Path(r"E:\MARVIS_Skill_V2")

CLEANUP_RULES = [
    {
        "name": "渲染成品素材",
        "paths": [BASE_DIR / "render_output"],
        "extensions": [".mp4", ".png", ".jpg", ".jpeg", ".gif", ".webm", ".mov"],
        "min_age_days": 30,
        "exclude_dirs": [],   # 排除的子目录
    },
    {
        "name": "互动日志",
        "paths": [BASE_DIR],
        "extensions": [".json"],
        "pattern_prefix": "interaction_log_",
        "min_age_days": 30,
        "exclude_dirs": ["demo"],
    },
    {
        "name": "计价与结算日志",
        "paths": [BASE_DIR],
        "extensions": [".json"],
        "pattern_prefix": ("pricing_log_", "settlement_", "billing_"),
        "min_age_days": 30,
        "exclude_dirs": ["demo"],
    },
    {
        "name": "Demo 临时产物",
        "paths": [BASE_DIR],
        "extensions": [".json", ".png", ".jpg", ".tmp", ".cache"],
        "pattern_prefix": ("demo_", "test_", "temp_"),
        "min_age_days": 30,
        "exclude_dirs": [],
    },
]

LOG_DIR = BASE_DIR / "cleanup_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CleanupRecord:
    """单条清理记录"""
    file_path: str
    file_size_bytes: int
    age_days: int
    rule_name: str
    deleted: bool
    error: str = ""


@dataclass
class CleanupReport:
    """清理报告"""
    started_at: str = ""
    finished_at: str = ""
    total_scanned: int = 0
    total_deleted: int = 0
    total_freed_bytes: int = 0
    errors: int = 0
    records: list = field(default_factory=list)


class CleanupScheduler:
    """过期文件清理调度器"""

    def __init__(self, base_dir: Optional[Path] = None, dry_run: bool = False):
        self.base_dir = base_dir or BASE_DIR
        self.dry_run = dry_run
        self.rules = CLEANUP_RULES

    def _get_file_age_days(self, file_path: Path) -> int:
        """获取文件已存在天数（基于修改时间）"""
        mtime = file_path.stat().st_mtime
        age_sec = time.time() - mtime
        return max(0, int(age_sec / 86400))

    def _match_rule(self, file_path: Path, rule: dict) -> bool:
        """检查文件是否匹配清理规则"""
        # 扩展名匹配
        if file_path.suffix.lower() not in [e.lower() for e in rule["extensions"]]:
            return False

        # 文件名前缀匹配（可选）
        if "pattern_prefix" in rule:
            prefixes = rule["pattern_prefix"]
            if isinstance(prefixes, str):
                prefixes = (prefixes,)
            name = file_path.name
            if not any(name.startswith(p) for p in prefixes):
                return False

        # 排除目录
        for exc in rule.get("exclude_dirs", []):
            if exc and str(exc) in str(file_path.parent):
                return False

        return True

    def scan_and_clean(self) -> CleanupReport:
        """扫描并清理过期文件"""
        report = CleanupReport(started_at=datetime.now().isoformat())

        for rule in self.rules:
            for scan_path in rule["paths"]:
                if not scan_path.exists():
                    continue

                for root, dirs, files in os.walk(scan_path):
                    for filename in files:
                        file_path = Path(root) / filename
                        if not self._match_rule(file_path, rule):
                            continue

                        report.total_scanned += 1
                        age_days = self._get_file_age_days(file_path)

                        if age_days < rule["min_age_days"]:
                            continue  # 未过期

                        file_size = file_path.stat().st_size
                        record = CleanupRecord(
                            file_path=str(file_path),
                            file_size_bytes=file_size,
                            age_days=age_days,
                            rule_name=rule["name"],
                            deleted=False,
                        )

                        if self.dry_run:
                            record.deleted = False
                            report.total_deleted += 1
                            report.total_freed_bytes += file_size
                        else:
                            try:
                                file_path.unlink()
                                record.deleted = True
                                report.total_deleted += 1
                                report.total_freed_bytes += file_size
                            except Exception as e:
                                record.error = str(e)
                                report.errors += 1

                        report.records.append(record)

        report.finished_at = datetime.now().isoformat()
        return report

    def write_report(self, report: CleanupReport) -> Path:
        """将清理报告写入归档日志"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"cleanup_log_{timestamp}.json"

        data = {
            "version": "2.1",
            "dry_run": self.dry_run,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "summary": {
                "total_scanned": report.total_scanned,
                "total_deleted": report.total_deleted,
                "total_freed_bytes": report.total_freed_bytes,
                "total_freed_mb": round(report.total_freed_bytes / (1024 * 1024), 2),
                "errors": report.errors,
            },
            "records": [
                {
                    "file_path": r.file_path,
                    "size_bytes": r.file_size_bytes,
                    "age_days": r.age_days,
                    "rule": r.rule_name,
                    "deleted": r.deleted,
                    "error": r.error,
                }
                for r in report.records
            ],
        }

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return log_path

    def run(self) -> tuple[CleanupReport, Path]:
        """完整执行：扫描 → 清理 → 归档报告"""
        report = self.scan_and_clean()
        log_path = self.write_report(report)
        return report, log_path


# ==================== 模拟过期文件工具 ====================

def create_mock_expired_file(filename: str, content: str = "", age_days: int = 31):
    """创建模拟过期文件（用于测试），设置修改时间为 age_days 前"""
    file_path = BASE_DIR / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    # 修改文件时间为 age_days 前
    old_time = time.time() - age_days * 86400
    os.utime(str(file_path), (old_time, old_time))

    return file_path


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MARVIS V2.1 过期文件自动清理")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际删除")
    parser.add_argument("--base-dir", type=str, default=str(BASE_DIR), help="扫描根目录")
    args = parser.parse_args()

    scheduler = CleanupScheduler(
        base_dir=Path(args.base_dir),
        dry_run=args.dry_run,
    )

    print(f"MARVIS V2.1 自动清理调度器")
    print(f"  模式: {'预览 (DRY RUN)' if args.dry_run else '正式清理'}")
    print(f"  根目录: {args.base_dir}")
    print()

    report, log_path = scheduler.run()

    s = report
    summary = {
        "total_scanned": s.total_scanned,
        "total_deleted": s.total_deleted,
        "total_freed_mb": round(s.total_freed_bytes / (1024 * 1024), 2),
        "errors": s.errors,
    }

    print(f"清理完成:")
    print(f"  扫描文件: {summary['total_scanned']}")
    print(f"  清理文件: {summary['total_deleted']}")
    print(f"  释放空间: {summary['total_freed_mb']} MB")
    print(f"  异常: {summary['errors']}")
    print(f"  归档日志: {log_path}")
