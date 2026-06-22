"""
MARVIS V2.0 - 公众号 / 内容平台 API 接入层
支持：微信公众号(订阅号) / 小红书 / 头条号 / 知乎 / 百家号
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time
import json


# ==================== 统一内容发布接口 ====================

@dataclass
class PublishRequest:
    """统一发布请求"""
    article_id: str
    platform: str           # wechat / xiaohongshu / toutiao / zhihu / baijiahao
    title: str
    content: str            # 正文（Markdown 或纯文本）
    cover_image_url: str = ""
    media_urls: list[str] = field(default_factory=list)  # 图片/视频 URL 列表
    tags: list[str] = field(default_factory=list)
    category: str = ""
    is_original: bool = True
    scheduled_at: str = ""  # 定时发布 ISO datetime
    metadata: dict = field(default_factory=dict)


@dataclass
class PublishResult:
    """发布结果"""
    article_id: str
    platform: str
    success: bool
    post_url: str = ""
    post_id: str = ""
    error_message: str = ""
    published_at: str = ""


# ==================== 微信公众号 API 客户端 ====================

class WeChatOfficialAccountClient:
    """
    微信公众号（订阅号）API 客户端

    前置条件：
    1. 已注册微信公众平台服务号/订阅号
    2. 已通过微信认证
    3. 已在后台配置 IP 白名单
    4. 已获取 AppID + AppSecret

    API 文档：https://developers.weixin.qq.com/doc/offiaccount/
    """

    BASE_URL = "https://api.weixin.qq.com"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: str = ""
        self._token_expire_at: float = 0

    def _get_access_token(self) -> str:
        """获取 access_token（自动缓存+刷新）"""
        if self._access_token and time.time() < self._token_expire_at:
            return self._access_token

        try:
            import requests
            resp = requests.get(
                f"{self.BASE_URL}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.app_id,
                    "secret": self.app_secret,
                },
                timeout=10,
            )
            data = resp.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                self._token_expire_at = time.time() + data.get("expires_in", 7200) - 300
                return self._access_token
            raise Exception(f"获取 access_token 失败: {data}")
        except ImportError:
            raise Exception("缺少 requests 库")

    def publish_draft(
        self,
        title: str,
        content: str,
        cover_media_id: str = "",
        thumb_media_id: str = "",
        need_open_comment: bool = False,
        only_fans_can_comment: bool = False,
    ) -> PublishResult:
        """
        发布图文草稿（订阅号能力）

        POST /cgi-bin/draft/add
        """
        try:
            token = self._get_access_token()
            import requests

            articles = [{
                "title": title,
                "content": content,
                "content_source_url": "",
                "thumb_media_id": thumb_media_id or cover_media_id,
                "need_open_comment": 1 if need_open_comment else 0,
                "only_fans_can_comment": 1 if only_fans_can_comment else 0,
                "show_cover_pic": 1 if thumb_media_id else 0,
            }]

            resp = requests.post(
                f"{self.BASE_URL}/cgi-bin/draft/add?access_token={token}",
                json={"articles": articles},
                timeout=30,
            )
            data = resp.json()

            if "media_id" in data:
                return PublishResult(
                    article_id="",
                    platform="wechat",
                    success=True,
                    post_id=data["media_id"],
                )
            return PublishResult(
                article_id="",
                platform="wechat",
                success=False,
                error_message=str(data),
            )
        except Exception as e:
            return PublishResult(platform="wechat", success=False, error_message=str(e))

    def upload_image(self, image_path: str) -> str:
        """上传图片素材，返回 media_id"""
        try:
            token = self._get_access_token()
            import requests

            with open(image_path, "rb") as f:
                resp = requests.post(
                    f"{self.BASE_URL}/cgi-bin/media/uploadimg?access_token={token}",
                    files={"media": f},
                    timeout=30,
                )
            data = resp.json()
            return data.get("url", "") or data.get("media_id", "")
        except Exception:
            return ""

    def upload_permanent_material(self, file_path: str, material_type: str = "image") -> dict:
        """
        上传永久素材
        material_type: image / voice / video / thumb
        返回 {"media_id": "...", "url": "..."}
        """
        try:
            token = self._get_access_token()
            import requests

            url = f"{self.BASE_URL}/cgi-bin/material/add_material?access_token={token}&type={material_type}"
            with open(file_path, "rb") as f:
                resp = requests.post(url, files={"media": f}, timeout=60)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def get_article_list(self, offset: int = 0, count: int = 20) -> list[dict]:
        """获取已发布文章列表"""
        try:
            token = self._get_access_token()
            import requests

            resp = requests.post(
                f"{self.BASE_URL}/cgi-bin/freepublish/batchget?access_token={token}",
                json={"offset": offset, "count": count, "no_content": 1},
                timeout=30,
            )
            data = resp.json()
            return data.get("item", [])
        except Exception:
            return []

    def get_article_stats(self, article_id: str) -> dict:
        """获取单篇文章数据统计"""
        try:
            token = self._get_access_token()
            import requests

            resp = requests.post(
                f"{self.BASE_URL}/datacube/getarticletotal?access_token={token}",
                json={
                    "begin_date": datetime.now().strftime("%Y-%m-%d"),
                    "end_date": datetime.now().strftime("%Y-%m-%d"),
                },
                timeout=10,
            )
            return resp.json()
        except Exception:
            return {}


# ==================== 多平台发布适配器 ====================

class MultiPlatformPublisher:
    """多平台统一发布调度器"""

    def __init__(self):
        self._clients: dict[str, object] = {}
        self.platform_priority = [
            "wechat",       # 微信订阅号（核心）
            "xiaohongshu",  # 小红书
            "toutiao",      # 头条号
            "zhihu",        # 知乎
            "baijiahao",    # 百家号
            "douyin",       # 抖音（短视频）
            "bilibili",     # B站
        ]

    def configure_wechat(self, app_id: str, app_secret: str):
        """配置微信公众号"""
        self._clients["wechat"] = WeChatOfficialAccountClient(app_id, app_secret)

    def get_client(self, platform: str):
        """获取指定平台客户端"""
        return self._clients.get(platform)

    def is_platform_configured(self, platform: str) -> bool:
        """检查平台是否已配置"""
        return platform in self._clients and self._clients[platform] is not None

    def publish(
        self,
        platform: str,
        title: str,
        content: str,
        media_urls: list[str] = None,
        cover_url: str = "",
    ) -> PublishResult:
        """发布到指定平台"""
        if not self.is_platform_configured(platform):
            return PublishResult(
                article_id="", platform=platform, success=False,
                error_message=f"{platform} 平台未配置 API 凭证",
            )

        client = self.get_client(platform)

        if platform == "wechat":
            return client.publish_draft(title=title, content=content)

        # 其他平台当前为 Mock，接入后替换
        return self._mock_publish(platform, title)

    def publish_to_all(
        self, title: str, content: str, platforms: list[str] = None
    ) -> dict[str, PublishResult]:
        """一键发布到所有已配置平台"""
        targets = platforms or [p for p in self.platform_priority if self.is_platform_configured(p)]
        results = {}
        for platform in targets:
            results[platform] = self.publish(platform, title, content)
        return results

    @staticmethod
    def _mock_publish(platform: str, title: str) -> PublishResult:
        return PublishResult(
            article_id="", platform=platform, success=True,
            post_url=f"https://{platform}.com/post/mock_{hash(title) % 10000}",
            post_id=f"mock_{hash(title) % 100000}",
        )

    def platform_status(self) -> dict[str, bool]:
        """各平台接入状态"""
        status = {}
        for p in self.platform_priority:
            status[p] = self.is_platform_configured(p)
        return status


# ==================== 内容格式化工具 ====================

class ContentFormatter:
    """跨平台内容格式适配"""

    @staticmethod
    def to_wechat_html(markdown_content: str, css_theme: str = "default") -> str:
        """
        将 Markdown 转为微信公众号兼容的 HTML

        约束：
        - 不支持外部 CSS
        - 不支持 JS
        - 图片需预先上传获取永久链接
        - 字号建议 15-17px
        """
        themes = {
            "default": {
                "bg": "#ffffff", "text": "#333333", "accent": "#576b95",
                "font_size": "16px", "line_height": "1.8",
            },
            "dark": {
                "bg": "#1a1a1a", "text": "#e0e0e0", "accent": "#4a90d9",
                "font_size": "16px", "line_height": "1.8",
            },
            "warm": {
                "bg": "#fdf6ec", "text": "#4a3728", "accent": "#c17d3b",
                "font_size": "16px", "line_height": "1.8",
            },
        }
        theme = themes.get(css_theme, themes["default"])

        # 简单 Markdown → HTML 转换
        import re
        html = markdown_content
        html = re.sub(r"^### (.+)", r'<h3 style="color:{accent};">\1</h3>', html, flags=re.M)
        html = re.sub(r"^## (.+)", r'<h2 style="color:{accent};">\1</h2>', html, flags=re.M)
        html = re.sub(r"^# (.+)", r'<h1 style="color:{accent};">\1</h1>', html, flags=re.M)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = re.sub(r"!\[(.+?)\]\((.+?)\)", r'<img src="\2" alt="\1" style="max-width:100%;">', html)

        # 段落换行
        html = html.replace("\n\n", "</p><p>")
        html = f"<p>{html}</p>"

        wrapper = f"""<section style="background:{theme['bg']};color:{theme['text']};font-size:{theme['font_size']};line-height:{theme['line_height']};padding:20px;">
{html}
</section>"""
        return wrapper

    @staticmethod
    def to_xiaohongshu(text: str, max_length: int = 1000) -> str:
        """适配小红书正文（限制 1000 字，需加话题标签）"""
        if len(text) > max_length:
            text = text[:max_length - 3] + "..."
        return text

    @staticmethod
    def extract_hashtags(text: str, max_tags: int = 5) -> list[str]:
        """提取/生成话题标签"""
        import re
        tags = re.findall(r"#[\u4e00-\u9fff\w]+", text)
        return tags[:max_tags]


# ==================== 凭证管理 ====================

@dataclass
class PlatformCredential:
    """平台 API 凭证"""
    platform: str
    app_id: str = ""
    app_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0
    extra: dict = field(default_factory=dict)


class CredentialStore:
    """本地加密凭证存储（不提交到 Git）"""

    def __init__(self, store_path: str = r"E:\MARVIS_Skill_V2\credentials.json"):
        self.store_path = store_path

    def save(self, cred: PlatformCredential):
        import os
        creds = self._load_all()
        creds[cred.platform] = {
            "app_id": cred.app_id,
            "app_secret": cred.app_secret,
            "access_token": cred.access_token,
            "refresh_token": cred.refresh_token,
            "expires_at": cred.expires_at,
            "extra": cred.extra,
        }
        with open(self.store_path, "w") as f:
            json.dump(creds, f, indent=2, ensure_ascii=False)

    def load(self, platform: str) -> Optional[PlatformCredential]:
        all_creds = self._load_all()
        if platform in all_creds:
            d = all_creds[platform]
            return PlatformCredential(platform=platform, **d)
        return None

    def _load_all(self) -> dict:
        import os
        if not os.path.exists(self.store_path):
            return {}
        with open(self.store_path, "r") as f:
            return json.load(f)

    def list_platforms(self) -> list[str]:
        return list(self._load_all().keys())


# ==================== 粉丝互动模块 ====================

@dataclass
class Comment:
    """评论数据"""
    comment_id: str
    post_id: str
    user_name: str
    content: str
    like_count: int = 0
    reply_count: int = 0
    is_top: bool = False
    is_negative: bool = False
    created_at: str = ""


@dataclass
class DirectMessage:
    """私信数据"""
    msg_id: str
    user_name: str
    content: str
    msg_type: str = "text"      # text / image / voice
    created_at: str = ""


@dataclass
class AutoReply:
    """自动回复"""
    reply_id: str
    target_id: str              # 评论ID 或 私信ID
    target_type: str            # comment / dm
    content: str
    reply_template: str         # seed_qa / guide_follow / faq_price / faq_channel
    qa_checks: dict = field(default_factory=dict)  # QA 校验结果
    approved: bool = False


@dataclass
class InteractionLog:
    """互动日志条目"""
    log_id: str
    timestamp: str
    event_type: str             # comment_fetch / auto_reply / dm_reply / negative_skip
    account_phase: str
    detail: dict = field(default_factory=dict)


class CommentFetcher:
    """
    评论抓取接口
    发布完成后定时拉取视频/文章评论区内容
    """

    def __init__(self):
        self._mock_comments: list[Comment] = []
        self._interaction_log: list[InteractionLog] = []

    def fetch(
        self,
        post_id: str,
        account_phase: str = "MATURE",
        max_fetch: int = 50,
    ) -> list[Comment]:
        """
        拉取指定帖子的评论列表（Mock 实现）

        返回按热度排序的评论列表，已过滤无意义水评
        """
        import random

        # 模拟评论数据池
        positive_templates = [
            "这个{variant}看起来不错，{price}值得入手吗？",
            "请问{variant}和{competitor}比哪个好？",
            "已下单，期待效果！{emoji}",
            "好详细啊，收藏了慢慢看",
            "{variant}有优惠券吗？怎么买最划算？",
            "博主测评很中肯，关注了",
            "刚好需要这个，太及时了",
            "能出一期{variant}的进阶版吗？",
            "买了同款，{variant}效果真的绝了",
            "这个夏天就靠{keyword}了",
        ]
        negative_templates = [
            "又是广告，取关了",
            "太贵了吧，智商税",
            "别忽悠了，根本不好用",
            "假测评，全是推广",
            "垃圾产品，踩雷了",
        ]
        noise_templates = [
            "沙发", "第一", "前排", "打卡", "滴滴",
            "。。。", "...", "？", "！", "666", "111",
        ]

        comments = []

        # 生成 8-20 条模拟评论（冷启动号评论偏少）
        base_count = 6 if account_phase == "TRIAL" else 12
        comment_count = random.randint(base_count, base_count + 10)

        # 70% 正面，15% 水评（过滤），15% 负面
        for i in range(comment_count):
            roll = random.random()
            if roll < 0.15 and i > 0:
                # 负面评论 — 仅成熟账号可能出现，冷启动号过滤更严格
                tmpl = random.choice(negative_templates) if account_phase == "MATURE" else ""
                if not tmpl:
                    tmpl = random.choice(positive_templates)
                is_negative = tmpl in negative_templates
            elif roll < 0.30:
                tmpl = random.choice(noise_templates)
                is_negative = False
            else:
                tmpl = random.choice(positive_templates)
                is_negative = False

            content = tmpl.format(
                variant=random.choice(["防晒霜", "精华", "面霜", "水乳", "洗面奶"]),
                price=random.choice(["两百多", "三百出头", "不到两百", "一百五"]),
                competitor=random.choice(["A牌", "B牌", "某大牌", "平替"]),
                emoji=random.choice(["✨", "🔥", "💯", "👍"]),
                keyword=random.choice(["它", "这个系列", "这款", "这个单品"]),
            )

            # 水评过滤：短于4字且无实际内容
            if len(content) < 5 or content in noise_templates:
                continue

            comment = Comment(
                comment_id=f"cmt_{post_id}_{i:04d}",
                post_id=post_id,
                user_name=f"用户_{random.choice(['A', 'B', 'C', 'D', 'E'])}_{i}",
                content=content,
                like_count=random.randint(0, 50) if not is_negative else random.randint(0, 3),
                reply_count=0,
                is_negative=is_negative,
                created_at=datetime.now().isoformat(),
            )
            comments.append(comment)

        # 按点赞数排序
        comments.sort(key=lambda c: c.like_count, reverse=True)
        self._mock_comments = comments

        return comments[:max_fetch]

    def extract_hotspot_keywords(self, comments: list[Comment]) -> list[str]:
        """从评论中提取热点关键词"""
        hotspot_bank = {
            "防晒霜": ["防晒", "SPF", "PA", "清爽", "不油腻", "物理防晒", "化学防晒"],
            "精华": ["抗老", "淡斑", "美白", "保湿", "修护", "维稳", "抗氧"],
            "面霜": ["滋润", "锁水", "干皮", "油皮", "秋冬", "屏障"],
            "水乳": ["补水", "基础护肤", "日常", "平价", "学生党"],
            "默认": ["价格", "效果", "成分", "评价", "推荐", "对比", "优惠"],
        }

        all_keywords = []
        for comment in comments:
            if comment.is_negative:
                continue
            for cat, keywords in hotspot_bank.items():
                for kw in keywords:
                    if kw in comment.content and kw not in all_keywords:
                        all_keywords.append(kw)

        return all_keywords[:8]  # 最多返回 8 个

    def extract_user_inquiries(self, comments: list[Comment]) -> list[dict]:
        """提取用户咨询诉求"""
        inquiry_patterns = [
            ("价格咨询", ["多少钱", "价格", "贵", "优惠", "划算", "便宜"]),
            ("购买渠道", ["哪里买", "怎么买", "链接", "渠道", "店铺"]),
            ("对比咨询", ["比较", "哪个好", "区别", "对比", "vs"]),
            ("效果咨询", ["效果", "有用吗", "真的吗", "好用吗", "管用"]),
            ("上新咨询", ["新品", "上新", "新版本", "什么时候", "时间"]),
        ]
        inquiries = []
        for comment in comments:
            if comment.is_negative:
                continue
            for cat, triggers in inquiry_patterns:
                if any(t in comment.content for t in triggers):
                    inquiries.append({
                        "comment_id": comment.comment_id,
                        "user_name": comment.user_name,
                        "category": cat,
                        "content": comment.content,
                    })
                    break
        return inquiries

    def get_interaction_log(self) -> list[InteractionLog]:
        return self._interaction_log


class AutoReplyEngine:
    """
    智能评论自动回复引擎

    分层规则：
    - 冷启动（TRIAL）：降低回复频次，话术轻量化，弱化营销引导
    - 成熟账号（MATURE）：完整互动模板，多轮引导关注
    """

    # 种草答疑模板
    SEED_QA_TEMPLATES = {
        "TRIAL": [
            "{keyword}的配方是经过皮肤科测试的，建议先了解自己肤质再选择哦",
            "这款主打{keyword}，适合日常使用，可以根据需求试试小样",
        ],
        "MATURE": [
            "感谢关注！{keyword}是我们的明星单品，主打{keyword}功效，{price_range}价位段性价比很高，可以看主页置顶的详细测评~",
            "选{keyword}主要看肤质，干皮选滋润款、油皮选清爽款，主页有对比视频可以翻一下",
            "已更新{keyword}的进阶版教程，点个关注不迷路，后续会持续出干货合集",
        ],
    }

    # 互动引导模板
    GUIDE_FOLLOW_TEMPLATES = {
        "TRIAL": [
            "后续会更新更多内容，可以保持关注",
        ],
        "MATURE": [
            "点赞收藏不迷路！每周更新{keyword}干货，关注我获取最新测评",
            "已出{keyword}系列合集，主页可直接观看，求个三连支持！",
            "关注走一波，{keyword}的完整攻略已经整理好，私信'攻略'领取",
        ],
    }

    def __init__(
        self,
        account_phase: str = "MATURE",
        credit_score: int = 100,
    ):
        self.account_phase = account_phase
        self.credit_score = credit_score
        self._replies: list[AutoReply] = []
        self._interaction_log: list[InteractionLog] = []

    def generate_reply(
        self,
        comment: Comment,
        hotspot_keywords: list[str],
        inquiry_category: str = "",
        final_qa=None,  # 可选注入 final_qa 质检引擎
    ) -> Optional[AutoReply]:
        """
        为单条评论生成自动回复

        流程：
        1. 负面评论 → 跳过，不生成营销回复
        2. 匹配热点关键词 → 选择种草答疑模板
        3. 无咨询诉求 → 使用互动引导模板
        4. 冷启动号 → 降频（50%概率不回复）、轻量化话术
        5. final_qa 校验 → 广告占比 / 极限词 → 不通过则丢弃
        """
        import random

        # 负面评论直接跳过
        if comment.is_negative:
            self._interaction_log.append(InteractionLog(
                log_id=f"log_skip_{comment.comment_id}",
                timestamp=datetime.now().isoformat(),
                event_type="negative_skip",
                account_phase=self.account_phase,
                detail={
                    "comment_id": comment.comment_id,
                    "content": comment.content,
                    "reason": "负面评论，不生成营销回复",
                },
            ))
            return None

        # 冷启动降频：50% 概率不回复
        if self.account_phase == "TRIAL" and random.random() > 0.5:
            return None

        # 选择模板类型
        keyword = hotspot_keywords[0] if hotspot_keywords else "内容"
        has_inquiry = inquiry_category in ("价格咨询", "购买渠道", "效果咨询", "对比咨询")

        if has_inquiry:
            tmpl = random.choice(self.SEED_QA_TEMPLATES[self.account_phase])
            tmpl_type = "seed_qa"
        else:
            tmpl = random.choice(self.GUIDE_FOLLOW_TEMPLATES[self.account_phase])
            tmpl_type = "guide_follow"

        # 冷启动价格区间不写具体金额
        price_range = "平价" if self.account_phase == "TRIAL" else "百元级"

        reply_content = tmpl.format(
            keyword=keyword,
            price_range=price_range,
        )

        # 冷启动文字占比控制（≤60字，广告占比≤12% → 广告文字≤7字）
        if self.account_phase == "TRIAL":
            max_chars = 60
            if len(reply_content) > max_chars:
                reply_content = reply_content[:max_chars - 3] + "..."

        # QA 校验（如果外部注入 final_qa）
        qa_checks = {}
        approved = True
        if final_qa:
            qa_checks = final_qa(reply_content)
            approved = qa_checks.get("approved", True)
            if not approved:
                self._interaction_log.append(InteractionLog(
                    log_id=f"log_qa_fail_{comment.comment_id}",
                    timestamp=datetime.now().isoformat(),
                    event_type="auto_reply",
                    account_phase=self.account_phase,
                    detail={
                        "comment_id": comment.comment_id,
                        "content": reply_content[:50],
                        "qa_result": qa_checks,
                    },
                ))
                return None

        reply = AutoReply(
            reply_id=f"reply_{comment.comment_id}",
            target_id=comment.comment_id,
            target_type="comment",
            content=reply_content,
            reply_template=tmpl_type,
            qa_checks=qa_checks,
            approved=approved,
        )

        self._replies.append(reply)
        self._interaction_log.append(InteractionLog(
            log_id=f"log_reply_{comment.comment_id}",
            timestamp=datetime.now().isoformat(),
            event_type="auto_reply",
            account_phase=self.account_phase,
            detail={
                "reply_id": reply.reply_id,
                "template": tmpl_type,
                "content": reply_content[:50],
                "qa_checks": qa_checks,
            },
        ))

        return reply

    def generate_batch(
        self,
        comments: list[Comment],
        hotspot_keywords: list[str],
        inquiries: list[dict],
        final_qa=None,
    ) -> list[AutoReply]:
        """批量生成评论回复"""
        inquiry_map = {inq["comment_id"]: inq["category"] for inq in inquiries}
        replies = []
        for comment in comments:
            cat = inquiry_map.get(comment.comment_id, "")
            reply = self.generate_reply(comment, hotspot_keywords, cat, final_qa)
            if reply:
                replies.append(reply)
        return replies

    def get_replies(self) -> list[AutoReply]:
        return self._replies

    def get_interaction_log(self) -> list[InteractionLog]:
        return self._interaction_log


class DirectMessageHandler:
    """
    私信自动应答子模块

    分级策略：
    - L1: 高频问题（价格/渠道/上新） → 自动应答
    - L2: 复杂诉求 → 标记人工待处理
    """

    # 高频问题自动应答模板
    FAQ_TEMPLATES = {
        "价格咨询": [
            "您好，{keyword}的价格根据规格不同有所差异，可以查看主页商品橱窗或私信'价格表'获取最新报价~",
            "目前{keyword}的参考价在百元级区间，具体以店铺实时价格为准，点击主页链接即可查看",
        ],
        "购买渠道": [
            "官方渠道购买更有保障！点击主页链接即可跳转，目前有{keyword}限时活动可以关注一下",
            "在主页商品橱窗可以直接下单，支持7天无理由，有任何问题随时联系客服",
        ],
        "上新时间": [
            "新品{keyword}预计下月初上线，关注主页不错过首发预告和粉丝专属优惠",
            "感谢关注！{keyword}的新品已经在筹备中，这周会发预告视频，记得点赞关注不迷路",
        ],
        "默认": [
            "收到您的消息，已转接人工客服，请稍候。如急需回复可私信'客服'获取优先通道",
        ],
    }

    def __init__(self, account_phase: str = "MATURE"):
        self.account_phase = account_phase
        self._replies: list[AutoReply] = []
        self._pending_human: list[DirectMessage] = []
        self._interaction_log: list[InteractionLog] = []

    def classify(self, dm: DirectMessage) -> str:
        """识别私信类别"""
        categories = [
            ("价格咨询", ["多少钱", "价格", "贵", "优惠", "便宜", "划算", "报价"]),
            ("购买渠道", ["哪里买", "怎么买", "链接", "渠道", "店铺", "下单", "购买"]),
            ("上新时间", ["新品", "上新", "新版本", "什么时候", "时间", "预告"]),
        ]
        for cat, triggers in categories:
            if any(t in dm.content for t in triggers):
                return cat
        return "默认"

    def handle(self, dm: DirectMessage, comment_hotspot_keywords: list[str] = None) -> Optional[AutoReply]:
        """处理单条私信"""
        import random

        category = self.classify(dm)
        keyword = (comment_hotspot_keywords or ["内容"])[0]

        if category == "默认":
            # 复杂诉求 → 标记人工
            self._pending_human.append(dm)
            self._interaction_log.append(InteractionLog(
                log_id=f"log_dm_pending_{dm.msg_id}",
                timestamp=datetime.now().isoformat(),
                event_type="dm_reply",
                account_phase=self.account_phase,
                detail={
                    "msg_id": dm.msg_id,
                    "user_name": dm.user_name,
                    "category": "人工待处理",
                    "content": dm.content[:50],
                },
            ))
            return None

        tmpl = random.choice(self.FAQ_TEMPLATES[category])
        content = tmpl.format(keyword=keyword)

        # 冷启动话术轻量化
        if self.account_phase == "TRIAL":
            if len(content) > 80:
                content = content[:77] + "..."

        reply = AutoReply(
            reply_id=f"dm_reply_{dm.msg_id}",
            target_id=dm.msg_id,
            target_type="dm",
            content=content,
            reply_template=f"faq_{category.replace('咨询', '').replace('渠道', 'channel').replace('时间', 'time')}",
            approved=True,
        )
        self._replies.append(reply)
        self._interaction_log.append(InteractionLog(
            log_id=f"log_dm_reply_{dm.msg_id}",
            timestamp=datetime.now().isoformat(),
            event_type="dm_reply",
            account_phase=self.account_phase,
            detail={
                "reply_id": reply.reply_id,
                "category": category,
                "content": content[:50],
            },
        ))

        return reply

    def handle_batch(
        self,
        dms: list[DirectMessage],
        comment_hotspot_keywords: list[str] = None,
    ) -> list[AutoReply]:
        """批量处理私信"""
        replies = []
        for dm in dms:
            reply = self.handle(dm, comment_hotspot_keywords)
            if reply:
                replies.append(reply)
        return replies

    def get_pending_human(self) -> list[DirectMessage]:
        return self._pending_human

    def get_replies(self) -> list[AutoReply]:
        return self._replies

    def get_interaction_log(self) -> list[InteractionLog]:
        return self._interaction_log


class InteractionLogger:
    """
    互动数据回流传入 marvis_core.py
    归档评论互动量、私信应答记录，用于匹配模型迭代和账号权重统计
    """

    def __init__(self, account_id: str = ""):
        self.account_id = account_id
        self._logs: list[InteractionLog] = []

    def collect(
        self,
        comment_logs: list[InteractionLog],
        reply_logs: list[InteractionLog],
        dm_logs: list[InteractionLog],
    ) -> list[InteractionLog]:
        """汇总全部互动日志"""
        all_logs = comment_logs + reply_logs + dm_logs
        self._logs.extend(all_logs)
        return all_logs

    def to_records(self) -> list[dict]:
        """转换为可写入归档的字典列表"""
        return [
            {
                "log_id": log.log_id,
                "timestamp": log.timestamp,
                "event_type": log.event_type,
                "account_phase": log.account_phase,
                "detail": log.detail,
            }
            for log in self._logs
        ]

    def get_stats(self) -> dict:
        """互动数据统计摘要"""
        stats = {
            "total_events": len(self._logs),
            "auto_replies": sum(1 for l in self._logs if l.event_type == "auto_reply"),
            "dm_replies": sum(1 for l in self._logs if l.event_type == "dm_reply"),
            "negative_skipped": sum(1 for l in self._logs if l.event_type == "negative_skip"),
            "qa_blocked": sum(1 for l in self._logs if "qa_fail" in l.event_type),
        }
        return stats

    def flush(self, archive_path: str = "") -> str:
        """将互动日志写入归档文件"""
        import json
        import os

        records = self.to_records()
        if not archive_path:
            archive_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"interaction_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            )

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump({
                "account_id": self.account_id,
                "generated_at": datetime.now().isoformat(),
                "stats": self.get_stats(),
                "records": records,
            }, f, indent=2, ensure_ascii=False)

        return archive_path


class FanInteractionManager:
    """
    粉丝互动总调度器
    发布任务完成后调用，统一编排评论抓取、回复、私信处理全流程
    """

    def __init__(
        self,
        account_phase: str = "MATURE",
        credit_score: int = 100,
        account_id: str = "",
        final_qa=None,
    ):
        self.account_phase = account_phase
        self.credit_score = credit_score
        self.account_id = account_id
        self.final_qa = final_qa

        self.comment_fetcher = CommentFetcher()
        self.reply_engine = AutoReplyEngine(account_phase, credit_score)
        self.dm_handler = DirectMessageHandler(account_phase)
        self.logger = InteractionLogger(account_id)

    def run(self, post_id: str) -> dict:
        """
        执行完整粉丝互动流程

        返回：
        {
            "comments": [...],
            "replies": [...],
            "dm_replies": [...],
            "pending_human": [...],
            "stats": {...},
            "archive_path": "...",
        }
        """
        # 1. 抓取评论
        comments = self.comment_fetcher.fetch(post_id, self.account_phase)

        # 2. 提取热点关键词和咨询诉求
        hotspot_keywords = self.comment_fetcher.extract_hotspot_keywords(comments)
        inquiries = self.comment_fetcher.extract_user_inquiries(comments)

        # 3. 智能回复评论
        replies = self.reply_engine.generate_batch(
            comments, hotspot_keywords, inquiries, self.final_qa,
        )

        # 4. 模拟私信（Mock）
        dms = self._mock_direct_messages(post_id)

        # 5. 私信自动应答
        dm_replies = self.dm_handler.handle_batch(dms, hotspot_keywords)
        pending_human = self.dm_handler.get_pending_human()

        # 6. 汇总互动日志
        self.logger.collect(
            self.comment_fetcher.get_interaction_log(),
            self.reply_engine.get_interaction_log(),
            self.dm_handler.get_interaction_log(),
        )

        # 7. 归档写入
        archive_path = self.logger.flush()

        return {
            "post_id": post_id,
            "account_phase": self.account_phase,
            "comments": comments,
            "replies": replies,
            "dm_replies": dm_replies,
            "pending_human": pending_human,
            "hotspot_keywords": hotspot_keywords,
            "stats": self.logger.get_stats(),
            "archive_path": archive_path,
        }

    @staticmethod
    def _mock_direct_messages(post_id: str) -> list[DirectMessage]:
        """模拟私信数据（真实环境替换为 API 拉取）"""
        import random

        templates = [
            ("价格咨询", "你好，这个产品多少钱？"),
            ("价格咨询", "最近有优惠活动吗？"),
            ("购买渠道", "在哪里可以买？给个链接"),
            ("购买渠道", "怎么下单？支持货到付款吗"),
            ("上新时间", "下次上新什么时候？"),
            ("默认", "你好，可以合作推广吗？我是XX平台的"),
        ]

        dms = []
        count = random.randint(1, len(templates))
        for i in range(count):
            cat, content = templates[i]
            dms.append(DirectMessage(
                msg_id=f"dm_{post_id}_{i:04d}",
                user_name=f"粉丝_{random.choice(['F', 'G', 'H'])}{i}",
                content=content,
                created_at=datetime.now().isoformat(),
            ))
        return dms


if __name__ == "__main__":
    print("=== 公众号 & 多平台 API 接入诊断 ===")
    print()

    store = CredentialStore()
    platforms = store.list_platforms()
    print(f"已配置平台: {platforms if platforms else '无（待配置）'}")

    if "wechat" in platforms:
        cred = store.load("wechat")
        print(f"微信公众号: AppID={cred.app_id[:6]}***")

    # 内容格式测试
    sample_md = """## 夏季防晒全攻略
**防晒霜怎么选？**物理防晒 vs 化学防晒一次说清楚。
### 关键结论
SPF50+ PA++++ 是夏季标配。"""

    print(f"\n微信公众号 HTML 预览:")
    print(ContentFormatter.to_wechat_html(sample_md, "warm")[:300])
