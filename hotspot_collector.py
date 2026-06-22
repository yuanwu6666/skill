"""
MARVIS V2.0 - 真实热点采集引擎
支持多源订阅：RSS源 / Web搜索 / API聚合
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class RawArticle:
    """原始文章结构"""
    title: str
    url: str
    source: str          # 36kr / ithome / zhihu / weibo / baidu / rss
    summary: str = ""
    published_at: str = ""
    raw_category: str = ""


# ==================== 全赛道热点关键词库 ====================

NICHE_KEYWORDS = {
    "美妆": {
        "cn": ["美妆", "护肤", "彩妆", "口红", "粉底", "精华", "面膜", "防晒",
               "眼影", "腮红", "化妆", "素颜", "淡妆", "浓妆", "卸妆", "隔离",
               "BB霜", "CC霜", "气垫", "散粉", "高光", "修容", "遮瑕", "眉笔"],
        "en": ["makeup", "skincare", "cosmetics", "lipstick", "foundation", "serum"],
        "rss_feeds": [
            "https://rsshub.app/weibo/search/hot/美妆",
            "https://rsshub.app/xiaohongshu/board/美妆",
        ],
    },
    "科技": {
        "cn": ["科技", "AI", "人工智能", "芯片", "5G", "6G", "机器人", "量子",
               "半导体", "自动驾驶", "大模型", "GPT", "手机发布", "新机",
               "苹果", "华为", "小米", "OPPO", "vivo", "三星", "芯片制裁",
               "开源", "GPU", "算力", "大语言模型", "AIGC", "智能穿戴"],
        "en": ["tech", "AI", "chip", "semiconductor", "autonomous", "LLM"],
        "rss_feeds": [
            "https://rsshub.app/36kr/newsflashes",
            "https://rsshub.app/ithome/",
            "https://rsshub.app/weibo/search/hot/科技",
        ],
    },
    "汽车": {
        "cn": ["汽车", "新能源", "电动车", "特斯拉", "比亚迪", "蔚来", "理想",
               "小鹏", "混动", "纯电", "充电桩", "换电站", "自动驾驶",
               "智能座舱", "车载", "油耗", "续航", "百公里", "SUV", "轿车"],
        "en": ["EV", "electric vehicle", "Tesla", "BYD", "autonomous driving"],
        "rss_feeds": [
            "https://rsshub.app/autohome/latest",
            "https://rsshub.app/weibo/search/hot/新能源",
        ],
    },
    "家居": {
        "cn": ["家居", "装修", "软装", "硬装", "全屋定制", "收纳", "断舍离",
               "极简风", "北欧风", "日式", "小户型", "租房改造", "家电",
               "扫地机", "洗碗机", "烘干机", "智能家居", "灯光设计"],
        "en": ["home", "interior", "decoration", "furniture", "smart home"],
        "rss_feeds": [
            "https://rsshub.app/xiaohongshu/board/家居",
        ],
    },
    "美食": {
        "cn": ["美食", "探店", "打卡", "米其林", "黑珍珠", "街边摊", "夜市",
               "烘焙", "料理", "食谱", "减脂餐", "轻食", "外卖", "预制菜",
               "咖啡", "奶茶", "火锅", "烧烤", "日料", "西餐"],
        "en": ["food", "cooking", "restaurant", "recipe", "gourmet"],
        "rss_feeds": [
            "https://rsshub.app/weibo/search/hot/美食",
        ],
    },
    "服饰": {
        "cn": ["穿搭", "OOTD", "时装周", "联名", "限量", "球鞋", "潮牌",
               "优衣库", "ZARA", "UR", "古着", "通勤穿搭", "约会穿搭",
               "显瘦", "显高", "配色", "叠穿", "配饰", "包包", "手表"],
        "en": ["fashion", "outfit", "sneaker", "streetwear", "luxury"],
        "rss_feeds": [
            "https://rsshub.app/xiaohongshu/board/穿搭",
        ],
    },
    "游戏": {
        "cn": ["游戏", "手游", "端游", "主机", "Switch", "PS5", "Xbox",
               "原神", "王者荣耀", "和平精英", "崩坏", "米哈游", "腾讯游戏",
               "网易游戏", "Steam", "Epic", "3A", "独立游戏", "电竞",
               "LOL", "LPL", "KPL", "TGA", "E3", "科隆游戏展"],
        "en": ["game", "gaming", "esports", "Steam", "Nintendo", "PlayStation"],
        "rss_feeds": [
            "https://rsshub.app/gamersky/news",
        ],
    },
    "运动健身": {
        "cn": ["健身", "跑步", "马拉松", "瑜伽", "普拉提", "撸铁", "增肌",
               "减脂", "HIIT", "CrossFit", "户外", "露营", "骑行", "滑雪",
               "冲浪", "攀岩", "飞盘", "腰旗橄榄球", "匹克球"],
        "en": ["fitness", "running", "yoga", "gym", "outdoor", "camping"],
        "rss_feeds": [
            "https://rsshub.app/weibo/search/hot/健身",
        ],
    },
    "金融理财": {
        "cn": ["理财", "基金", "股票", "A股", "港股", "美股", "定投",
               "ETF", "可转债", "打新", "存款利率", "降息", "加息",
               "房贷", "LPR", "公积金", "个税", "保险", "养老金"],
        "en": ["finance", "stock", "fund", "ETF", "insurance", "pension"],
        "rss_feeds": [],
        "high_risk": True,   # 金融赛道标记高风险
    },
    "母婴": {
        "cn": ["母婴", "育儿", "怀孕", "待产", "月子", "奶粉", "纸尿裤",
               "婴儿车", "安全座椅", "早教", "辅食", "产假", "哺乳",
               "产后修复", "儿童疫苗", "学区房", "入园", "幼小衔接"],
        "en": ["baby", "parenting", "pregnancy", "maternity", "nursery"],
        "rss_feeds": [],
    },
    "宠物": {
        "cn": ["宠物", "猫", "狗", "猫咪", "狗狗", "英短", "布偶", "金毛",
               "柴犬", "柯基", "猫粮", "狗粮", "驱虫", "绝育", "疫苗",
               "猫砂", "遛狗", "宠物友好", "宠物托运", "云吸猫"],
        "en": ["pet", "cat", "dog", "kitten", "puppy", "veterinary"],
        "rss_feeds": [],
    },
    "教育": {
        "cn": ["教育", "高考", "考研", "考公", "考编", "留学", "雅思",
               "托福", "GRE", "MBA", "博士", "导师", "论文", "学历",
               "专升本", "成考", "自考", "网课", "知识付费", "编程入门"],
        "en": ["education", "exam", "study abroad", "IELTS", "TOEFL"],
        "rss_feeds": [],
    },
    "旅游": {
        "cn": ["旅游", "旅行", "自驾", "徒步", "穷游", "出境游", "免签",
               "签证", "民宿", "酒店", "机票", "高铁", "景点", "打卡",
               "网红地", "小众", "海岛", "雪山", "西北大环线"],
        "en": ["travel", "trip", "vacation", "hotel", "flight", "tour"],
        "rss_feeds": [],
    },
    "泛娱乐": {
        "cn": ["综艺", "电视剧", "电影", "明星", "偶像", "选秀", "塌房",
               "CP", "番剧", "动漫", "B站", "抖音", "小红书", "热搜",
               "爆款", "网红", "脱口秀", "喜剧", "音乐节", "演唱会"],
        "en": ["entertainment", "celebrity", "movie", "drama", "anime", "concert"],
        "rss_feeds": [
            "https://rsshub.app/weibo/search/hot",
        ],
    },
    "健康养生": {
        "cn": ["养生", "中医", "泡脚", "艾灸", "刮痧", "拔罐", "推拿",
               "体检", "三高", "糖尿病", "失眠", "脱发", "护肝", "养胃",
               "补钙", "维生素", "鱼油", "益生菌", "褪黑素", "颈椎"],
        "en": ["health", "wellness", "TCM", "supplement", "vitamin"],
        "rss_feeds": [],
        "high_risk": True,   # 健康赛道标记高风险（易触广告法）
    },
}


class HotSpotCollector:
    """多源热点采集器（RSS + Web Search + API 聚合）"""

    def __init__(self, niches: list[str] = None):
        """
        niches: 关注的赛道列表，如 ['美妆', '科技']，默认全量
        """
        self.niches = niches or list(NICHE_KEYWORDS.keys())
        self.collected: list[RawArticle] = []

    def collect_from_web_search(self, niche: str, limit: int = 5) -> list[RawArticle]:
        """通过 web_search 采集热点（需在主 Agent 层调用）"""
        # 返回搜索指令，由主 Agent 的 web_search 工具执行
        keywords = NICHE_KEYWORDS.get(niche, {}).get("cn", [niche])
        queries = []
        for kw in keywords[:3]:  # 取前3个关键词
            queries.append(f"{kw} 最新 热点")
        return queries  # 返回查询列表，供上层调度

    def filter_by_niche(self, article: RawArticle) -> Optional[str]:
        """自动识别文章所属赛道"""
        text = article.title + article.summary
        best_niche = None
        best_score = 0

        for niche, data in NICHE_KEYWORDS.items():
            score = 0
            for kw in data.get("cn", []):
                if kw in text:
                    score += 1
            if score > best_score:
                best_score = score
                best_niche = niche

        return best_niche if best_score >= 2 else None

    def is_high_risk_niche(self, niche: str) -> bool:
        """检查是否为高风险赛道"""
        return NICHE_KEYWORDS.get(niche, {}).get("high_risk", False)

    def get_rss_feeds(self, niche: str) -> list[str]:
        """获取某赛道的 RSS 订阅源"""
        return NICHE_KEYWORDS.get(niche, {}).get("rss_feeds", [])

    def get_all_niches(self) -> list[str]:
        """获取所有赛道名称"""
        return list(NICHE_KEYWORDS.keys())

    def get_niche_keywords(self, niche: str) -> list[str]:
        """获取某赛道的中文关键词"""
        return NICHE_KEYWORDS.get(niche, {}).get("cn", [])

    def niche_summary(self) -> dict:
        """赛道配置汇总"""
        result = {}
        for niche in self.niches:
            data = NICHE_KEYWORDS.get(niche, {})
            result[niche] = {
                "关键词数": len(data.get("cn", [])),
                "RSS源数": len(data.get("rss_feeds", [])),
                "高风险": data.get("high_risk", False),
            }
        return result


# ==================== 通用 RSS / API 采集适配器 ====================

class RSSFeedAdapter:
    """通用 RSS 采集适配器，可对接各类 RSS 源"""

    @staticmethod
    def parse_rsshub_url(topic: str, source: str = "weibo") -> str:
        """生成 RSSHub 路由 URL"""
        routes = {
            "weibo_hot": f"https://rsshub.app/weibo/search/hot/{topic}",
            "36kr": "https://rsshub.app/36kr/newsflashes",
            "ithome": "https://rsshub.app/ithome/",
            "zhihu_hot": "https://rsshub.app/zhihu/hotlist",
            "baidu_hot": "https://rsshub.app/baidu/top",
            "xiaohongshu": f"https://rsshub.app/xiaohongshu/board/{topic}",
        }
        return routes.get(source, "")

    @staticmethod
    def get_fallback_sources() -> list[dict]:
        """兜底通用源（不依赖赛道）"""
        return [
            {"name": "微博热搜", "url": "https://rsshub.app/weibo/search/hot"},
            {"name": "百度热榜", "url": "https://rsshub.app/baidu/top"},
            {"name": "知乎热榜", "url": "https://rsshub.app/zhihu/hotlist"},
            {"name": "36氪快讯", "url": "https://rsshub.app/36kr/newsflashes"},
        ]


if __name__ == "__main__":
    collector = HotSpotCollector()
    print("全赛道配置:")
    for niche, info in collector.niche_summary().items():
        risk = "⚠️高风险" if info["高风险"] else "✓安全"
        print(f"  {niche:8s} | 关键词:{info['关键词数']:3d} | RSS:{info['RSS源数']:2d} | {risk}")
    print(f"\n共 {len(NICHE_KEYWORDS)} 个赛道, {sum(len(v.get('cn',[])) for v in NICHE_KEYWORDS.values())} 个关键词")
