"""
MARVIS V2.0 - 账号变现阶段引擎
零粉冷启动 → 试单变现 → 稳定规模化 → 多账号矩阵
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AccountPhase(str, Enum):
    """账号变现阶段"""
    COLD_START = "冷启动养号"       # 0粉，纯资讯，不接广告
    TRIAL = "小规模试单"            # 7天+，日2单，折价0.4，仅B级
    SCALING = "稳定规模化"          # 500粉+，全功能，日5-8单
    MATRIX = "多账号矩阵"           # 多账号接入

    def next_phase(self):
        order = [self.COLD_START, self.TRIAL, self.SCALING, self.MATRIX]
        idx = order.index(self)
        return order[idx + 1] if idx + 1 < len(order) else self


@dataclass
class Account:
    """MARVIS 管理的单账号"""
    account_id: str
    platform: str           # 抖音/小红书/头条/视频号
    niche: str              # 垂直赛道：美妆/科技/家居/美食/汽车
    followers: int = 0
    total_posts: int = 0
    phase: AccountPhase = AccountPhase.COLD_START

    # 冷启动指标
    created_at: datetime = field(default_factory=datetime.now)
    days_active: int = 0
    avg_views: int = 0
    avg_likes: int = 0

    # 变现数据
    total_revenue: float = 0.0
    total_orders: int = 0
    settled_orders: int = 0

    def update_metrics(self, views: int, likes: int):
        self.avg_views = views
        self.avg_likes = likes
        self.days_active = (datetime.now() - self.created_at).days

    def check_phase_upgrade(self) -> bool:
        """检测是否满足阶段升级条件"""
        self.days_active = (datetime.now() - self.created_at).days

        if self.phase == AccountPhase.COLD_START:
            # 冷启动→试单：7天 + 基础播放稳定（日均播放>200）
            if self.days_active >= 7 and self.avg_views >= 200:
                self.phase = AccountPhase.TRIAL
                return True

        elif self.phase == AccountPhase.TRIAL:
            # 试单→规模化：粉丝>500
            if self.followers >= 500:
                self.phase = AccountPhase.SCALING
                return True

        elif self.phase == AccountPhase.SCALING:
            # 规模化→矩阵：多账号接入（手动触发）
            pass

        return False

    @property
    def daily_order_limit(self) -> int:
        """单日接单上限"""
        return {
            AccountPhase.COLD_START: 0,
            AccountPhase.TRIAL: 2,
            AccountPhase.SCALING: 5,
            AccountPhase.MATRIX: 8,
        }.get(self.phase, 0)

    @property
    def cold_start_discount(self) -> float:
        """冷启动折价系数"""
        return {
            AccountPhase.COLD_START: 0.0,   # 不接广告
            AccountPhase.TRIAL: 0.4,         # 折价60%
            AccountPhase.SCALING: 1.0,       # 标准价
            AccountPhase.MATRIX: 1.0,
        }.get(self.phase, 1.0)

    @property
    def post_limit_per_day(self) -> int:
        """每日发布上限"""
        return {
            AccountPhase.COLD_START: 3,
            AccountPhase.TRIAL: 4,
            AccountPhase.SCALING: 6,
            AccountPhase.MATRIX: 8,
        }.get(self.phase, 3)

    @property
    def allowed_business_levels(self) -> list:
        """允许接单的广告主等级"""
        return {
            AccountPhase.COLD_START: [],
            AccountPhase.TRIAL: ["B散单"],
            AccountPhase.SCALING: ["S头部", "A优质", "B散单"],
            AccountPhase.MATRIX: ["S头部", "A优质", "B散单"],
        }.get(self.phase, [])

    @property
    def ad_text_ratio_limit(self) -> float:
        """广告文案占比上限"""
        return {
            AccountPhase.COLD_START: 0.0,
            AccountPhase.TRIAL: 0.12,    # 冷启动仅文末轻推荐
            AccountPhase.SCALING: 0.20,
            AccountPhase.MATRIX: 0.20,
        }.get(self.phase, 0.20)

    @property
    def content_ratio(self) -> tuple:
        """资讯:广告发布配比"""
        return {
            AccountPhase.COLD_START: (3, 0),
            AccountPhase.TRIAL: (2, 1),
            AccountPhase.SCALING: (1, 1),
            AccountPhase.MATRIX: (1, 1),
        }.get(self.phase, (1, 0))

    def summary(self) -> dict:
        return {
            "账号ID": self.account_id,
            "平台": self.platform,
            "赛道": self.niche,
            "粉丝": f"{self.followers:,}",
            "阶段": self.phase.value,
            "活跃天数": self.days_active,
            "日均播放": f"{self.avg_views:,}",
            "单日接单上限": self.daily_order_limit,
            "折价系数": f"{self.cold_start_discount:.1f}",
            "日发布上限": self.post_limit_per_day,
            "累计营收": f"¥{self.total_revenue:,.2f}",
        }
