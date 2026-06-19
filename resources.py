"""资源管理器 —— 负责插件的文件读写、HTTP 下载及定时清理等资源操作。"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

import aiofiles
import aiohttp

from astrbot.api import AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .plugin_logger import PluginLogger, PluginLoggerLevel
from .sign_config import SignData


class ResourceManager:
    """统一管理插件运行时的文件 IO、图片下载和定时删除。"""

    def __init__(self, name: str, config: AstrBotConfig) -> None:
        self.config: AstrBotConfig = config

        # ---- 日志 ----
        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        # ---- 目录结构 ----
        data_root = get_astrbot_data_path()

        self.plugin_dir: str = os.path.join(data_root, "plugins", name)
        self.data_dir: str = os.path.join(data_root, "plugin_data", name)
        self.signdata_file: str = os.path.join(self.data_dir, "sign_data.json")

        # 塔罗牌资源
        self.tarots_dir: str = os.path.join(self.plugin_dir, "tarots")
        self.tarots_meaning_file: str = os.path.join(self.tarots_dir, "tarot_meanings.json")
        self.tarots_cdn_base: str = (
            "https://raw.giteeusercontent.com/hidge/astrbot_plugin_jiuhu_sign_images/raw/master/tarots"
        )

        # 运势卡资源
        self.fortune_dir: str = os.path.join(self.plugin_dir, "fortune")
        self.font_dir: str = os.path.join(self.fortune_dir, "font")
        self.background: str = os.path.join(self.fortune_dir, "background.json")
        self.fortune_text_file: str = os.path.join(self.fortune_dir, "fortune_text.json")

        # 运行时输出目录
        self.output_dir: str = os.path.join(self.data_dir, "output")
        self.avatar_dir: str = os.path.join(self.data_dir, "avatar")

    # ------------------------------------------------------------------
    # JSON 读写
    # ------------------------------------------------------------------

    async def read_json(self, src_path: str | None) -> dict[str, Any]:
        """读取 JSON 文件，返回字典；失败返回空字典。"""
        if not src_path:
            self.plugin_logger.log("读取 JSON 失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return {}
        if not os.path.exists(src_path):
            self.plugin_logger.log(f"读取 JSON 失败: 文件不存在 {src_path}", PluginLoggerLevel.ERROR)
            return {}

        try:
            async with aiofiles.open(src_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            self.plugin_logger.log(f"读取 JSON 失败: {src_path} | {e}", PluginLoggerLevel.ERROR)
            return {}

    async def save_json(self, data: dict[str, Any], save_path: str | None) -> str | None:
        """将字典保存为 JSON 文件。"""
        if not save_path:
            self.plugin_logger.log("保存 JSON 失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None

        try:
            async with aiofiles.open(save_path, "w", encoding="utf-8") as f:
                content = json.dumps(data, ensure_ascii=False, indent=4)
                await f.write(content)
                return save_path
        except Exception as e:
            self.plugin_logger.log(f"保存 JSON 失败: {save_path} | {e}", PluginLoggerLevel.ERROR)
            return None

    async def save_data(self, data: SignData) -> None:
        """持久化 SignData 对象到数据文件。"""
        try:
            async with aiofiles.open(self.signdata_file, "w", encoding="utf-8") as f:
                content = json.dumps(data.model_dump(), ensure_ascii=False, indent=4)
                await f.write(content)
        except Exception as e:
            self.plugin_logger.log(
                f"保存签到数据失败: {self.signdata_file} | {e}", PluginLoggerLevel.ERROR
            )

    # ------------------------------------------------------------------
    # 图片读写 & 下载
    # ------------------------------------------------------------------

    async def read_image(self, src_path: str | None) -> bytes | None:
        """读取图片文件，返回 bytes；失败返回 None。"""
        if not src_path:
            self.plugin_logger.log("读取图片失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        if not os.path.exists(src_path):
            self.plugin_logger.log(f"读取图片失败: 文件不存在 {src_path}", PluginLoggerLevel.ERROR)
            return None

        try:
            async with aiofiles.open(src_path, "rb") as f:
                return await f.read()
        except Exception as e:
            self.plugin_logger.log(f"读取图片失败: {src_path} | {e}", PluginLoggerLevel.ERROR)
            return None

    async def save_image(self, data: bytes, save_path: str | None) -> str | None:
        """将二进制数据保存为图片文件。"""
        if not save_path:
            self.plugin_logger.log("保存图片失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        if os.path.exists(save_path):
            self.plugin_logger.log(f"图片已存在，跳过保存: {save_path}", PluginLoggerLevel.WARNING)
            return save_path

        try:
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(data)
                return save_path
        except Exception as e:
            self.plugin_logger.log(f"保存图片失败: {save_path} | {e}", PluginLoggerLevel.ERROR)
            return None

    async def download_image(
        self,
        url: str | None,
        save_path: str | None,
        timeout: int = 30,
    ) -> str | None:
        """从 HTTP URL 下载图片并保存到本地，返回保存路径。"""
        if not url:
            self.plugin_logger.log("下载图片失败: URL 参数为 None", PluginLoggerLevel.ERROR)
            return None
        if not save_path:
            self.plugin_logger.log("下载图片失败: 保存路径参数为 None", PluginLoggerLevel.ERROR)
            return None

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    raw_data = await resp.read()
                    return await self.save_image(raw_data, save_path)
            except Exception as e:
                self.plugin_logger.log(f"下载图片失败: {url} | {e}", PluginLoggerLevel.ERROR)
                return None

    # ------------------------------------------------------------------
    # 文件清理
    # ------------------------------------------------------------------

    def get_files(self, folder: str | None) -> list[str]:
        """非递归列出指定文件夹下的所有文件路径。"""
        if not folder:
            self.plugin_logger.log("列出文件失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return []
        if not os.path.isdir(folder):
            self.plugin_logger.log(f"列出文件失败: 文件夹不存在 {folder}", PluginLoggerLevel.WARNING)
            return []

        return [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name))
        ]

    def schedule_delete(self, path: str | None, delay: float) -> asyncio.Task | None:
        """创建异步任务，在 delay 秒后删除指定路径的文件。"""
        if not path:
            self.plugin_logger.log("定时删除失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        if not os.path.exists(path):
            self.plugin_logger.log(f"定时删除跳过: 文件不存在 {path}", PluginLoggerLevel.WARNING)
            return None

        async def _delete_after_delay() -> None:
            await asyncio.sleep(delay)
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.plugin_logger.log(f"定时删除成功: {path}", PluginLoggerLevel.INFO)
                else:
                    self.plugin_logger.log(
                        f"定时删除跳过: 文件已不存在 {path}", PluginLoggerLevel.WARNING
                    )
            except Exception as e:
                self.plugin_logger.log(f"定时删除失败: {path} | {e}", PluginLoggerLevel.ERROR)

        return asyncio.create_task(_delete_after_delay())

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def generate_filename(self) -> str:
        """根据当前时间生成一个用于文件名的字符串（精确到秒）。"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
