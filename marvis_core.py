"""
MARVIS 全域热点广告变现自动化Skill V2.0 - 核心调度引擎
单向调度架构：MARVIS → AiToEarn（纯渲染节点），无反向调用

新增集成（V2.1）：
- hotspot_collector: 15赛道热点池 + RSS 采集
- aitoearn_connector: 真实 AiToEarn API + 本地降级渲染
- platform_api: 微信公众号 + 多平台发布 API
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import json

# 阶段引擎
try:
    from account_phase import Account, AccountPhase
except ImportError:
    Account = None
    AccountPhase = None

# 热点采集引擎（15赛道）
try:
    from hotspot_collector import HotSpotCollector, NICHE_KEYWORDS
except ImportError:
    HotSpotCollector = None
    NICHE_KEYWORDS = {}

# AiToEarn 渲染连接器
try:
    from aitoearn_connector import (
        RenderOrchestrator, RenderRequest, RenderResult,
        RenderEngine, RenderStatus,
    )
except ImportError:
    RenderOrchestrator = None

# 多平台发布 API + 粉丝互动
try:
    from platform_api import MultiPlatformPublisher, PublishResult, FanInteractionManager
except ImportError:
    MultiPlatformPublisher = None
    FanInteractionManager = None


# ==================== 枚举定义 ====================

class PriorityTag(str, Enum):
    P0 = "P0加急"
    P1 = "P1高优"
    P2 = "P2常规"
    P3 = "P3低优"

class BusinessLevel(str, Enum):
    S = "S头部"
    A = "A优质"
    B = "B散单"
    C = "C风险"

class MediaTag(str, Enum):
    SHORT_VIDEO = "9:16短视频"
    VERTICAL_IMAGE = "竖版图文"
    HORIZONTAL_IMAGE = "16:9横版图"

class MatchScoreTag(str, Enum):
    HIGH = "90-100高分爆款"
    MID_HIGH = "80-89中高分"
    QUALIFIED = "70-79合格"

class SourceTag(str, Enum):
    SCHEDULED = "定时自动任务"
    MANUAL = "人工加急任务"
    REVIEW = "复盘补量任务"

class PerformanceTag(str, Enum):
    STANDARD = "标准画质"
    LIGHTWEIGHT = "降级轻量化画质"

class OrderStatus(str, Enum):
    PENDING = "待接单"
    APPROVED = "预审通过"
    COPYWRITING = "待文案生成"
    RENDERING = "待AiToEarn渲染"
    QA_DONE = "质检完成"
    PUBLISHED = "已投放"
    SETTLING = "待结算"
    SETTLED = "已结清"
    REJECTED = "已拒单"
    CANCELLED = "已取消"

class Platform(str, Enum):
    DOUYIN = "抖音"
    XIAOHONGSHU = "小红书"
    TOUTIAO = "头条"
    SHIPINHAO = "视频号"
    ZHIHU = "知乎"

# ==================== 数据结构 ====================

@dataclass
class TaskTag:
    priority_tag: PriorityTag
    business_tag: str          # BusinessLevel.value
    media_tag: str             # MediaTag.value
    match_score_tag: str       # MatchScoreTag.value
    source_tag: str            # SourceTag.value
    performance_tag: str       # PerformanceTag.value

    def to_dict(self):
        return {
            "priority_tag": str(self.priority_tag),
            "business_tag": self.business_tag,
            "media_tag": self.media_tag,
            "match_score_tag": self.match_score_tag,
            "source_tag": self.source_tag,
            "performance_tag": self.performance_tag,
        }


@dataclass
class HotSpot:
    id: str
    title: str
    score: int           # 0-100
    category: str        # 行业赛道
    source_url: str
    is_negative: bool    # 负面热点标记
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Advertiser:
    id: str
    name: str
    level: BusinessLevel
    credit_score: int = 100
    monthly_orders: int = 0
    total_orders: int = 0
    has_violation: bool = False

    def adjust_credit(self, delta: int) -> bool:
        """调整信用分，返回是否触发降级"""
        self.credit_score = max(0, min(self.credit_score + delta, 200))
        if self.credit_score < 60:
            self.level = BusinessLevel.C
            return True
        return False


@dataclass
class AdOrder:
    id: str
    advertiser_id: str
    product_name: str
    product_category: str
    media_type: str            # MediaTag.value
    platform: str              # Platform.value
    advertiser_name: str = ""           # 由 submit_order 从注册广告主回填
    advertiser_level: BusinessLevel = BusinessLevel.B  # 由 submit_order 回填
    status: OrderStatus = OrderStatus.PENDING
    hot_spot_id: Optional[str] = None
    match_score: int = 0       # 热点-广告匹配分 0-100
    base_price: float = 500.0  # 账号基础底价
    final_price: float = 0.0
    copywriting: list = field(default_factory=list)
    render_result: Optional[str] = None
    qa_report: Optional[dict] = None
    publish_links: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    settled: bool = False

    def to_summary(self):
        return {
            "订单ID": self.id,
            "广告主": self.advertiser_name,
            "等级": str(self.advertiser_level),
            "产品": self.product_name,
            "平台": self.platform,
            "状态": str(self.status),
            "匹配分": self.match_score,
            "报价": f"¥{self.final_price:.2f}",
            "已结算": "是" if self.settled else "否",
        }


@dataclass
class RenderTask:
    task_id: str
    order_id: str
    prompt: str
    params: dict
    status: str = "pending"


# ==================== 任务标签管理器 ====================

class TaskTagManager:
    """任务标签生成与队列分流"""

    # 算力分配
    GPU_ALLOCATION = {
        "high": 0.30,    # P0/P1 高优队列 30%
        "normal": 0.50,  # P2 常规队列 50%
        "low": 0.20,     # P3 低优兜底 20%
    }

    def __init__(self):
        self._gpu_load = 0.0

    def set_gpu_load(self, load: float):
        self._gpu_load = load

    def get_gpu_load(self) -> float:
        return self._gpu_load

    def create_task_tag(
        self,
        order: AdOrder,
        hot_score: int,
        task_source: SourceTag,
    ) -> TaskTag:
        """生成完整任务标签"""
        # 广告主等级→优先级
        if order.advertiser_level in (BusinessLevel.S, BusinessLevel.A):
            priority_tag = PriorityTag.P1
        elif order.advertiser_level == BusinessLevel.B:
            priority_tag = PriorityTag.P2
        else:
            priority_tag = PriorityTag.P3

        # 热点匹配分标签
        if hot_score >= 90:
            match_tag = MatchScoreTag.HIGH
        elif hot_score >= 80:
            match_tag = MatchScoreTag.MID_HIGH
        else:
            match_tag = MatchScoreTag.QUALIFIED

        # 算力标签
        gpu_load = self.get_gpu_load()
        perf_tag = PerformanceTag.LIGHTWEIGHT if gpu_load >= 90 else PerformanceTag.STANDARD

        return TaskTag(
            priority_tag=priority_tag,
            business_tag=order.advertiser_level.value,
            media_tag=order.media_type,
            match_score_tag=match_tag.value,
            source_tag=task_source.value,
            performance_tag=perf_tag.value,
        )

    def dispatch_by_tag(self, tag: TaskTag, order: AdOrder) -> str:
        """分流至对应队列"""
        if tag.priority_tag in (PriorityTag.P0, PriorityTag.P1):
            return "high_priority_queue"
        elif tag.priority_tag == PriorityTag.P2:
            return "normal_queue"
        else:
            return "low_priority_queue"

    def generate_render_params(self, tag: TaskTag, order: AdOrder,
                               account_phase: Optional['AccountPhase'] = None) -> dict:
        """根据标签 + 账号阶段动态生成 AiToEarn 渲染参数

        优先级: 账号阶段 > 商家等级 > 算力标签
        冷启动新号: 强制 1080P/15s/轻量化，无视其他参数
        """
        params = {"model": "default", "format": "mp4"}
        media_type = order.media_type

        # === V2.1: 账号冷启动阶段感知（最高优先级） ===
        is_cold_start = (
            account_phase is not None
            and account_phase.value in ("冷启动养号", "小规模试单")
        )

        if is_cold_start:
            # 冷启动强制轻量化规格
            params["resolution"] = "1080P"
            params["video_duration"] = 15
            params["model"] = "lightweight_model"
            params["ad_area_ratio"] = 0.12  # 广告画面占比上限 12%
        elif tag.performance_tag == PerformanceTag.STANDARD.value:
            if tag.business_tag in (BusinessLevel.S.value,):
                params["resolution"] = "4K"
                params["video_duration"] = 45
            elif tag.business_tag == BusinessLevel.A.value:
                params["resolution"] = "1080P"
                params["video_duration"] = 30
            else:
                params["resolution"] = "1080P"
                params["video_duration"] = 25
        else:
            params["resolution"] = "720P"
            params["video_duration"] = 15
            params["model"] = "lightweight_model"

        # 载体尺寸
        if media_type == MediaTag.SHORT_VIDEO.value:
            params["aspect_ratio"] = "9:16"
        elif media_type == MediaTag.VERTICAL_IMAGE.value:
            params["aspect_ratio"] = "3:4"
        else:
            params["aspect_ratio"] = "16:9"

        if "video_duration" in params:
            params["total_frames"] = params["video_duration"] * 30  # 30fps

        return params


# ==================== 四级热点广告匹配模型 ====================

class HotAdMatcher:
    """四级匹配模型：总分100，70分门槛"""

    NEGATIVE_KEYWORDS = ["灾难", "事故", "坠机", "爆炸", "地震", "洪水",
                          "火灾", "恐怖", "战争", "疫情", "空难", "矿难"]

    def __init__(self):
        self.hotspots: list[HotSpot] = []
        self.blacklist_keywords = self.NEGATIVE_KEYWORDS[:]

    def add_hotspot(self, hotspot: HotSpot):
        self.hotspots.append(hotspot)

    def is_negative_hotspot(self, title: str) -> bool:
        """检测负面热点"""
        for kw in self.blacklist_keywords:
            if kw in title:
                return True
        return False

    def match(self, hotspot: HotSpot, order: AdOrder) -> dict:
        """四级匹配打分"""
        details = {}

        # 检测负面热点 → 直接归零
        if hotspot.is_negative:
            return {"total": 0, "details": {"blocked": "负面热点禁止绑定广告"}, "eligible": False}

        # 一级：行业赛道匹配（45分）
        # 从 NICHE_KEYWORDS 动态获取关键词（支持15赛道）
        if NICHE_KEYWORDS:
            cat_keywords = NICHE_KEYWORDS.get(order.product_category, {}).get("cn", [order.product_category])
        else:
            # 兜底硬编码
            _fallback = {
                "美妆": ["美妆", "护肤", "彩妆", "化妆"],
                "科技": ["科技", "AI", "手机", "数码", "芯片"],
                "汽车": ["汽车", "新能源", "电动车", "自驾"],
                "快消": ["食品", "饮料", "零食", "日化"],
                "服饰": ["服装", "穿搭", "时尚", "潮牌"],
                "游戏": ["游戏", "电竞", "手游", "主机"],
            }
            cat_keywords = _fallback.get(order.product_category, [order.product_category])
        cat_score = 0
        for kw in cat_keywords:
            if kw in hotspot.title or kw in hotspot.category:
                cat_score = 45
                break
        if cat_score == 0:
            # 部分匹配
            cat_score = 20
        details["一级-行业赛道"] = cat_score

        # 二级：受众匹配（25分）— 简化：基于产品品类与热点类别交集
        audience_score = 20 if cat_score >= 20 else 10
        details["二级-受众匹配"] = audience_score

        # 三级：场景关联（20分）
        scene_score = 15 if cat_score >= 20 else 5
        details["三级-场景关联"] = scene_score

        # 四级：情绪调性（10分）
        details["四级-情绪调性"] = 10  # 默认满分，负面已被拦截

        total = sum(details.values())
        eligible = total >= 70
        return {
            "total": total,
            "details": details,
            "eligible": eligible,
        }


# ==================== 报价计算引擎 ====================

class PricingEngine:
    """标准化自动报价公式 + 冷启动折价"""

    PLATFORM_COEFFICIENTS = {
        Platform.DOUYIN.value: 1.2,
        Platform.XIAOHONGSHU.value: 1.2,
        Platform.TOUTIAO.value: 1.0,
        Platform.SHIPINHAO.value: 1.0,
        Platform.ZHIHU.value: 0.9,
    }

    MEDIA_COEFFICIENTS = {
        MediaTag.SHORT_VIDEO.value: 1.5,
        MediaTag.VERTICAL_IMAGE.value: 1.0,
        MediaTag.HORIZONTAL_IMAGE.value: 1.0,
    }

    def calculate(self, order: AdOrder, cold_start_discount: float = 1.0) -> float:
        """最终报价 = 基础底价 × 匹配分系数 × 平台系数 × 载体系数 × 商家溢价 × 冷启动折价"""
        # 匹配分系数
        if order.match_score >= 90:
            match_coef = 1.3
        elif order.match_score >= 80:
            match_coef = 1.1
        else:
            match_coef = 1.0

        platform_coef = self.PLATFORM_COEFFICIENTS.get(order.platform, 1.0)
        media_coef = self.MEDIA_COEFFICIENTS.get(order.media_type, 1.0)

        # 商家溢价
        biz_premium = 1.10 if order.advertiser_level == BusinessLevel.S else 1.0

        final_price = order.base_price * match_coef * platform_coef * media_coef * biz_premium * cold_start_discount
        return round(final_price, 2)


# ==================== 内容质检引擎 ====================

class ContentQAEngine:
    """三层全维度内容质检"""

    BLOCKED_WORDS = [
        "最", "第一", "唯一", "国家级", "世界级", "顶级",
        "绝对", "永久", "万能", "根治", "治愈", "彻底",
        "100%", "百分百", "无效退款", "立竿见影",
    ]

    def __init__(self):
        self.qa_records: list[dict] = []

    def check_copywriting(self, text: str) -> dict:
        """文字合规层"""
        issues = []
        violations = [w for w in self.BLOCKED_WORDS if w in text]
        if violations:
            for w in violations:
                issues.append(f"违规词「{w}」")

        # 广告文字占比
        ad_ratio = len(text) / 500  # 简化
        if ad_ratio > 0.20:
            issues.append("广告文字占比超过20%阈值")

        # 检查是否包含「推广」标识
        if "推广" not in text and "广告" not in text:
            issues.append("缺少「推广」或「广告」标识")

        return {"passed": len(issues) == 0, "issues": issues}

    def check_scene_fusion(self, copy_text: str, hotspot_title: str) -> dict:
        """文案融合层：校验广告是否依托热点场景"""
        # 简化：检查文案中是否提及热点关键词
        keywords = hotspot_title[:4]
        fusion_ok = keywords in copy_text
        return {
            "passed": fusion_ok,
            "issues": [] if fusion_ok else [f"文案未融入热点场景「{hotspot_title[:30]}...」"],
        }

    def check_visual_compliance(self, render_result: str) -> dict:
        """画面合规层：视觉检测（mock）"""
        return {"passed": True, "issues": []}

    def full_check(self, text: str, hotspot_title: str, render_result: str = "") -> tuple:
        """全量质检"""
        text_result = self.check_copywriting(text)
        fusion_result = self.check_scene_fusion(text, hotspot_title)
        visual_result = self.check_visual_compliance(render_result)

        all_passed = text_result["passed"] and fusion_result["passed"] and visual_result["passed"]
        report = {
            "文字合规": text_result,
            "文案融合": fusion_result,
            "画面合规": visual_result,
            "总结果": "通过" if all_passed else "不通过",
        }
        self.qa_records.append(report)
        return all_passed, report


# ==================== 结算台账引擎 ====================

class SettlementEngine:
    """全链路自动结算台账"""

    def __init__(self):
        self.orders: list[AdOrder] = []
        self.payment_records: list[dict] = []

    def add_order(self, order: AdOrder):
        self.orders.append(order)

    def record_payment(self, order_id: str, amount: float, txn_ref: str):
        """录入回款"""
        self.payment_records.append({
            "order_id": order_id,
            "amount": amount,
            "status": "全额回款",
            "txn_ref": txn_ref,
            "timestamp": datetime.now().isoformat(),
        })
        for o in self.orders:
            if o.id == order_id:
                o.settled = True
                break

    def daily_report(self) -> dict:
        """每日收益日报"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily = [o for o in self.orders if o.created_at.strftime("%Y-%m-%d") == today]
        total_revenue = sum(o.final_price for o in daily)
        settled_total = sum(o.final_price for o in daily if o.settled)
        return {
            "日期": today,
            "接单总数": len(daily),
            "总营收": f"¥{total_revenue:.2f}",
            "已结算": f"¥{settled_total:.2f}",
            "待结算": f"¥{total_revenue - settled_total:.2f}",
            "明细": [o.to_summary() for o in daily],
        }


# ==================== MARVIS 主控调度器 ====================

class MarvisScheduler:
    """MARVIS 全局主控调度中心（单向调度 AiToEarn）"""

    def __init__(
        self,
        render_api_key: str = "",
        render_api_base: str = "https://api.aitoearn.com/v2",
    ):
        self.tag_manager = TaskTagManager()
        self.matcher = HotAdMatcher()
        self.pricing = PricingEngine()
        self.qa_engine = ContentQAEngine()
        self.settlement = SettlementEngine()

        # 三级队列
        self.high_priority_queue: list[AdOrder] = []
        self.normal_queue: list[AdOrder] = []
        self.low_priority_queue: list[AdOrder] = []

        # 广告主存储
        self.advertisers: dict[str, Advertiser] = {}

        # 热点存储
        self.hotspots: list[HotSpot] = []

        # 账号管理
        self.accounts: dict[str, 'Account'] = {}  # forward ref

        # 历史记录
        self.execution_log: list[dict] = []

        # === V2.1 新增：真实服务连接器 ===
        # 渲染编排器（AiToEarn 云端 + 本地降级）
        self.render_orchestrator = None
        if RenderOrchestrator:
            self.render_orchestrator = RenderOrchestrator(
                cloud_api_key=render_api_key,
                cloud_api_base=render_api_base,
                local_output_dir=r"E:\MARVIS_Skill_V2\render_output",
            )

        # 多平台发布器
        self.publisher = MultiPlatformPublisher() if MultiPlatformPublisher else None

        # 热点采集器（15赛道）
        self.hotspot_collector = HotSpotCollector() if HotSpotCollector else None

    def configure_wechat(self, app_id: str, app_secret: str):
        """配置微信公众号 API 凭证"""
        if self.publisher:
            self.publisher.configure_wechat(app_id, app_secret)

    def configure_render_api(self, api_key: str):
        """更新 AiToEarn 云端 API Key"""
        if self.render_orchestrator:
            self.render_orchestrator.cloud.api_key = api_key
            self.render_orchestrator.cloud_available = True

    def register_advertiser(self, adv: Advertiser):
        self.advertisers[adv.id] = adv

    def load_hotspots(self, hotspots: list[HotSpot]):
        self.hotspots = hotspots
        for hs in hotspots:
            self.matcher.add_hotspot(hs)

    def register_account(self, acc: 'Account'):
        """注册账号到调度器，取 forward ref"""
        self.accounts[acc.account_id] = acc

    def submit_order(self, order: AdOrder) -> dict:
        """接单预审入口（含阶段限制校验）"""
        adv = self.advertisers.get(order.advertiser_id)
        if adv:
            order.advertiser_level = adv.level
            order.advertiser_name = adv.name

        # C级风险广告主：拒单
        if order.advertiser_level == BusinessLevel.C:
            order.status = OrderStatus.REJECTED
            return {"success": False, "reason": "广告主为C级风险等级，自动拒单"}

        # 合规预审（仅校验产品名违禁词，不要求「推广」标识）
        blocked = [w for w in self.qa_engine.BLOCKED_WORDS if w in order.product_name]
        if blocked:
            order.status = OrderStatus.REJECTED
            return {"success": False, "reason": f"产品名含违规词: {blocked}"}

        # 账号阶段限制校验
        if self.accounts:
            acc = list(self.accounts.values())[0]  # 取第一个账号
            # 冷启动阶段不接广告
            if acc.phase == AccountPhase.COLD_START:
                order.status = OrderStatus.REJECTED
                return {"success": False, "reason": f"账号处于冷启动阶段，暂不接广告"}
            # 广告主等级限制
            allowed = acc.allowed_business_levels
            if allowed and order.advertiser_level.value not in allowed:
                order.status = OrderStatus.REJECTED
                return {"success": False, "reason": f"当前阶段仅允许{allowed}级广告主"}
            # 日接单上限
            today_orders = [o for o in self.settlement.orders
                          if o.created_at.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d")
                          and o.status not in (OrderStatus.REJECTED, OrderStatus.CANCELLED)]
            if len(today_orders) >= acc.daily_order_limit:
                order.status = OrderStatus.REJECTED
                return {"success": False, "reason": f"已达今日接单上限({acc.daily_order_limit}单)"}

        order.status = OrderStatus.APPROVED
        self.settlement.add_order(order)
        return {"success": True, "order_id": order.id}

    def match_and_tag(self, order: AdOrder) -> Optional[TaskTag]:
        """热点匹配 + 任务标签生成"""
        if not self.hotspots:
            return None

        # 选最高分热点
        best_match = None
        best_score = 0
        for hs in self.hotspots:
            if hs.is_negative:
                continue
            result = self.matcher.match(hs, order)
            if result["eligible"] and result["total"] > best_score:
                best_score = result["total"]
                best_match = hs

        if best_match is None:
            order.status = OrderStatus.PENDING
            return None

        order.match_score = best_score
        order.hot_spot_id = best_match.id

        # 计算报价（含冷启动折价）
        cold_discount = 1.0
        if self.accounts:
            acc = list(self.accounts.values())[0]
            cold_discount = acc.cold_start_discount
        order.final_price = self.pricing.calculate(order, cold_start_discount=cold_discount)

        # 生成任务标签
        tag = self.tag_manager.create_task_tag(
            order=order,
            hot_score=best_score,
            task_source=SourceTag.SCHEDULED,
        )
        return tag

    def dispatch_to_queue(self, order: AdOrder, tag: TaskTag):
        """分流到三级队列"""
        target = self.tag_manager.dispatch_by_tag(tag, order)
        if target == "high_priority_queue":
            self.high_priority_queue.append(order)
        elif target == "normal_queue":
            self.normal_queue.append(order)
        else:
            self.low_priority_queue.append(order)
        order.status = OrderStatus.COPYWRITING

    def generate_copywriting(self, order: AdOrder, tag: TaskTag) -> list[str]:
        """AI文案生成（动态热点植入 + 账号阶段感知）

        两套差异化软植入方案，自动提取热点关键词并植入产品信息。
        冷启动账号: 文字占比≤12%（约60字符），成熟账号: ≤20%（约100字符）。
        """
        hs = next((h for h in self.hotspots if h.id == order.hot_spot_id), None)
        hotspot_title = hs.title if hs else "热点资讯"

        # V2.1: 提取热点关键词（标题前8字为场景锚点 + 赛道关键词）
        scene_anchor = hotspot_title[:8] if len(hotspot_title) >= 8 else hotspot_title
        category = getattr(hs, 'category', order.product_category) if hs else order.product_category

        # V2.1: 账号阶段感知 → 控制文案长度
        max_chars = 100  # 默认 20%
        if self.accounts:
            acc = list(self.accounts.values())[0]
            ratio_limit = acc.ad_text_ratio_limit
            max_chars = int(500 * ratio_limit)  # 12%=60, 20%=100

        # 方案A：资讯融合风 — 以热点话题开头，自然过渡到产品推荐
        product_short = order.product_name[:10] + "…" if len(order.product_name) > 10 else order.product_name
        plan_a = (
            f"{scene_anchor}趋势引发关注，{category}赛道热度飙升。"
            f"实测{product_short}表现抢眼，值得参考【推广】"
        )

        # 方案B：体验测评风 — 热点数据引入 + 实测分享
        plan_b = (
            f"近期{category}圈热议{scene_anchor}话题，"
            f"顺带分享{product_short}使用体验，意外好用【广告】"
        )

        # 截断到长度限制
        if len(plan_a) > max_chars:
            plan_a = plan_a[:max_chars - 5] + "…【推广】"
        if len(plan_b) > max_chars:
            plan_b = plan_b[:max_chars - 5] + "…【广告】"

        # 文案质检
        for plan_name, text in [("方案A", plan_a), ("方案B", plan_b)]:
            passed, report = self.qa_engine.full_check(text, hotspot_title)
            if not passed:
                # 尝试修复违规词
                fixed = text
                for w in self.qa_engine.BLOCKED_WORDS:
                    fixed = fixed.replace(w, "")
                if fixed != text:
                    passed2, _ = self.qa_engine.full_check(fixed, hotspot_title)
                    if not passed2:
                        continue
                    text = fixed
                else:
                    continue
            order.copywriting.append(text)

        return order.copywriting

    def send_to_render(self, order: AdOrder, tag: TaskTag) -> dict:
        """下发渲染任务到 AiToEarn（云端优先 → 本地降级）"""
        # V2.1: 注入账号阶段参数，冷启动感知渲染时长
        account_phase = None
        if self.accounts:
            acc = list(self.accounts.values())[0]
            account_phase = acc.phase
        render_params = self.tag_manager.generate_render_params(tag, order, account_phase=account_phase)
        prompt = order.copywriting[0] if order.copywriting else "默认广告素材"

        # V2.1: 加载赛道 LUT 滤镜配置
        lut_config = {}
        try:
            import json, os
            lut_path = os.path.join(os.path.dirname(__file__), "filter_lut_config.json")
            if os.path.exists(lut_path):
                with open(lut_path, "r", encoding="utf-8") as f:
                    lut_data = json.load(f)
                niche = getattr(order, "product_category", "")
                track = lut_data.get("tracks", {}).get(niche, {})
                if track:
                    lut_config = track.get("lut", {})
                    lut_config["track_key"] = track.get("key", "")
                    lut_config["track_name"] = niche
        except Exception:
            pass  # LUT 加载失败不影响渲染主流程

        if self.render_orchestrator:
            # === V2.1：真实渲染连接器 ===
            from hashlib import md5
            task_id = f"render_{order.id}_{md5(prompt.encode()).hexdigest()[:8]}"
            render_request = RenderRequest(
                task_id=task_id,
                order_id=order.id,
                prompt=prompt,
                width={"9:16": 1080, "3:4": 810, "16:9": 1920}.get(
                    render_params.get("aspect_ratio", "9:16"), 1080,
                ),
                height={"9:16": 1920, "3:4": 1080, "16:9": 1080}.get(
                    render_params.get("aspect_ratio", "9:16"), 1920,
                ),
                duration_sec=render_params.get("video_duration", 30),
                resolution=render_params.get("resolution", "1080P"),
                lut_config=lut_config,
            )

            result = self.render_orchestrator.submit_render(render_request)
            order.render_result = result.output_path or result.output_url
            order.status = OrderStatus.RENDERING if result.status == RenderStatus.PROCESSING else OrderStatus.QA_DONE

            return {
                "task_id": task_id,
                "result": order.render_result,
                "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                "engine": result.metadata.get("engine", "aitoearn_cloud"),
                "params": render_params,
            }

        # 兜底：纯 Mock
        render_task = RenderTask(
            task_id=f"render_{order.id}",
            order_id=order.id,
            prompt=prompt,
            params=render_params,
        )
        mock_result = f"rendered_{order.id}_{render_params.get('resolution','1080P')}_{render_params.get('aspect_ratio','unknown')}.mp4"
        order.render_result = mock_result
        order.status = OrderStatus.QA_DONE

        return {
            "task_id": render_task.task_id,
            "result": mock_result,
            "params": render_params,
            "engine": "mock",
        }

    def final_qa(self, order: AdOrder) -> dict:
        """最终画面质检 + 真实施放"""
        hs = next((h for h in self.hotspots if h.id == order.hot_spot_id), None)
        hotspot_title = hs.title if hs else "热点资讯"
        _, report = self.qa_engine.full_check(
            order.copywriting[0] if order.copywriting else "",
            hotspot_title,
            order.render_result or "",
        )
        order.qa_report = report

        if report["总结果"] == "通过":
            order.status = OrderStatus.PUBLISHED

            # === V2.1：真实多平台发布 ===
            if self.publisher and self.publisher.is_platform_configured(order.platform):
                pub_result = self.publisher.publish(
                    platform=order.platform,
                    title=order.product_name,
                    content=order.copywriting[0] if order.copywriting else "",
                )
                order.publish_links = {order.platform: pub_result.post_url}
            else:
                # Mock 发布链接
                order.publish_links = {
                    order.platform: f"https://{order.platform}.com/post/{order.id}",
                }

        return report

    def publish_to_all_platforms(self, order: AdOrder) -> dict[str, PublishResult]:
        """一键发布到所有已配置平台"""
        if not self.publisher:
            return {}
        return self.publisher.publish_to_all(
            title=order.product_name,
            content=order.copywriting[0] if order.copywriting else "无内容",
        )

    def trigger_fan_interaction(self, order: AdOrder) -> dict:
        """
        发布完成后自动触发粉丝互动任务队列

        由 final_qa → PUBLISHED 状态后调用，编排评论抓取、智能回复、
        私信应答、互动数据回流全流程。

        账号阶段适配：
        - 冷启动（TRIAL）：降低回复频次，话术轻量化
        - 成熟（MATURE）：完整互动模板，多轮引导关注
        """
        if not FanInteractionManager:
            return {
                "success": False,
                "reason": "FanInteractionManager 未加载（platform_api.py 缺失）",
            }

        # 确定账号阶段
        account_phase = "MATURE"
        credit_score = 100
        if self.accounts:
            acc = list(self.accounts.values())[0]
            phase_map = {
                "冷启动养号": "TRIAL",
                "小规模试单": "TRIAL",
                "快速放量期": "MATURE",
                "全量成熟期": "MATURE",
            }
            account_phase = phase_map.get(acc.phase.value, "MATURE")
            # 根据粉丝数/互动率推算信用分（满分100）
            credit_score = min(100, int(max(30, acc.followers / 100 + acc.avg_likes * 0.5)))

        # 创建粉丝互动管理器，注入 final_qa 质检引擎
        def qa_wrapper(text: str) -> dict:
            """将 ContentQAEngine.check_copywriting 适配为 AutoReplyEngine 所需的签名。
            评论回复仅需文字合规（违禁词+广告占比），豁免场景融合。"""
            text_with_label = f"{text}（推广）" if "推广" not in text and "广告" not in text else text
            text_result = self.qa_engine.check_copywriting(text_with_label)
            return {
                "approved": text_result["passed"],
                "text_issues": text_result.get("issues", []),
                "fusion_issues": [],
            }

        manager = FanInteractionManager(
            account_phase=account_phase,
            credit_score=credit_score,
            account_id=getattr(order, "advertiser_id", ""),
            final_qa=qa_wrapper,
        )

        # 使用订单的 render_result 路径派生 post_id
        post_id = getattr(order, "render_result", "") or f"post_{order.id}"

        result = manager.run(post_id)
        result["order_id"] = order.id
        result["success"] = True

        # 写入执行日志
        self.execution_log.append({
            "step": "粉丝互动触发",
            "order": order.id,
            "timestamp": datetime.now().isoformat(),
            "stats": result.get("stats", {}),
            "archive_path": result.get("archive_path", ""),
        })

        return result

    def queue_summary(self) -> dict:
        """队列状态汇总"""
        return {
            "高优队列 (30%算力)": len(self.high_priority_queue),
            "常规队列 (50%算力)": len(self.normal_queue),
            "低优队列 (20%算力)": len(self.low_priority_queue),
            "GPU负载": f"{self.tag_manager.get_gpu_load()}%",
        }

    def run_full_pipeline(self) -> dict:
        """执行完整自动化流水线"""
        log = {
            "pipeline": "V2.0 全流程",
            "timestamp": datetime.now().isoformat(),
            "steps": [],
        }
        self.execution_log.append(log)

        # Step 1: 刷新订单池（已完成预审的订单）
        pending = [o for o in self.settlement.orders if o.status == OrderStatus.APPROVED]
        log["steps"].append({"step": "订单刷新", "count": len(pending)})

        # Step 2-5: 匹配、打标签、分流、报价
        for order in pending:
            tag = self.match_and_tag(order)
            if tag is None:
                order.status = OrderStatus.PENDING  # 无匹配热点，顺延
                log["steps"].append({
                    "step": "匹配失败",
                    "order": order.id,
                    "reason": "无合格热点(≥70分)",
                })
                continue

            self.dispatch_to_queue(order, tag)
            copies = self.generate_copywriting(order, tag)
            render_result = self.send_to_render(order, tag)
            qa = self.final_qa(order)

            log["steps"].append({
                "step": "处理完成",
                "order": order.id,
                "match_score": order.match_score,
                "price": f"¥{order.final_price}",
                "queue": self.tag_manager.dispatch_by_tag(tag, order),
                "copies": len(copies),
                "render": render_result["result"],
                "qa": qa["总结果"],
            })

            # Step 6: 发布后自动触发粉丝互动（V2.1 新增）
            if order.status == OrderStatus.PUBLISHED:
                interaction_result = self.trigger_fan_interaction(order)
                log["steps"].append({
                    "step": "粉丝互动",
                    "order": order.id,
                    "auto_replies": interaction_result.get("stats", {}).get("auto_replies", 0),
                    "dm_replies": interaction_result.get("stats", {}).get("dm_replies", 0),
                    "negative_skipped": interaction_result.get("stats", {}).get("negative_skipped", 0),
                    "archive_path": interaction_result.get("archive_path", ""),
                })

        return log


# ==================== Demo 数据工厂 ====================

def build_demo_data() -> MarvisScheduler:
    """构建完整 Demo 数据集"""
    scheduler = MarvisScheduler()

    # 注册广告主
    advertisers = [
        Advertiser(id="A001", name="兰蔻旗舰店", level=BusinessLevel.S, credit_score=120, monthly_orders=8),
        Advertiser(id="A002", name="小米科技", level=BusinessLevel.A, credit_score=105, monthly_orders=3),
        Advertiser(id="A003", name="元气森林", level=BusinessLevel.B, credit_score=100, monthly_orders=1),
        Advertiser(id="A004", name="XX虚拟币平台", level=BusinessLevel.C, credit_score=45, has_violation=True),
    ]
    for a in advertisers:
        scheduler.register_advertiser(a)

    # 加载热点
    hotspots = [
        HotSpot(id="H001", title="新款iPhone发布：AI功能成最大亮点，掀起换机热潮", score=95,
                category="科技", source_url="https://example.com/h001",
                is_negative=False),
        HotSpot(id="H002", title="全国多地发生特大暴雨洪涝灾害，千万人受灾", score=98,
                category="社会", source_url="https://example.com/h002",
                is_negative=True),  # 负面热点，禁止绑定广告
        HotSpot(id="H003", title="特斯拉新款自动驾驶实测：城区路段零接管", score=88,
                category="汽车", source_url="https://example.com/h003",
                is_negative=False),
        HotSpot(id="H004", title="618大促：美妆品类销量同比增长200%", score=85,
                category="美妆", source_url="https://example.com/h004",
                is_negative=False),
    ]
    scheduler.load_hotspots(hotspots)

    # 创建广告订单
    orders = [
        AdOrder(
            id="ORD001", advertiser_id="A001",
            product_name="兰蔻持妆粉底液",
            product_category="美妆",
            media_type=MediaTag.SHORT_VIDEO.value,
            platform=Platform.DOUYIN.value,
            base_price=800.0,
        ),
        AdOrder(
            id="ORD002", advertiser_id="A001",
            product_name="兰蔻菁纯面霜",
            product_category="美妆",
            media_type=MediaTag.VERTICAL_IMAGE.value,
            platform=Platform.XIAOHONGSHU.value,
            base_price=600.0,
        ),
        AdOrder(
            id="ORD003", advertiser_id="A002",
            product_name="小米14 Ultra",
            product_category="科技",
            media_type=MediaTag.SHORT_VIDEO.value,
            platform=Platform.DOUYIN.value,
            base_price=1000.0,
        ),
        AdOrder(
            id="ORD004", advertiser_id="A003",
            product_name="元气森林樱花限定",
            product_category="快消",
            media_type=MediaTag.HORIZONTAL_IMAGE.value,
            platform=Platform.TOUTIAO.value,
            base_price=400.0,
        ),
        AdOrder(
            id="ORD005", advertiser_id="A004",
            product_name="XX币一夜暴涨100倍",
            product_category="金融",
            media_type=MediaTag.SHORT_VIDEO.value,
            platform=Platform.DOUYIN.value,
            base_price=500.0,
        ),
    ]

    for o in orders:
        result = scheduler.submit_order(o)

    return scheduler
