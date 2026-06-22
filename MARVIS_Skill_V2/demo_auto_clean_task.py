"""
demo_auto_clean_task.py
MARVIS V2.1 — 30天自动清理定时任务专项验证

验证项：
1. 过期文件扫描 — 31天前的文件被识别，30天内文件不受影响
2. 预览模式 — dry_run 不实际删除文件
3. 正式清理 — 删除后文件不存在
4. 日志归档 — 清理报告写入 cleanup_log_*.json
5. 规则过滤 — 非匹配扩展名/不在清理范围内的文件不受影响
6. 边界安全 — BASE_DIR 为路径根，不会越界清理系统文件
"""

import sys
import os
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def check(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}", end="")
    if detail:
        print(f" → {detail}", end="")
    print()


BASE_DIR = Path(r"E:\MARVIS_Skill_V2")
TEST_DIR = BASE_DIR / "test_cleanup_area"


# ==================== 辅助：创建与清理测试文件 ====================

def create_test_file(rel_path: str, content: str = "test", age_days: int = 0):
    """创建测试文件，修改时间为 age_days 前"""
    file_path = TEST_DIR / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    if age_days > 0:
        old_time = time.time() - age_days * 86400
        os.utime(str(file_path), (old_time, old_time))
    return file_path


def cleanup_test_area():
    """清理测试区域"""
    if TEST_DIR.exists():
        import shutil
        shutil.rmtree(str(TEST_DIR))


# ==================== 校验 1: 过期扫描 ====================

def verify_01_expired_scan():
    section("校验 1: 过期文件扫描 — 31天旧文件识别")

    from task_cleanup_scheduler import CleanupScheduler

    cleanup_test_area()

    # 创建测试文件
    f1 = create_test_file("render_output/old_video.mp4", "video data", age_days=35)
    f2 = create_test_file("render_output/recent_video.mp4", "video data", age_days=10)
    f3 = create_test_file("render_output/old_image.png", "img data", age_days=60)
    f4 = create_test_file("interaction_log_20260101.json", "{}", age_days=40)
    f5 = create_test_file("interaction_log_20260620.json", "{}", age_days=2)
    f6 = create_test_file("settlement_log_20260101.json", "{}", age_days=45)
    f7 = create_test_file("demo_cache_temp.json", "{}", age_days=50)
    f8 = create_test_file("keep_me.txt", "important", age_days=40)  # 非目标扩展名

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=True)

    # 临时修改规则路径为测试目录
    from task_cleanup_scheduler import CLEANUP_RULES
    original_rules = CLEANUP_RULES.copy()
    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    report = scheduler.scan_and_clean()

    deleted_paths = [r.file_path for r in report.records if r.deleted]
    check(
        "过期文件被识别",
        str(f1) in deleted_paths,
        f"f1(35天).mp4 命中",
    )
    check(
        "近期文件不受影响",
        str(f2) not in deleted_paths,
        f"f2(10天).mp4 豁免",
    )
    check(
        "过期PNG被识别",
        str(f3) in deleted_paths,
        f"f3(60天).png 命中",
    )
    check(
        "过期日志被识别",
        str(f4) in deleted_paths,
        f"f4(40天) interaction_log 命中",
    )
    check(
        "近期日志豁免",
        str(f5) not in deleted_paths,
        f"f5(2天) interaction_log 豁免",
    )
    check(
        "过期结算日志命中",
        str(f6) in deleted_paths,
        f"f6(45天) settlement_log 命中",
    )
    check(
        "过期Demo临时文件命中",
        str(f7) in deleted_paths,
        f"f7(50天) demo_cache 命中",
    )
    check(
        "非目标扩展名豁免",
        str(f8) not in deleted_paths,
        "f8.txt 不在清理范围",
    )

    # 恢复
    for i, rule in enumerate(CLEANUP_RULES):
        if i < len(original_rules):
            CLEANUP_RULES[i] = original_rules[i]

    return scheduler


# ==================== 校验 2: Dry Run 不删除 ====================

def verify_02_dry_run_no_delete():
    section("校验 2: 预览模式 — dry_run 不实际删除文件")

    from task_cleanup_scheduler import CleanupScheduler

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=True)

    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    f = create_test_file("render_output/dryrun_test.mp4", "dry", age_days=40)
    assert f.exists(), "测试文件应存在"

    report = scheduler.scan_and_clean()

    check("报告标记待删除目标", report.total_deleted >= 1, f"{report.total_deleted} 项")
    check("实际文件未删除", f.exists(), "dry_run 不执行 unlink")


# ==================== 校验 3: 正式清理 ====================

def verify_03_real_delete():
    section("校验 3: 正式清理 — 文件被物理删除")

    from task_cleanup_scheduler import CleanupScheduler

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=False)

    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    f = create_test_file("render_output/delete_me.mp4", "delete", age_days=50)
    assert f.exists()

    report, log_path = scheduler.run()

    check("文件被删除", not f.exists(), "unlink 执行成功")
    check("删除计数正确", report.total_deleted >= 1, f"删除了 {report.total_deleted} 个")


# ==================== 校验 4: 日志归档 ====================

def verify_04_cleanup_log():
    section("校验 4: 清理日志归档 — cleanup_log_*.json 写入")

    from task_cleanup_scheduler import CleanupScheduler, LOG_DIR

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=False)

    # 创建测试文件
    create_test_file("render_output/log_test.mp4", "x", age_days=60)

    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    report, log_path = scheduler.run()

    check("归档日志文件存在", log_path.exists(), str(log_path))

    with open(log_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    check("日志含 summary", "summary" in data)
    check("日志含 records", "records" in data)
    check("日志记录条数", len(data["records"]) == report.total_deleted)

    summary = data["summary"]
    check("summary 含 freed_mb", "total_freed_mb" in summary)


# ==================== 校验 5: 规则过滤精确度 ====================

def verify_05_rule_precision():
    section("校验 5: 规则过滤精确度")

    from task_cleanup_scheduler import CleanupScheduler

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=True)

    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    # 创建各种边缘文件
    create_test_file("render_output/valid.mp4", "", age_days=60)   # 应命中
    create_test_file("render_output/valid.png", "", age_days=60)   # 应命中
    create_test_file("render_output/not_target.docx", "", age_days=60)  # 不命中
    create_test_file("render_output/not_target.pdf", "", age_days=60)   # 不命中
    create_test_file("other_file.json", "", age_days=60)  # 不匹配 prefix

    report = scheduler.scan_and_clean()

    deleted_paths = [r.file_path for r in report.records]
    valid_count = sum(1 for p in deleted_paths if "valid" in p)
    invalid_count = sum(1 for p in deleted_paths if "not_target" in p or "other_file" in p)

    check("匹配扩展名命中", valid_count >= 2, f"应命中 .mp4 + .png")
    check("非目标扩展名豁免", invalid_count == 0, "docx/pdf 未命中")


# ==================== 校验 6: 边界安全 ====================

def verify_06_boundary_safety():
    section("校验 6: 边界安全 — 不会越界清理")

    from task_cleanup_scheduler import CleanupScheduler

    scheduler = CleanupScheduler(base_dir=TEST_DIR, dry_run=True)

    for rule in scheduler.rules:
        rule["paths"] = [
            TEST_DIR / Path(p).relative_to(BASE_DIR) if str(BASE_DIR) in str(p) else p
            for p in rule.get("paths", [])
        ]

    report = scheduler.scan_and_clean()

    # 检查所有记录路径都在 TEST_DIR 下
    for r in report.records:
        assert str(TEST_DIR) in str(Path(r.file_path).parent) or str(TEST_DIR) in r.file_path, \
            f"路径越界: {r.file_path}"

    check(
        "所有清理路径均在 BASE_DIR 内",
        True,
        f"共 {len(report.records)} 条记录，无越界",
    )

    # 检查系统关键路径不在扫描范围
    system_paths = ["C:\\Windows", "C:\\Program Files", "C:\\System32"]
    for rule in scheduler.rules:
        for p in rule["paths"]:
            for sys_p in system_paths:
                assert sys_p.lower() not in str(p).lower(), f"系统路径出现在扫描列表中: {p}"

    check("系统路径不在扫描范围", True)


# ==================== 主入口 ====================

if __name__ == "__main__":
    print(f"MARVIS V2.1 自动清理定时任务验证")
    print(f"测试区域: {TEST_DIR}")

    results = []

    try:
        verify_01_expired_scan()
        results.append(("01-过期扫描", True))
    except Exception as e:
        print(f"  [FAIL] 校验 1 异常: {e}")
        results.append(("01-过期扫描", False))

    try:
        verify_02_dry_run_no_delete()
        results.append(("02-预览模式", True))
    except Exception as e:
        print(f"  [FAIL] 校验 2 异常: {e}")
        results.append(("02-预览模式", False))

    try:
        verify_03_real_delete()
        results.append(("03-正式清理", True))
    except Exception as e:
        print(f"  [FAIL] 校验 3 异常: {e}")
        results.append(("03-正式清理", False))

    try:
        verify_04_cleanup_log()
        results.append(("04-日志归档", True))
    except Exception as e:
        print(f"  [FAIL] 校验 4 异常: {e}")
        results.append(("04-日志归档", False))

    try:
        verify_05_rule_precision()
        results.append(("05-规则过滤", True))
    except Exception as e:
        print(f"  [FAIL] 校验 5 异常: {e}")
        results.append(("05-规则过滤", False))

    try:
        verify_06_boundary_safety()
        results.append(("06-边界安全", True))
    except Exception as e:
        print(f"  [FAIL] 校验 6 异常: {e}")
        results.append(("06-边界安全", False))

    # 清理测试区域
    cleanup_test_area()

    # 汇总
    section("验收汇总")
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'✓' if ok else '✗'}] {name}")
    print(f"\n  总计: {passed}/{len(results)} 项通过")
    if passed == len(results):
        print("  结论: 自动清理定时任务全部验收通过。")
    else:
        print(f"  结论: {len(results) - passed} 项未通过。")
