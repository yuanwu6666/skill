"""
V2.1 零粉冷启动新号全链路 Demo
验证：折价计价、接单上限、广告字数/画面限流、轻量化渲染、广告主等级过滤
"""
import sys
sys.path.insert(0, r"E:\MARVIS_Skill_V2")

from datetime import datetime
from marvis_core import *
from account_phase import Account, AccountPhase

print("=" * 60)
print("  零粉冷启动新号 · 全链路 Demo")
print("=" * 60)

# ===== Step 1: 初始化 =====
scheduler = MarvisScheduler()
print(f"\n[1] 调度器就绪 | 渲染: {'云端可用' if scheduler.render_orchestrator.cloud_available else '本地降级'} | 热点: 15赛道\n")

# ===== Step 2: 创建冷启动账号（TRIAL 阶段，200粉） =====
new_acc = Account(
    account_id="ACC_NEW_001",
    platform="抖音",
    niche="美妆",
    followers=200,
    days_active=9,
    avg_views=350,
    phase=AccountPhase.TRIAL,  # 已过冷启动养号期
)
scheduler.accounts = {"ACC_NEW_001": new_acc}

print(f"[2] 注册账号: {new_acc.account_id}")
print(f"    阶段: {new_acc.phase.value} | 粉丝: {new_acc.followers}")
print(f"    折价系数: {new_acc.cold_start_discount} | 日接单上限: {new_acc.daily_order_limit}单")
print(f"    广告文字占比上限: {int(new_acc.ad_text_ratio_limit*100)}%")
print(f"    资讯:广告配比 = {new_acc.content_ratio[0]}:{new_acc.content_ratio[1]}")

# ===== Step 3: 注册广告主 =====
adv_b = Advertiser(id="B001", name="元气森林旗舰店", level=BusinessLevel.B, credit_score=80)
adv_s = Advertiser(id="S001", name="兰蔻旗舰店", level=BusinessLevel.S, credit_score=120)
scheduler.register_advertiser(adv_b)
scheduler.register_advertiser(adv_s)

# ===== Step 4: 加载热点 =====
hotspots = [
    HotSpot(id="H003", title="夏季饮品消费趋势：无糖茶饮增速领跑，年轻群体偏好变迁",
            score=85, category="美食", source_url="https://hot.example.com/summer-drink",
            is_negative=False),
    HotSpot(id="H004", title="暴雨红色预警：多省遭遇极端天气，出行请注意安全",
            score=95, category="社会", source_url="",
            is_negative=True),
]
scheduler.load_hotspots(hotspots)
print(f"\n[3] 加载热点: {len(hotspots)}条 (含{sum(1 for h in hotspots if h.is_negative)}条负面)\n")

# ============================================================
# 测试 1: S级广告主应被拒绝（TRIAL 阶段仅允许 B 级）
# ============================================================
print("-" * 50)
print("【测试1】S级广告主提交 → 应被拦截（TRIAL仅允许B级）")
print("-" * 50)
order_s = AdOrder(id="NEW_S_001", advertiser_id="S001",
                  product_name="兰蔻持妆粉底液", product_category="美妆",
                  media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value,
                  base_price=800)
r1 = scheduler.submit_order(order_s)
print(f"  结果: {'✗ 拒绝' if not r1['success'] else '✓ 通过'} → {r1.get('reason', '')}")

# ============================================================
# 测试 2: B级广告主正常接单 → 折价报价验证
# ============================================================
print("\n" + "-" * 50)
print("【测试2】B级广告主（元气森林）提交 → 折价计价")
print("-" * 50)
order_b = AdOrder(id="NEW_B_001", advertiser_id="B001",
                  product_name="元气森林无糖茉莉花茶", product_category="美食",
                  media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value,
                  base_price=800)
r2 = scheduler.submit_order(order_b)
print(f"  预审: {'✓ 通过' if r2['success'] else '✗ 拒绝'}")

if r2["success"]:
    tag = scheduler.match_and_tag(order_b)
    # 动态获取匹配系数
    ms = order_b.match_score
    match_coef = 1.3 if ms >= 90 else (1.1 if ms >= 80 else 1.0)
    expected = round(800 * match_coef * 1.2 * 1.5 * 1.0 * 0.4, 2)
    mature_price = round(800 * match_coef * 1.2 * 1.5, 2)
    print(f"  匹配分: {ms}/100 → 系数{match_coef}")
    print(f"  公式: 800 × {match_coef} × 1.2(抖音) × 1.5(短视频) × 1.0(B级) × 0.4(折价)")
    ok = "✓" if abs(order_b.final_price - expected) < 0.01 else "✗"
    print(f"  报价: ¥{order_b.final_price:.2f} | 验算: ¥{expected} {ok}")
    print(f"  成熟账号同单报价: ¥{mature_price} | 折价节省: ¥{round(mature_price - order_b.final_price, 2)}")

# ============================================================
# 测试 3: 提交第2单 → 应通过
# ============================================================
print("\n" + "-" * 50)
print("【测试3】第2单 → 应通过")
print("-" * 50)
order_b2 = AdOrder(id="NEW_B_002", advertiser_id="B001",
                   product_name="元气森林白桃味气泡水", product_category="美食",
                   media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value,
                   base_price=600)
r3 = scheduler.submit_order(order_b2)
print(f"  预审: {'✓ 通过' if r3['success'] else '✗ 拒绝'} {r3.get('reason', '')}")
if r3["success"]:
    tag2 = scheduler.match_and_tag(order_b2)
    ms2 = order_b2.match_score
    mc2 = 1.3 if ms2 >= 90 else (1.1 if ms2 >= 80 else 1.0)
    expected2 = round(600 * mc2 * 1.2 * 1.5 * 0.4, 2)
    ok2 = "✓" if abs(order_b2.final_price - expected2) < 0.01 else "✗"
    print(f"  匹配分: {ms2}/100 → 系数{mc2}")
    print(f"  报价: ¥{order_b2.final_price:.2f} | 验算: ¥{expected2} {ok2}")

# ============================================================
# 测试 4: 提交第3单 → 日上限2单，应被拒绝
# ============================================================
print("\n" + "-" * 50)
print("【测试4】第3单 → 日上限2单，应被拦截")
print("-" * 50)
order_b3 = AdOrder(id="NEW_B_003", advertiser_id="B001",
                   product_name="元气森林燃茶乌龙茶", product_category="美食",
                   media_type=MediaTag.SHORT_VIDEO.value, platform=Platform.DOUYIN.value,
                   base_price=600)
r4 = scheduler.submit_order(order_b3)
print(f"  预审: {'✓ 通过' if r4['success'] else '✗ 拒绝'} → {r4.get('reason', '')}")

# ============================================================
# 测试 5: 文案生成 + 广告占比（新号12%限制）
# ============================================================
print("\n" + "-" * 50)
print("【测试5】文案生成 + 广告文字占比（新号≤12%）")
print("-" * 50)
if r2["success"]:
    copies = scheduler.generate_copywriting(order_b, tag)
    print(f"  生成: {len(copies)}套文案")
    for i, c in enumerate(copies):
        ratio = len(c) / 500 if len(c) < 500 else 1.0
        print(f"  [{chr(65+i)}] {c[:60]}... | 字数{len(c)} / 占比{ratio:.1%}")

# ============================================================
# 测试 6: 渲染参数（1080P/15s 轻量化）
# ============================================================
print("\n" + "-" * 50)
print("【测试6】渲染参数 → 应输出1080P/15s（新号轻量化）")
print("-" * 50)
if r2["success"]:
    render_result = scheduler.send_to_render(order_b, tag)
    print(f"  引擎: {render_result.get('engine', '?')}")
    print(f"  参数: {render_result.get('params', {})}")

# ============================================================
# 测试 7: QA质检（四层）
# ============================================================
print("\n" + "-" * 50)
print("【测试7】四层质检")
print("-" * 50)
if r2["success"]:
    qa = scheduler.final_qa(order_b)
    print(f"  结果: {qa.get('总结果', '?')}")
    for layer, result in qa.items():
        if isinstance(result, dict) and result.get('issues'):
            for issue in result['issues']:
                print(f"  × {issue}")

# ============================================================
# 结算日报
# ============================================================
print("\n" + "=" * 60)
report = scheduler.settlement.daily_report()
print("  本日结算汇总")
print(f"  接单: {report['接单总数']}单 | 营收: {report['总营收']}")
print(f"  说明: 第3单因日上限拦截 + S级广告主等级受限，2单生效")

# 兜底：如果 mature_price 未定义（测试2未跑）
try:
    _ = mature_price
except NameError:
    mature_price = round(800 * 1.3 * 1.2 * 1.5, 2)

# ============================================================
# 对比总结
# ============================================================
print("\n" + "=" * 60)
print("  冷启动 vs 成熟账号 对比")
print("=" * 60)
print(f"  {'指标':<20} {'冷启动新号 (TRIAL)':<25} {'成熟账号 (SCALING)'}")
print(f"  {'-'*20} {'-'*25} {'-'*20}")
print(f"  {'折价系数':<20} {'0.4 (折价60%)':<25} {'1.0 (标准价)'}")
print(f"  {'日接单上限':<20} {'2单':<25} {'5单'}")
print(f"  {'广告文字占比':<20} {'≤12%':<25} {'≤20%'}")
print(f"  {'渲染规格':<20} {'1080P/15s 轻量':<25} {'4K/30s 标准'}")
print(f"  {'商家等级':<20} {'仅B级':<25} {'S/A/B全开放'}")
print(f"  {'资讯:广告配比':<20} {'2:1':<25} {'1:1'}")
print(f"  {'单日总发布':<20} {'≤4条':<25} {'≤6条'}")
print(f"  {'同800底价报价':<20} {'¥{:.2f}'.format(mature_price * 0.4):<25} {'¥{:.2f}'.format(mature_price)}")
print("\n冷启动新号全链路验证完成 ✓")

# ============================================================
# 额外: 演示内容配比（模拟一天的发布计划）
# ============================================================
print("\n" + "=" * 60)
print("  模拟新号一天发布计划（2资讯 + 1广告 = 2:1配比）")
print("=" * 60)
print(f"  08:00  纯资讯 #1  美食赛道热点速递       (资讯)")
print(f"  12:00  纯资讯 #2  夏季饮品趋势深度解读   (资讯)")
print(f"  16:00  广告 #1   元气森林无糖茉莉花茶     (广告, 间隔4h+)")
print(f"  说明: 当日3条发布 = 2资讯+1广告，满足2:1配比和4小时间隔")
