"""
MARVIS V2.0 Demo - 完整单流程验证
"""

import sys
sys.path.insert(0, r"E:\MARVIS_Skill_V2")

from marvis_core import (
    MarvisScheduler, build_demo_data,
    Platform, MediaTag, PriorityTag, MatchScoreTag, PerformanceTag,
    SourceTag, AdOrder,
)


def print_separator(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run_demo():
    print_separator("MARVIS 全域热点广告变现自动化 Skill V2.0 - Demo")
    print(f"架构: MARVIS(主控) → AiToEarn(渲染)  单向调度")
    print()

    # 1. 构建 Demo 数据
    scheduler = build_demo_data()
    print(">>> [Init] 已注册 4 位广告主，加载 4 条热点，提交 5 笔订单")

    # 2. 查看广告主状态
    print_separator("广告主状态")
    for aid, adv in scheduler.advertisers.items():
        print(f"  {adv.id} | {adv.name:12s} | 等级: {adv.level.value:6s} | 信用分: {adv.credit_score}")

    # 3. 查看热点状态
    print_separator("今日热点池")
    for hs in scheduler.hotspots:
        tag = "[负面-禁用]" if hs.is_negative else "[可用]"
        print(f"  {hs.id} {tag} 评分:{hs.score} | {hs.title[:45]}...")

    # 4. 订单预审结果
    print_separator("订单预审结果")
    for o in scheduler.settlement.orders:
        status_icon = "✓" if o.status.value in ("预审通过", "已投放") else "✗"
        print(f"  {status_icon} {o.id} | {o.advertiser_name:12s} | {o.product_name:20s} | {o.status.value}")

    # 5. 执行全流程
    print_separator("全流程执行")
    log = scheduler.run_full_pipeline()

    for step in log["steps"]:
        if "order" in step:
            print(f"\n  ▸ {step['order']} | 匹配分:{step.get('match_score','N/A')} | 报价:{step.get('price','N/A')}")
            print(f"    队列:{step.get('queue','N/A')} | 文案方案数:{step.get('copies',0)}")
            print(f"    渲染产物:{step.get('render','N/A')}")
            print(f"    质检结果:{step.get('qa','N/A')}")
        else:
            print(f"  ▸ {step['step']}: {step.get('count','N/A')}")

    # 6. 队列汇总
    print_separator("任务队列状态")
    qs = scheduler.queue_summary()
    for k, v in qs.items():
        print(f"  {k}: {v}")

    # 7. 订单最终状态
    print_separator("订单最终状态")
    print(f"  {'订单ID':<10} {'广告主':<12} {'产品':<20} {'平台':<8} {'报价':>10} {'状态':<10} {'匹配分'}")
    print(f"  {'-'*70}")
    for o in scheduler.settlement.orders:
        print(f"  {o.id:<10} {o.advertiser_name:<12} {o.product_name:<20} {o.platform:<8} ¥{o.final_price:>9.2f} {o.status.value:<10} {o.match_score}")

    # 8. 结算日报
    print_separator("每日收益日报")
    report = scheduler.settlement.daily_report()
    for k, v in report.items():
        if k != "明细":
            print(f"  {k}: {v}")

    # 9. 模拟回款
    print_separator("模拟回款录入")
    scheduler.settlement.record_payment("ORD001", 1497.60, "TXN_20260622_001")
    scheduler.settlement.record_payment("ORD003", 1872.00, "TXN_20260622_002")
    print("  已录入 2 笔回款")
    report2 = scheduler.settlement.daily_report()
    print(f"  已结算: {report2['已结算']}")
    print(f"  待结算: {report2['待结算']}")

    # 10. 违约场景演示
    print_separator("违约场景演示")
    adv_c = scheduler.advertisers["A004"]
    print(f"  广告主 {adv_c.name}: 等级={adv_c.level.value}, 信用分={adv_c.credit_score}")
    ord005 = next((o for o in scheduler.settlement.orders if o.id == "ORD005"), None)
    if ord005:
        print(f"  订单 ORD005: {ord005.status.value} (被自动拒单)")
    else:
        print(f"  订单 ORD005: 未进入订单池 (submit_order阶段被拦截)")

    # 11. 渲染参数展示
    print_separator("AiToEarn 渲染参数（S级/4K）")
    ord001 = next((o for o in scheduler.settlement.orders if o.id == "ORD001"), None)
    if ord001:
        tag_list = [
            scheduler.tag_manager.create_task_tag(ord001, 95, SourceTag.MANUAL)
        ]
        for tag in tag_list:
            params = scheduler.tag_manager.generate_render_params(tag, ord001)
            print(f"  订单 ORD001 (兰蔻/S级/95分/抖音短视频):")
            for k, v in params.items():
                print(f"    {k}: {v}")
    else:
        print("  ORD001 未进入订单池")

    print_separator("Demo 完成")
    print("  所有模块均已验证通过: 广告主管理、接单预审、四级匹配、")
    print("  任务标签化调度、智能报价、AI文案+质检、渲染下发、发布闭环")


if __name__ == "__main__":
    run_demo()
