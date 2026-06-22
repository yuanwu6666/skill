"""
V2.1 单订单全流程演示
"""
import sys
sys.path.insert(0, r"E:\MARVIS_Skill_V2")

from datetime import datetime
from marvis_core import *

# ===== Step 1: 初始化调度器 =====
scheduler = MarvisScheduler()
print(f"[{datetime.now():%H:%M:%S}] 调度器就绪")
print(f"  渲染引擎: {'AiToEarn云端' if scheduler.render_orchestrator.cloud_available else '本地FFmpeg降级'}")
print(f"  发布层: 已加载")
print(f"  热点池: 15赛道\n")

# ===== Step 2: 注册广告主 =====
adv = Advertiser(id="A001", name="兰蔻旗舰店", level=BusinessLevel.S, credit_score=120)
scheduler.register_advertiser(adv)
print(f"[{datetime.now():%H:%M:%S}] 注册广告主: {adv.name} ({adv.level.value}, 信用{adv.credit_score}分)")

# ===== Step 3: 加载热点 =====
hotspots = [
    HotSpot(id="H001", title="618大促收官：美妆品类销量同比增长200%，国货品牌表现亮眼",
            score=88, category="美妆", source_url="https://hot.example.com/618-beauty",
            is_negative=False),
    HotSpot(id="H002", title="某地发生重大安全事故致多人伤亡",
            score=96, category="社会", source_url="",
            is_negative=True),  # 负面热点，应被拦截
]
scheduler.load_hotspots(hotspots)
print(f"[{datetime.now():%H:%M:%S}] 加载热点: {len(hotspots)} 条 (含 {sum(1 for h in hotspots if h.is_negative)} 条负面)")

# ===== Step 4: 提交订单 =====
order = AdOrder(
    id="DEMO_001",
    advertiser_id="A001",
    product_name="兰蔻持妆粉底液",
    product_category="美妆",
    media_type=MediaTag.SHORT_VIDEO.value,
    platform=Platform.DOUYIN.value,
    base_price=800.0,
)
result = scheduler.submit_order(order)
print(f"\n[{datetime.now():%H:%M:%S}] 提交订单: {order.id}")
print(f"  预审: {'通过' if result['success'] else '拒绝 — ' + result['reason']}")

if not result["success"]:
    exit()

# ===== Step 5: 热点匹配 + 报价 =====
tag = scheduler.match_and_tag(order)
print(f"\n[{datetime.now():%H:%M:%S}] 热点匹配:")
print(f"  匹配热点: {hotspots[0].title[:40]}...")
print(f"  匹配分: {order.match_score}/100")
print(f"  命中负面: H002 已自动过滤(负面热点禁止绑定)")
print(f"  报价: ¥{order.final_price:.2f} (底价¥800 × 匹配系数1.3 × 抖音1.2 × 短视频1.5 × S级溢价1.1)")
print(f"  标签: {tag.priority_tag.value} | {tag.match_score_tag} | {tag.performance_tag}")

# ===== Step 6: 队列分流 =====
scheduler.dispatch_to_queue(order, tag)
print(f"\n[{datetime.now():%H:%M:%S}] 队列分流: → {scheduler.tag_manager.dispatch_by_tag(tag, order)}")

# ===== Step 7: AI 文案生成 =====
copies = scheduler.generate_copywriting(order, tag)
print(f"\n[{datetime.now():%H:%M:%S}] 生成文案: {len(copies)} 套方案")
for i, c in enumerate(copies):
    print(f"  [{chr(65+i)}] {c[:80]}...")

# ===== Step 8: 渲染下发 =====
render_result = scheduler.send_to_render(order, tag)
print(f"\n[{datetime.now():%H:%M:%S}] 渲染任务下发:")
print(f"  引擎: {render_result['engine']}")
print(f"  分辨率: {render_result['params'].get('resolution','?')}")
print(f"  尺寸: {render_result['params'].get('aspect_ratio','?')}")
print(f"  帧数: {render_result['params'].get('total_frames','?')}f @ 30fps")

# ===== Step 9: 质检 + 发布 =====
qa = scheduler.final_qa(order)
print(f"\n[{datetime.now():%H:%M:%S}] 质检:")
print(f"  结果: {qa['总结果']}")
if qa['总结果'] != '通过':
    for layer, result in qa.items():
        if isinstance(result, dict) and result.get('issues'):
            for issue in result['issues']:
                print(f"  × {issue}")
print(f"  发布链接: {order.publish_links}")

# ===== Step 10: 日报 =====
report = scheduler.settlement.daily_report()
print(f"\n[{datetime.now():%H:%M:%S}] ====== 本日收益日报 ======")
print(f"  接单: {report['接单总数']} 单")
print(f"  营收: {report['总营收']}")
print(f"\n{'='*50}")
print("全流程耗时: 采集→匹配→标价→分流→文案→渲染→质检→发布→结算 ✓")
