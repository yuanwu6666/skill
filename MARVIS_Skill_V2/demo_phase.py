"""
MARVIS V2.0 - 零粉冷启动 → 稳定变现 完整四阶段 Demo

阶段1: 冷启动养号 (0粉, 7天, 纯资讯)
阶段2: 小规模试单 (7天+, 日2单, 折价0.4, 仅B级)
阶段3: 稳定规模化 (500粉+, 日5单, 标准价, 全等级)
阶段4: 多账号矩阵 (多账号并行)
"""

import sys
sys.path.insert(0, r"E:\MARVIS_Skill_V2")

from marvis_core import (
    MarvisScheduler, build_demo_data,
    AdOrder, Advertiser, HotSpot,
    Platform, MediaTag, PriorityTag, MatchScoreTag, PerformanceTag,
    SourceTag, BusinessLevel, OrderStatus, PricingEngine,
)
from account_phase import Account, AccountPhase
from datetime import datetime, timedelta


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run_phase_demo(scheduler: MarvisScheduler, account: Account, phase_label: str):
    """运行一个阶段的完整流程"""
    print_section(phase_label)

    # 显示账号状态
    s = account.summary()
    print(f"  阶段: {s['阶段']} | 粉丝: {s['粉丝']} | 日接单上限: {s['单日接单上限']} | 折价: {s['折价系数']}")

    # 提交订单
    orders_to_submit = [
        AdOrder(id="ORD_A1", advertiser_id="A001", product_name="兰蔻持粉底液",
                product_category="美妆", media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value, base_price=800.0),
        AdOrder(id="ORD_A2", advertiser_id="A002", product_name="小米14 Ultra",
                product_category="科技", media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value, base_price=1000.0),
        AdOrder(id="ORD_A3", advertiser_id="A003", product_name="元气森林樱花限定",
                product_category="快消", media_type=MediaTag.HORIZONTAL_IMAGE.value, platform=Platform.TOUTIAO.value, base_price=400.0),
        AdOrder(id="ORD_A4", advertiser_id="A001", product_name="兰蔻菁纯面霜",
                product_category="美妆", media_type=MediaTag.VERTICAL_IMAGE.value, platform=Platform.XIAOHONGSHU.value, base_price=600.0),
    ]

    accepted = 0
    rejected = 0
    for o in orders_to_submit:
        result = scheduler.submit_order(o)
        if result["success"]:
            accepted += 1
        else:
            rejected += 1
            print(f"  ✗ {o.id} 被拒: {result['reason']}")

    print(f"\n  提交 {len(orders_to_submit)} 笔 → 通过 {accepted} / 拒绝 {rejected}")

    if accepted == 0:
        print(f"  当前阶段无可用订单，跳过后续流程。")
        # 生成纯资讯内容（冷启动）
        if account.phase == AccountPhase.COLD_START:
            print(f"  >>> 冷启动模式：生成纯资讯内容，不接广告 <<<")
            for i in range(account.post_limit_per_day):
                print(f"    发布 #{i+1}: 纯资讯短视频（无推广） → 模拟发布成功")
            account.total_posts += account.post_limit_per_day
        return

    # 跑全流程
    log = scheduler.run_full_pipeline()
    print()
    for step in log["steps"]:
        if "order" in step:
            print(f"  ▸ {step['order']} | 匹配:{step.get('match_score','N/A')}分 | 报价:{step.get('price','N/A')}")
            print(f"    队列:{step.get('queue','N/A')} | 文案:{step.get('copies',0)}套 | 质检:{step.get('qa','N/A')}")

    # 汇总
    today_orders = [o for o in scheduler.settlement.orders
                    if o.created_at.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d")
                    and o.status not in (OrderStatus.REJECTED, OrderStatus.CANCELLED)]
    total = sum(o.final_price for o in today_orders)
    account.total_revenue += total
    account.total_orders += len(today_orders)
    print(f"\n  本阶段累计: {len(today_orders)}单, 营收 ¥{total:,.2f}")


def main():
    print_section("MARVIS V2.0 零粉冷启动 → 稳定变现 四阶段全景 Demo")
    print("  架构: MARVIS(主控) → AiToEarn(渲染)  单向调度")

    # ==================== 初始化 ====================
    scheduler = MarvisScheduler()

    # 注册广告主
    advertisers = [
        Advertiser(id="A001", name="兰蔻旗舰店", level=BusinessLevel.S, credit_score=120),
        Advertiser(id="A002", name="小米科技", level=BusinessLevel.A, credit_score=105),
        Advertiser(id="A003", name="元气森林", level=BusinessLevel.B, credit_score=100),
        Advertiser(id="A004", name="XX虚拟币平台", level=BusinessLevel.C, credit_score=45, has_violation=True),
    ]
    for a in advertisers:
        scheduler.register_advertiser(a)

    # 加载热点
    hotspots = [
        HotSpot(id="H001", title="新款iPhone发布：AI功能成最大亮点", score=95,
                category="科技", source_url="https://example.com/h001", is_negative=False),
        HotSpot(id="H002", title="全国多地特大暴雨洪涝灾害", score=98,
                category="社会", source_url="https://example.com/h002", is_negative=True),
        HotSpot(id="H003", title="特斯拉新款自动驾驶实测：城区零接管", score=88,
                category="汽车", source_url="https://example.com/h003", is_negative=False),
        HotSpot(id="H004", title="618大促：美妆品类销量同比增长200%", score=85,
                category="美妆", source_url="https://example.com/h004", is_negative=False),
    ]
    scheduler.load_hotspots(hotspots)

    # ==================== 阶段1: 冷启动养号 ====================
    account = Account(
        account_id="ACC_DOUYIN_01",
        platform="抖音",
        niche="美妆",
        followers=0,
        phase=AccountPhase.COLD_START,
        created_at=datetime.now() - timedelta(days=1),
    )
    scheduler.register_account(account)
    run_phase_demo(scheduler, account, "阶段1: 冷启动养号 (0粉丝，纯资讯，不接广告)")

    # ==================== 阶段2: 小规模试单 ====================
    # 模拟7天后账号数据
    account.followers = 320
    account.update_metrics(views=450, likes=28)
    account.created_at = datetime.now() - timedelta(days=8)
    account.days_active = 8
    account.phase = AccountPhase.COLD_START
    upgraded = account.check_phase_upgrade()
    print(f"\n  >>> 账号升级检测: {'已升级到 ' + account.phase.value if upgraded else '未满足条件'}")

    # 重新创建 scheduler（清空历史订单，模拟新一天）
    scheduler2 = MarvisScheduler()
    for a in advertisers: scheduler2.register_advertiser(a)
    scheduler2.load_hotspots(hotspots)
    scheduler2.register_account(account)
    run_phase_demo(scheduler2, account, "阶段2: 小规模试单 (320粉，日2单，折价0.4，仅B级)")

    # ==================== 阶段3: 稳定规模化 ====================
    # 模拟粉丝增长到500+
    account.followers = 1200
    account.update_metrics(views=3500, likes=180)
    account.phase = AccountPhase.TRIAL
    upgraded = account.check_phase_upgrade()
    print(f"\n  >>> 账号升级检测: {'已升级到 ' + account.phase.value if upgraded else '未满足条件'}")

    scheduler3 = MarvisScheduler()
    for a in advertisers: scheduler3.register_advertiser(a)
    scheduler3.load_hotspots(hotspots)
    scheduler3.register_account(account)
    run_phase_demo(scheduler3, account, "阶段3: 稳定规模化 (1200粉，日5单，标准价，全等级开放)")

    # ==================== 阶段4: 多账号矩阵 ====================
    account.phase = AccountPhase.MATRIX

    # 第二个账号
    account2 = Account(
        account_id="ACC_REDBOOK_01",
        platform="小红书",
        niche="美妆",
        followers=680,
        phase=AccountPhase.SCALING,
    )

    print_section("阶段4: 多账号矩阵")
    print(f"  主账号 [抖音/美妆]: {account.followers:,}粉, 阶段={account.phase.value}")
    print(f"  子账号 [小红书/美妆]: {account2.followers:,}粉, 阶段={account2.phase.value}")
    print(f"  矩阵日接单: 主号{account.daily_order_limit}单 + 子号{account2.daily_order_limit}单 = {account.daily_order_limit + account2.daily_order_limit}单/天")

    # ==================== 收益汇总 ====================
    print_section("四阶段收益总览")

    # 模拟累计数据
    total_revenue = 0
    print(f"  {'阶段':<16} {'模式':<12} {'折价':<8} {'日均单':<8} {'预估月收'}")
    print(f"  {'-'*60}")

    phases_data = [
        ("阶段1-冷启动", "纯资讯", "0.0", "0", "¥0 (积累流量资产)"),
        ("阶段2-试单", "B级轻植入", "0.4", "2", f"¥{2 * 400 * 1.0 * 1.0 * 1.0 * 0.4 * 30:,.0f} (基础)"),
        ("阶段3-规模化", "全等级", "1.0", "5", f"¥{5 * 600 * 1.1 * 1.2 * 1.5 * 1.1 * 30:,.0f} (含S级溢价)"),
        ("阶段4-矩阵", "多号×2", "1.0", "10+", "¥20,000~¥50,000+"),
    ]
    for phase, mode, discount, daily, monthly in phases_data:
        print(f"  {phase:<16} {mode:<12} {discount:<8} {daily:<8} {monthly}")

    print(f"\n  >>> 全链路自动化降本优势 <<<")
    print(f"  无人工找热点 / 无外包写文案 / 无外包剪辑美工 / 无人工对账")
    print(f"  单人可同时运营 3-5 个赛道账号，批量承接广告")

    print_section("Demo 完成")


if __name__ == "__main__":
    main()
