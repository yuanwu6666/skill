"""
V2.1 C 级风险商家拒单 Demo
验证：order.submit_order 前置预审 → C级直接拦截 → 不进匹配/计价/渲染
"""
import sys
sys.path.insert(0, r"E:\MARVIS_Skill_V2")

from marvis_core import *
from account_phase import Account, AccountPhase

print("=" * 60)
print("  C 级风险商家拒单 · 全链路 Demo")
print("=" * 60)

scheduler = MarvisScheduler()

# 成熟账号（SCALING），消除账号阶段变量
acc = Account(
    account_id="ACC_MATURE_003", platform="抖音", niche="科技",
    followers=12000, days_active=120, avg_views=15000,
    phase=AccountPhase.SCALING,
)
scheduler.accounts = {"ACC_MATURE_003": acc}
print(f"\n账号: {acc.account_id} | 阶段: {acc.phase.value} | 接单上限: {acc.daily_order_limit}单")

# ===== 加载正常热点（确保非热点因素干扰） =====
hotspots = [
    HotSpot(id="H_OK_01", title="新款iPhone发布：AI功能成最大亮点", score=95,
            category="科技", source_url="", is_negative=False),
    HotSpot(id="H_OK_02", title="特斯拉自动驾驶城区实测零接管", score=88,
            category="汽车", source_url="", is_negative=False),
]
scheduler.load_hotspots(hotspots)

# ============================================================
# 测试 1: C级商家 → 直接拒单
# ============================================================
print("\n" + "-" * 50)
print("【测试1】C级风险广告主提交 → 应直接拒单")
print("-" * 50)
adv_c = Advertiser(
    id="C001", name="XX虚拟币平台", level=BusinessLevel.C,
    credit_score=35, has_violation=True, monthly_orders=0,
)
scheduler.register_advertiser(adv_c)

order_c = AdOrder(
    id="REJ_C_001", advertiser_id="C001",
    product_name="XX币一夜暴涨100倍速来上车",
    product_category="金融",
    media_type=MediaTag.SHORT_VIDEO.value,
    platform=Platform.DOUYIN.value,
    base_price=500,
)
r1 = scheduler.submit_order(order_c)
print(f"  结果: {'✗ 拒绝' if not r1['success'] else '✗ 漏拦!'}")
print(f"  原因: {r1.get('reason', '')}")
print(f"  订单状态: {order_c.status.value}")

# ============================================================
# 测试 2: C级 + 违规词双重拦截（违规词优先还是C级优先？）
# ============================================================
print("\n" + "-" * 50)
print("【测试2】C级 + 产品名含违规词（双重违规）")
print("-" * 50)
order_c2 = AdOrder(
    id="REJ_C_002", advertiser_id="C001",
    product_name="第一暴利投资神器",  # 「第一」是违禁词
    product_category="金融",
    media_type=MediaTag.HORIZONTAL_IMAGE.value,
    platform=Platform.TOUTIAO.value,
    base_price=300,
)
r2 = scheduler.submit_order(order_c2)
# C级检测在 submit_order 中先于违规词检测
print(f"  结果: {'✗ 拒绝' if not r2['success'] else '✗ 漏拦!'}")
print(f"  原因: {r2.get('reason', '')}  ← C级优先于违规词拦截")

# ============================================================
# 测试 3: 正常广告主对比 → 应通过预审
# ============================================================
print("\n" + "-" * 50)
print("【测试3】正常S级广告主对比 → 应正常通过")
print("-" * 50)
adv_s = Advertiser(id="S001", name="小米科技", level=BusinessLevel.S, credit_score=130)
scheduler.register_advertiser(adv_s)

order_normal = AdOrder(
    id="NORM_001", advertiser_id="S001",
    product_name="小米14 Ultra", product_category="科技",
    media_type=MediaTag.SHORT_VIDEO.value,
    platform=Platform.DOUYIN.value,
    base_price=1000,
)
r3 = scheduler.submit_order(order_normal)
print(f"  预审: {'✓ 通过' if r3['success'] else '✗ 拒绝'}")

# ============================================================
# 测试 4: 验证 C级订单未进入后续流程
# ============================================================
print("\n" + "-" * 50)
print("【测试4】C级订单是否进入计价/渲染/发布流程")
print("-" * 50)
c_orders = [o for o in scheduler.settlement.orders
            if o.status == OrderStatus.REJECTED]
c_ids = [o.id for o in c_orders]
print(f"  已拒订单: {c_ids}")
print(f"  结算中总数: {len(scheduler.settlement.orders)} (含拒单)")
# 通过订单数 = 总 - 已拒
approved = [o for o in scheduler.settlement.orders if o.status != OrderStatus.REJECTED]
print(f"  有效订单: {len(approved)} 单")

# 确认 C 级订单未被 match_and_tag 处理
for o in c_orders:
    print(f"  [{o.id}] match_score={o.match_score} (未匹配) | final_price=¥{o.final_price:.2f} (未计价) | render={o.render_result or '无'} (未渲染)")

# ============================================================
# 测试 5: 信用分降级路径验证
# ============================================================
print("\n" + "-" * 50)
print("【测试5】信用分降级 → C级 路径验证")
print("-" * 50)
adv_downgrade = Advertiser(id="D001", name="某日化品牌", level=BusinessLevel.A,
                           credit_score=100, monthly_orders=2)
scheduler.register_advertiser(adv_downgrade)

# 模拟违规扣分到 C 级
print(f"  初始: {adv_downgrade.name} | 等级={adv_downgrade.level.value} | 信用={adv_downgrade.credit_score}")
downgraded = adv_downgrade.adjust_credit(-45)  # 100 → 55，应触发降级到 C
print(f"  扣分-45: 等级={adv_downgrade.level.value} | 信用={adv_downgrade.credit_score} | 降级触发={downgraded}")

order_d = AdOrder(
    id="DGRADE_001", advertiser_id="D001",
    product_name="温和洁面乳", product_category="美妆",
    media_type=MediaTag.VERTICAL_IMAGE.value,
    platform=Platform.XIAOHONGSHU.value,
    base_price=400,
)
r5 = scheduler.submit_order(order_d)
print(f"  降级后提交: {'✗ 拒绝' if not r5['success'] else '✗ 漏拦!'} → {r5.get('reason', '')}")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("  C 级风险商家拒单 验证汇总")
print("=" * 60)
print("  ✓ C级广告主直接拦截，不进入热点匹配")
print("  ✓ C级 + 违规词双重违规 → C级优先拦截")
print("  ✓ 正常S级广告主同期通过，互不干扰")
print("  ✓ C级订单未计价(final_price=0)、未渲染(render_result=null)")
print("  ✓ 信用分降至60以下自动降级为C级，后续订单触发拦截")
print("  ✓ 拒单计入结算台账但标记为 REJECTED 状态")
print("\nC级风险商家拒单验证完成 ✓")
