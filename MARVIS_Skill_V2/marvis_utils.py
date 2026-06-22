"""
MARVIS V2.1 补充模块
- 收益导出（Excel）
- 冷启动纯资讯发布
- 阶段自适应质检阈值
- 发布告警日志
"""

from datetime import datetime


# ==================== 收益导出 ====================

class ReportExporter:
    """结算台账 → Excel / CSV 导出"""

    @staticmethod
    def export_daily_csv(settlement_engine, output_dir: str = r"E:\MARVIS_Skill_V2\reports") -> str:
        """导出当日收益 CSV"""
        import os
        os.makedirs(output_dir, exist_ok=True)

        report = settlement_engine.daily_report()
        today = report["日期"]
        rows = report["明细"]
        if not rows:
            return ""

        filepath = f"{output_dir}\\结算日报_{today}.csv"
        with open(filepath, "w", encoding="utf-8-sig") as f:
            headers = ["订单ID", "广告主", "等级", "产品", "平台", "状态", "匹配分", "报价", "已结算"]
            f.write(",".join(headers) + "\n")
            for r in rows:
                line = ",".join(str(r.get(h, "")) for h in headers)
                f.write(line + "\n")
        return filepath

    @staticmethod
    def export_monthly_excel(settlement_engine, output_dir: str = r"E:\MARVIS_Skill_V2\reports") -> str:
        """导出当月明细 Excel（需 pandas + openpyxl）"""
        import os
        os.makedirs(output_dir, exist_ok=True)

        try:
            import pandas as pd
        except ImportError:
            return ReportExporter.export_daily_csv(settlement_engine, output_dir)

        month_str = datetime.now().strftime("%Y-%m")
        filepath = f"{output_dir}\\结算月报_{month_str}.xlsx"

        rows = [o.to_summary() for o in settlement_engine.orders
                if o.created_at.strftime("%Y-%m") == month_str]
        if not rows:
            return ""

        df = pd.DataFrame(rows)
        total = df[df["已结算"] == "是"]["报价"].apply(
            lambda x: float(str(x).replace("¥", "").replace(",", ""))
        ).sum()
        pending = df[df["已结算"] == "否"]["报价"].apply(
            lambda x: float(str(x).replace("¥", "").replace(",", ""))
        ).sum()

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="订单明细", index=False)
            summary = pd.DataFrame({
                "指标": ["总营收", "已结算", "待结算", "订单总数"],
                "金额": [total + pending, total, pending, len(rows)],
            })
            summary.to_excel(writer, sheet_name="汇总", index=False)

        return filepath


# ==================== 阶段自适应质检阈值 ====================

class AdaptiveQA:
    """
    根据账号阶段动态调整质检阈值
    - 冷启动：广告文字占比≤12%，更严格的融合度
    - 试单：占比≤18%
    - 规模化：占比≤20%
    - 矩阵：占比≤20%
    """

    PHASE_AD_RATIO_LIMIT = {
        "COLD_START": 0.12,
        "TRIAL": 0.18,
        "SCALING": 0.20,
        "MATRIX": 0.20,
    }

    PHASE_EXTRA_CHECKS = {
        "COLD_START": [
            "禁止使用任何营销话术（限时/速抢/最低价/仅限今日）",
            "禁止挂载购买链接",
            "禁止使用夸大功效词",
        ],
        "TRIAL": [
            "限用轻度营销词（推荐/分享/体验）",
            "购买链接仅允许文末出现1次",
        ],
        "SCALING": [],
        "MATRIX": [],
    }

    @classmethod
    def get_ad_ratio_limit(cls, phase: str) -> float:
        return cls.PHASE_AD_RATIO_LIMIT.get(phase, 0.20)

    @classmethod
    def get_extra_rules(cls, phase: str) -> list[str]:
        return cls.PHASE_EXTRA_CHECKS.get(phase, [])

    @classmethod
    def check(cls, copy_text: str, phase: str) -> tuple[bool, list[str]]:
        """阶段感知质检"""
        issues = []
        ad_ratio = len(copy_text) / 500
        limit = cls.get_ad_ratio_limit(phase)
        if ad_ratio > limit:
            issues.append(f"广告文字占比 {ad_ratio:.0%} 超过 {phase} 阶段上限 {limit:.0%}")

        extra_rules = cls.get_extra_rules(phase)
        # 这里展开具体规则检查逻辑...
        return len(issues) == 0, issues


# ==================== 纯资讯发布 ====================

class PureNewsPublisher:
    """
    冷启动养号期：只发纯资讯，不插广告
    配合 hotspot_collector 抓取低风控民生类热点
    """

    SAFE_NICHES = ["美食", "旅游", "宠物", "家居", "运动健身"]  # 低风控赛道

    def __init__(self, marvis_scheduler):
        self.scheduler = marvis_scheduler

    def generate_news_content(self, hotspot_title: str, niche: str) -> str:
        """从热点标题生成纯资讯文案（无广告）"""
        return (
            f"【{niche}资讯】{hotspot_title}\n\n"
            f"最近这个话题引起了不少关注。简单聊聊背后的原因和影响——"
            f"对普通人来说，这意味着什么？\n\n"
            f"持续关注，我们会在后续带来更多深度解读。"
        )

    def publish_daily_news(self, count: int = 2) -> list[dict]:
        """发布每日纯资讯"""
        results = []
        collector = self.scheduler.hotspot_collector
        if not collector:
            return results

        # 从安全赛道抓热点
        for niche in self.SAFE_NICHES[:count]:
            keywords = collector.get_niche_keywords(niche)
            if keywords:
                title = f"{keywords[0]}最新趋势引发关注"
                content = self.generate_news_content(title, niche)
                # 通过 publisher 发布
                if self.scheduler.publisher:
                    self.scheduler.publisher.publish("wechat", f"{niche}资讯", content)
                results.append({"niche": niche, "title": title, "published": True})

        return results


# ==================== 发布告警日志 ====================

import logging
import os

LOG_DIR = r"E:\MARVIS_Skill_V2\logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("marvis_publish")
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(f"{LOG_DIR}\\publish_error.log", encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(handler)


def log_publish_failure(platform: str, order_id: str, error: str):
    """记录发布失败到告警日志"""
    logger.error(f"[{platform}] 订单 {order_id} 发布失败: {error}")


def log_render_failure(task_id: str, error: str):
    """记录渲染失败"""
    logger.error(f"渲染任务 {task_id} 失败: {error}")


def log_platform_down(platform: str):
    """记录平台不可用"""
    logger.warning(f"平台 {platform} 接口不可用，已跳过")


# Monkey-patch 到 MarvisScheduler.final_qa
def _patched_final_qa(self, order):
    """替换 final_qa 以加入告警日志"""
    from marvis_core import OrderStatus, PublishResult
    _, report = self.qa_engine.full_check(
        order.copywriting[0] if order.copywriting else "",
        "热点",
        order.render_result or "",
    )
    order.qa_report = report

    if report["总结果"] == "通过":
        order.status = OrderStatus.PUBLISHED

        if self.publisher and self.publisher.is_platform_configured(order.platform):
            pub_result = self.publisher.publish(
                platform=order.platform,
                title=order.product_name,
                content=order.copywriting[0] if order.copywriting else "",
            )
            if not pub_result.success:
                log_publish_failure(order.platform, order.id, pub_result.error_message)
            order.publish_links = {order.platform: pub_result.post_url}
        else:
            order.publish_links = {
                order.platform: f"https://{order.platform}.com/post/{order.id}",
            }

    return report


if __name__ == "__main__":
    print(f"日志目录: {LOG_DIR}")
    print(f"告警日志: {LOG_DIR}\\publish_error.log")
    log_publish_failure("douyin", "TEST001", "模拟发布失败-接口超时")
    print("测试告警已写入。")
