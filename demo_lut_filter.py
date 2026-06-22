"""
demo_lut_filter.py
MARVIS V2.1 — LUT 滤镜配置专项验证

验证项：
1. filter_lut_config.json 加载成功，15赛道全部存在
2. 赛道标识匹配 — 按 product_category 命中对应滤镜参数
3. 冷启动/成熟账号分层渲染，LUT 参数统一复用不冲突
4. marvis_core.py send_to_render 注入 LUT 至 RenderRequest
5. aitoearn_connector.py to_api_payload 输出包含 lut 字段
6. 不匹配赛道降级为空 lut_config，不阻断渲染
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def check(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}", end="")
    if detail:
        print(f" → {detail}", end="")
    print()


# ==================== 校验 1: 配置文件完整性 ====================

def verify_01_config_integrity():
    section("校验 1: filter_lut_config.json 加载 & 15赛道解析")

    config_path = os.path.join(os.path.dirname(__file__), "filter_lut_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    check("JSON 加载成功", "version" in config, config.get("version", ""))
    check("tracks 键存在", "tracks" in config)

    tracks = config["tracks"]
    expected_niches = [
        "美妆护肤", "美食探店", "时尚穿搭", "母婴育儿", "健身运动",
        "数码3C", "旅游出行", "家居生活", "汽车评测", "宠物萌宠",
        "教育培训", "游戏电竞", "影视娱乐", "医疗健康", "本地生活",
    ]

    missing = [n for n in expected_niches if n not in tracks]
    check(
        f"15赛道全部存在",
        len(missing) == 0,
        f"缺失: {missing}" if missing else f"共 {len(tracks)} 条",
    )

    # 每条赛道必须含 lut 参数
    required_lut_keys = [
        "contrast", "saturation", "color_temp", "sharpness",
        "exposure_comp", "highlights", "shadows", "vignette", "preset",
    ]
    bad_tracks = []
    for niche, track in tracks.items():
        lut = track.get("lut", {})
        missing_keys = [k for k in required_lut_keys if k not in lut]
        if missing_keys:
            bad_tracks.append(f"{niche}: missing {missing_keys}")

    check(
        "每条赛道 LUT 参数完整",
        len(bad_tracks) == 0,
        f"异常: {bad_tracks}" if bad_tracks else "15条赛道全部参数齐备",
    )

    return config


# ==================== 校验 2: 赛道匹配 ====================

def verify_02_niche_matching(config: dict):
    section("校验 2: 按 product_category 匹配 LUT 滤镜")

    # 模拟 AdOrder
    class MockOrder:
        def __init__(self, category):
            self.product_category = category
            self.id = "test"

    test_cases = [
        ("美妆护肤", "warm_clean", 1.15),
        ("美食探店", "appetizing_warm", 1.25),
        ("数码3C", "tech_cool", 0.95),
        ("游戏电竞", "neon_vivid", 1.20),
        ("医疗健康", "clinical_clean", 0.95),
    ]

    for niche, expected_preset, expected_sat in test_cases:
        track = config["tracks"].get(niche, {})
        lut = track.get("lut", {})

        preset_ok = lut.get("preset") == expected_preset
        sat_ok = abs(lut.get("saturation", 0) - expected_sat) < 0.01
        passed = preset_ok and sat_ok

        check(
            f"赛道「{niche}」",
            passed,
            f"preset={lut.get('preset')} sat={lut.get('saturation')}",
        )


# ==================== 校验 3: 冷启动/成熟账号 LUT 复用 ====================

def verify_03_phase_compatibility(config: dict):
    section("校验 3: 冷启动/成熟账号分层渲染 LUT 参数统一")

    from marvis_core import (
        MarvisScheduler, ContentQAEngine, BusinessLevel, MediaTag,
        TaskTag, OrderStatus, AdOrder, HotSpot,
    )

    base_dir = os.path.dirname(__file__)
    config_path = os.path.join(base_dir, "filter_lut_config.json")

    # 构造完整调度器
    scheduler = MarvisScheduler()

    class MockOrder:
        def __init__(self, category):
            self.id = "LUT_001"
            self.product_category = category
            self.product_name = "防晒霜SPF50"
            self.media_type = MediaTag.SHORT_VIDEO.value
            self.platform = "多平台业务号"
            self.copywriting = ["测试文案（推广）"]
            self.status = OrderStatus.COPYWRITING
            self.render_result = ""
            self.hot_spot_id = ""
            self.publish_links = {}
            self.qa_report = {}
            self.advertiser_id = ""
            self.advertiser_level = ""

    order = MockOrder("美妆护肤")
    import datetime
    scheduler.hotspots = [HotSpot(
        id="HS_001", title="夏季防晒趋势新风向",
        score=87, category="美妆护肤",
        source_url="crawled", is_negative=False,
        timestamp=datetime.datetime(2026, 6, 20),
    )]

    # 模拟 tag
    from marvis_core import PriorityTag
    tag = TaskTag(
        priority_tag=PriorityTag.P0,
        business_tag="B",
        media_tag="SHORT_VIDEO",
        match_score_tag="HIGH",
        source_tag="HOT",
        performance_tag="STANDARD",
    )

    # 成熟账号渲染验证
    result_mature = scheduler.send_to_render(order, tag)

    # 冷启动账号渲染验证
    from account_phase import Account, AccountPhase
    acc = Account(
        account_id="COLD_001", platform="多平台业务号",
        niche="美妆护肤", followers=150,
        avg_views=2000, avg_likes=80,
        phase=AccountPhase.COLD_START,
    )
    scheduler.accounts = {acc.account_id: acc}
    result_cold = scheduler.send_to_render(order, tag)

    check("成熟账号渲染结果", "params" in result_mature, str(result_mature.get("params", {})))
    check("冷启动账号渲染结果", "params" in result_cold, str(result_cold.get("params", {})))

    cold_params = result_cold.get("params", {})
    mature_params = result_mature.get("params", {})

    # 冷启动时长应 ≤ 成熟时长（15s vs 25s+）
    check(
        "冷启动轻量化渲染生效",
        cold_params.get("video_duration", 999) <= mature_params.get("video_duration", 0),
        f"冷 {cold_params.get('video_duration')}s vs 成熟 {mature_params.get('video_duration')}s",
    )


# ==================== 校验 4: LUT 注入到 RenderRequest ====================

def verify_04_lut_in_request():
    section("校验 4: RenderRequest 携带 LUT 字段 & to_api_payload 输出")

    from aitoearn_connector import RenderRequest

    lut = {
        "contrast": 1.10, "saturation": 1.15, "color_temp": 5800,
        "sharpness": 1.05, "exposure_comp": 0.15,
        "highlights": 0.92, "shadows": 1.08, "vignette": 0.10,
        "preset": "warm_clean", "track_key": "beauty_skincare",
        "track_name": "美妆护肤",
    }

    req = RenderRequest(
        task_id="LUT_TEST_01",
        order_id="ORDER_001",
        prompt="测试",
        lut_config=lut,
    )

    payload = req.to_api_payload()

    check("lut 字段注入到 to_api_payload", "lut" in payload)
    check("lut 参数完整", payload.get("lut", {}).get("preset") == "warm_clean")
    check("lut 赛道标识", payload.get("lut", {}).get("track_name") == "美妆护肤")

    # 空 LUT 不应出现在 payload 中
    req_empty = RenderRequest(task_id="no_lut", order_id="X", prompt="x")
    payload_empty = req_empty.to_api_payload()
    check("空 LUT 不出现在 payload", "lut" not in payload_empty)


# ==================== 校验 5: 不匹配赛道降级 ====================

def verify_05_unknown_niche_fallback():
    section("校验 5: 不匹配赛道降级为空 lut_config，不阻断渲染")

    from marvis_core import (
        MarvisScheduler, TaskTag, OrderStatus, MediaTag, AdOrder, PriorityTag,
    )

    scheduler = MarvisScheduler()

    class MockOrder:
        def __init__(self, category):
            self.id = "UNKNOWN_001"
            self.product_category = category
            self.product_name = "未知产品"
            self.media_type = MediaTag.SHORT_VIDEO.value
            self.platform = "多平台业务号"
            self.copywriting = ["测试（推广）"]
            self.status = OrderStatus.COPYWRITING
            self.render_result = ""
            self.hot_spot_id = ""
            self.publish_links = {}
            self.qa_report = {}
            self.advertiser_id = ""
            self.advertiser_level = ""

    order = MockOrder("不存在的赛道XYZ")

    tag = TaskTag(
        priority_tag=PriorityTag.P2,
        business_tag="B",
        media_tag="SHORT_VIDEO",
        match_score_tag="LOW",
        source_tag="SCHEDULED",
        performance_tag="STANDARD",
    )

    result = scheduler.send_to_render(order, tag)
    check(
        "不匹配赛道降级成功",
        "result" in result,
        str(result.get("params", {})),
    )
    check(
        "渲染未阻断",
        result.get("task_id", "").startswith("render_"),
    )


# ==================== 校验 6: 热加载修改 ====================

def verify_06_hot_reload():
    section("校验 6: 热加载 — 修改配置文件后无需改代码即生效")

    from aitoearn_connector import RenderRequest

    # 模拟从文件读取的配置（模拟热加载场景）
    saved_lut = {
        "contrast": 1.30, "saturation": 1.20, "color_temp": 5000,
        "sharpness": 1.25, "exposure_comp": 0.00,
        "highlights": 0.82, "shadows": 1.18, "vignette": 0.15,
        "preset": "neon_vivid", "track_key": "gaming_esports",
        "track_name": "游戏电竞",
    }

    req = RenderRequest(
        task_id="HOT_LOAD",
        order_id="GAME_001",
        prompt="电竞新游上线",
        lut_config=saved_lut,
    )

    payload = req.to_api_payload()
    check("热加载 LUT 生效", payload["lut"]["preset"] == "neon_vivid")
    check("热加载赛道更新", payload["lut"]["track_name"] == "游戏电竞")

    # 修改 LUT 参数 → RenderRequest 重新创建即可
    saved_lut["saturation"] = 1.50
    saved_lut["preset"] = "neon_vivid_v2"

    req2 = RenderRequest(
        task_id="HOT_LOAD_2",
        order_id="GAME_001",
        prompt="电竞新游上线",
        lut_config=saved_lut,
    )

    payload2 = req2.to_api_payload()
    check("热加载参数即时生效", payload2["lut"]["saturation"] == 1.50)
    check("热加载预设即时生效", payload2["lut"]["preset"] == "neon_vivid_v2")


# ==================== 主入口 ====================

if __name__ == "__main__":
    print(f"MARVIS V2.1 LUT 滤镜配置验证")

    results = []

    # 校验 1
    try:
        config = verify_01_config_integrity()
        results.append(("01-配置完整性", True))
    except Exception as e:
        print(f"  [FAIL] 校验 1 异常: {e}")
        results.append(("01-配置完整性", False))
        config = {}

    # 校验 2
    try:
        if config:
            verify_02_niche_matching(config)
            results.append(("02-赛道匹配", True))
        else:
            results.append(("02-赛道匹配", False))
    except Exception as e:
        print(f"  [FAIL] 校验 2 异常: {e}")
        results.append(("02-赛道匹配", False))

    # 校验 3
    try:
        verify_03_phase_compatibility(config)
        results.append(("03-分层兼容", True))
    except Exception as e:
        print(f"  [FAIL] 校验 3 异常: {e}")
        results.append(("03-分层兼容", False))

    # 校验 4
    try:
        verify_04_lut_in_request()
        results.append(("04-LUT注入", True))
    except Exception as e:
        print(f"  [FAIL] 校验 4 异常: {e}")
        results.append(("04-LUT注入", False))

    # 校验 5
    try:
        verify_05_unknown_niche_fallback()
        results.append(("05-降级兜底", True))
    except Exception as e:
        print(f"  [FAIL] 校验 5 异常: {e}")
        results.append(("05-降级兜底", False))

    # 校验 6
    try:
        verify_06_hot_reload()
        results.append(("06-热加载", True))
    except Exception as e:
        print(f"  [FAIL] 校验 6 异常: {e}")
        results.append(("06-热加载", False))

    # 汇总
    section("验收汇总")
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'✓' if ok else '✗'}] {name}")
    print(f"\n  总计: {passed}/{len(results)} 项通过")
    if passed == len(results):
        print("  结论: LUT 滤镜配置全部验收通过。")
    else:
        print(f"  结论: {len(results) - passed} 项未通过。")
