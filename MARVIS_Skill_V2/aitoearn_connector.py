"""
MARVIS V2.0 - AiToEarn 渲染服务连接器
生产级：真实 API 对接 + 本地降级渲染 + 任务队列
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import time
import json
import hashlib


class RenderStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RenderEngine(str, Enum):
    """支持的渲染引擎"""
    AITOEARN_CLOUD = "aitoearn_cloud"       # AiToEarn 云端集群
    COMFYUI_LOCAL = "comfyui_local"         # 本地 ComfyUI
    OPENVINO_LOCAL = "openvino_local"        # 本地 OpenVINO (Intel AIPC)
    FFMPEG_FALLBACK = "ffmpeg_fallback"      # FFmpeg 兜底


@dataclass
class RenderRequest:
    """标准化渲染请求"""
    task_id: str
    order_id: str
    prompt: str                           # 文案 / 画面描述
    engine: RenderEngine = RenderEngine.AITOEARN_CLOUD

    # 视觉参数
    width: int = 1080
    height: int = 1920
    duration_sec: int = 30
    fps: int = 30
    resolution: str = "1080P"

    # 风格控制
    style_preset: str = "social_media"    # social_media / cinematic / clean
    color_palette: str = "warm_vibrant"   # warm_vibrant / cool_professional / neutral
    text_overlay: str = ""                # 贴片文案
    logo_url: str = ""                    # 品牌 Logo URL
    cta_text: str = ""                    # Call To Action 文字

    # V2.1: LUT 滤镜参数（按赛道匹配）
    lut_config: dict = field(default_factory=dict)

    # 回调
    callback_url: str = ""
    priority: int = 0                     # 0-10，越高越优先

    # 元信息
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_api_payload(self) -> dict:
        """转为 AiToEarn Cloud API 请求体"""
        payload = {
            "task_id": self.task_id,
            "order_id": self.order_id,
            "prompt": self.prompt,
            "engine": self.engine.value,
            "visual": {
                "width": self.width,
                "height": self.height,
                "duration_sec": self.duration_sec,
                "fps": self.fps,
                "resolution": self.resolution,
                "style_preset": self.style_preset,
                "color_palette": self.color_palette,
            },
            "overlay": {
                "text": self.text_overlay,
                "logo_url": self.logo_url,
                "cta_text": self.cta_text,
            },
            "callback_url": self.callback_url,
            "priority": self.priority,
        }
        # V2.1: 注入 LUT 滤镜参数
        if self.lut_config:
            payload["lut"] = self.lut_config
        return payload


@dataclass
class RenderResult:
    """渲染结果"""
    task_id: str
    status: RenderStatus
    output_url: str = ""
    output_path: str = ""
    thumbnail_url: str = ""
    duration_rendered: float = 0.0
    error_message: str = ""
    metadata: dict = field(default_factory=dict)


# ==================== AiToEarn Cloud API 客户端 ====================

class AiToEarnCloudClient:
    """
    AiToEarn 云端渲染 API 客户端

    接口协议（单向调度）：
    - MARVIS → POST /api/v2/render/submit   下发渲染任务
    - MARVIS → GET  /api/v2/render/status    查询任务状态
    - MARVIS → DELETE /api/v2/render/cancel  取消任务
    - AiToEarn → POST <callback_url>         渲染完成回调（单向回流）
    """

    def __init__(
        self,
        api_base: str = "https://api.aitoearn.com/v2",
        api_key: str = "",
        timeout: int = 30,
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.timeout = timeout
        self._active_tasks: dict[str, RenderRequest] = {}

    def submit(self, request: RenderRequest) -> RenderResult:
        """
        提交渲染任务到 AiToEarn 云端

        POST /api/v2/render/submit
        Headers: Authorization: Bearer <api_key>
        Body: request.to_api_payload()
        """
        if not self.api_key:
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.FAILED,
                error_message="缺少 API Key，请在初始化时提供 api_key 参数",
            )

        # 真实调用逻辑（部署时启用）
        try:
            import requests
            resp = requests.post(
                f"{self.api_base}/render/submit",
                json=request.to_api_payload(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._active_tasks[request.task_id] = request
                return RenderResult(
                    task_id=request.task_id,
                    status=RenderStatus(data.get("status", "queued")),
                    output_url=data.get("output_url", ""),
                )
            else:
                return RenderResult(
                    task_id=request.task_id,
                    status=RenderStatus.FAILED,
                    error_message=f"API 错误 {resp.status_code}: {resp.text[:200]}",
                )
        except ImportError:
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.FAILED,
                error_message="缺少 requests 库，请执行: pip install requests",
            )
        except Exception as e:
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.FAILED,
                error_message=str(e),
            )

    def query_status(self, task_id: str) -> RenderResult:
        """查询渲染任务状态"""
        try:
            import requests
            resp = requests.get(
                f"{self.api_base}/render/status/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return RenderResult(
                    task_id=task_id,
                    status=RenderStatus(data.get("status", "unknown")),
                    output_url=data.get("output_url", ""),
                    duration_rendered=data.get("duration_rendered", 0),
                    metadata=data.get("metadata", {}),
                )
        except Exception as e:
            return RenderResult(task_id=task_id, status=RenderStatus.FAILED, error_message=str(e))

    def cancel(self, task_id: str) -> bool:
        """取消渲染任务"""
        try:
            import requests
            resp = requests.delete(
                f"{self.api_base}/render/cancel/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            return resp.status_code == 200
        except Exception:
            return False

    def wait_for_completion(self, task_id: str, poll_interval: int = 5, max_wait: int = 300) -> RenderResult:
        """轮询等待渲染完成"""
        elapsed = 0
        while elapsed < max_wait:
            result = self.query_status(task_id)
            if result.status == RenderStatus.COMPLETED:
                return result
            if result.status == RenderStatus.FAILED:
                return result
            time.sleep(poll_interval)
            elapsed += poll_interval
        return RenderResult(task_id=task_id, status=RenderStatus.FAILED, error_message="渲染超时")


# ==================== 本地降级渲染器 ====================

class LocalFallbackRenderer:
    """
    本地降级渲染器：AiToEarn 云端不可用时自动降级

    降级策略优先级:
    1. ComfyUI 本地 (E:\ComfyUI-aki-v3\)
    2. OpenVINO Z-Image Turbo (Intel AIPC)
    3. FFmpeg 静态帧合成 (兜底)
    """

    def __init__(self, output_dir: str = r"E:\MARVIS_Skill_V2\render_output"):
        self.output_dir = output_dir
        import os
        os.makedirs(output_dir, exist_ok=True)

    def detect_available_engine(self) -> RenderEngine:
        """检测可用的本地渲染引擎"""
        import os
        # 检测 ComfyUI
        if os.path.exists(r"E:\ComfyUI-aki-v3\main.py"):
            return RenderEngine.COMFYUI_LOCAL
        # 检测 OpenVINO
        if os.path.exists(r"C:\Program Files\Intel\openvino"):
            return RenderEngine.OPENVINO_LOCAL
        return RenderEngine.FFMPEG_FALLBACK

    def render(self, request: RenderRequest) -> RenderResult:
        """执行本地渲染"""
        engine = self.detect_available_engine()

        if engine == RenderEngine.COMFYUI_LOCAL:
            return self._render_comfyui(request)
        elif engine == RenderEngine.OPENVINO_LOCAL:
            return self._render_openvino(request)
        else:
            return self._render_ffmpeg_fallback(request)

    def _render_comfyui(self, request: RenderRequest) -> RenderResult:
        """ComfyUI 本地渲染"""
        output_path = f"{self.output_dir}\\{request.task_id}.mp4"

        # ComfyUI API workflow
        workflow = {
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "frames": request.duration_sec * request.fps,
            "output_path": output_path,
        }

        try:
            import requests
            resp = requests.post(
                "http://127.0.0.1:8188/prompt",
                json={"prompt": workflow},
                timeout=10,
            )
            if resp.status_code == 200:
                return RenderResult(
                    task_id=request.task_id,
                    status=RenderStatus.PROCESSING,
                    output_path=output_path,
                    metadata={"engine": "comfyui_local"},
                )
        except Exception as e:
            pass  # 降级到 FFmpeg

        return self._render_ffmpeg_fallback(request)

    def _render_openvino(self, request: RenderRequest) -> RenderResult:
        """OpenVINO Z-Image Turbo 本地渲染"""
        output_path = f"{self.output_dir}\\{request.task_id}.png"
        try:
            import subprocess
            subprocess.run([
                "python", "-c",
                f"from openvino_txt2img import generate; "
                f"generate(prompt='{request.prompt}', output='{output_path}', "
                f"width={request.width}, height={request.height})"
            ], timeout=120, check=False)
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.COMPLETED,
                output_path=output_path,
            )
        except Exception:
            return self._render_ffmpeg_fallback(request)

    def _render_ffmpeg_fallback(self, request: RenderRequest) -> RenderResult:
        """
        FFmpeg 兜底渲染：生成纯色+文字的占位视频
        这是最后降级方案，确保流程不中断
        """
        output_path = f"{self.output_dir}\\{request.task_id}_fallback.mp4"
        import subprocess
        import os

        # 构建 FFmpeg 命令：生成带文字的纯色视频
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={request.width}x{request.height}:d={request.duration_sec}:r={request.fps}",
            "-vf", (
                f"drawtext=text='AiToEarn 降级渲染':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-60,"
                f"drawtext=text='{request.order_id}':fontsize=32:fontcolor=#00d4ff:x=(w-text_w)/2:y=(h-text_h)/2+20,"
                f"drawtext=text='分辨率:{request.resolution}':fontsize=24:fontcolor=#888888:x=(w-text_w)/2:y=(h-text_h)/2+70"
            ),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.COMPLETED,
                output_path=output_path,
                metadata={
                    "engine": "ffmpeg_fallback",
                    "note": "云端 AiToEarn 不可用，已使用 FFmpeg 本地降级渲染",
                },
            )
        except FileNotFoundError:
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.FAILED,
                error_message="FFmpeg 未安装。请安装 FFmpeg 或配置 AiToEarn 云端 API Key",
            )
        except Exception as e:
            return RenderResult(
                task_id=request.task_id,
                status=RenderStatus.FAILED,
                error_message=f"FFmpeg 渲染失败: {e}",
            )


# ==================== 统一渲染调度器 ====================

class RenderOrchestrator:
    """
    渲染编排器：自动选择引擎（云端优先 → 本地降级）
    单向通信：MARVIS → AiToEarn，无反向
    """

    def __init__(
        self,
        cloud_api_key: str = "",
        cloud_api_base: str = "https://api.aitoearn.com/v2",
        local_output_dir: str = r"E:\MARVIS_Skill_V2\render_output",
    ):
        self.cloud = AiToEarnCloudClient(api_base=cloud_api_base, api_key=cloud_api_key)
        self.local = LocalFallbackRenderer(output_dir=local_output_dir)
        self.cloud_available = bool(cloud_api_key)

    def submit_render(self, request: RenderRequest, force_local: bool = False) -> RenderResult:
        """
        提交渲染任务，自动路由：
        1. AiToEarn 云端（有 API Key）
        2. ComfyUI 本地（检测到安装）
        3. FFmpeg 兜底
        """
        if not force_local and self.cloud_available:
            result = self.cloud.submit(request)
            if result.status != RenderStatus.FAILED:
                return result
            # 云端失败，降级
            print(f"[RenderOrchestrator] 云端渲染失败: {result.error_message}，降级到本地")

        return self.local.render(request)

    def generate_request_from_order(
        self,
        order_id: str,
        prompt: str,
        resolution: str = "1080P",
        width: int = 1080,
        height: int = 1920,
        duration: int = 30,
    ) -> RenderRequest:
        """从广告订单生成标准化渲染请求"""
        task_id = f"render_{order_id}_{hashlib.md5(prompt.encode()).hexdigest()[:8]}"
        return RenderRequest(
            task_id=task_id,
            order_id=order_id,
            prompt=prompt,
            width=width,
            height=height,
            duration_sec=duration,
            resolution=resolution,
            priority=5,
        )


# ==================== 接入测试 ====================

if __name__ == "__main__":
    print("=== AiToEarn 渲染服务连接器 诊断 ===")
    print()

    # 1. 引擎检测
    local = LocalFallbackRenderer()
    engine = local.detect_available_engine()
    print(f"本地可用引擎: {engine.value}")

    # 2. 云端连接测试
    orchestrator = RenderOrchestrator()
    print(f"云端 API: {'已配置' if orchestrator.cloud_available else '未配置（将使用本地/FFmpeg 降级）'}")

    # 3. 生成测试请求
    req = orchestrator.generate_request_from_order(
        order_id="TEST001",
        prompt="美妆博主展示粉底液遮瑕效果，自然光线，温暖色调",
        resolution="1080P",
    )
    print(f"\n测试渲染请求:")
    print(f"  task_id: {req.task_id}")
    print(f"  prompt: {req.prompt[:40]}...")
    print(f"  尺寸: {req.width}x{req.height}")
    print(f"  时长: {req.duration_sec}s @ {req.fps}fps")

    # 4. 提交渲染（自动降级）
    result = orchestrator.submit_render(req, force_local=True)
    print(f"\n渲染结果:")
    print(f"  状态: {result.status.value}")
    print(f"  输出: {result.output_path}")
    if result.error_message:
        print(f"  错误: {result.error_message}")
    if result.metadata:
        print(f"  元信息: {result.metadata}")
