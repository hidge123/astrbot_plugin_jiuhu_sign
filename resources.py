import asyncio
import json
import aiofiles
import aiohttp
import os
from typing import Optional, Dict, Any
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .plugin_logger import PluginLogger, PluginLoggerLevel
from astrbot.api import AstrBotConfig
from .sign_config import SignData


class ResourceManager:
    """资源管理器：负责插件的文件读写、下载等资源操作"""

    def __init__(self, name: str, config: AstrBotConfig):
        self.config: AstrBotConfig = config

        # 注册日志控制器
        if config.get("debug_mode"):
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        self.plugin_dir: str = os.path.join(get_astrbot_data_path(), "plugins", name)
        self.data_dir: str = os.path.join(get_astrbot_data_path(), "plugin_data", name)
        self.data_file: str = os.path.join(self.data_dir, "sign_data.json")
        self.tarots_dir: str = os.path.join(self.plugin_dir, "tarots")
        self.tarots_meaning_file: str = os.path.join(self.tarots_dir, "tarot_meanings.json")

    async def save_image(self, src: bytes, save_path: str) -> None:
        """保存图片到指定路径"""
        if os.path.exists(save_path):
            self.plugin_logger.log(f"文件已存在,path: {save_path}", PluginLoggerLevel.ERROR)
            return

        try:
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(src)
        except Exception as e:
            self.plugin_logger.log(f"{e}", PluginLoggerLevel.ERROR)

    async def save_json(self, src: Dict[str, Any], save_path: str) -> None:
        """将字典数据保存为 JSON 文件"""
        try:
            async with aiofiles.open(save_path, "w", encoding="utf-8") as f:
                content = json.dumps(src, ensure_ascii=False, indent=4)
                await f.write(content)
        except Exception as e:
            self.plugin_logger.log(f"{e}", PluginLoggerLevel.ERROR)

    async def save_data(self, src: SignData) -> None:
        """保存 SignData 对象到 data_file"""
        try:
            async with aiofiles.open(self.data_file, "w", encoding="utf-8") as f:
                content = json.dumps(src.model_dump(), ensure_ascii=False, indent=4)
                await f.write(content)
        except Exception as e:
            self.plugin_logger.log(f"{e}", PluginLoggerLevel.ERROR)

    async def download_image(self, url: str, save_path: str) -> None:
        """从 URL 下载图片并保存"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    await self.save_image(await resp.read(), save_path)
            except Exception as e:
                self.plugin_logger.log(f"{e}", PluginLoggerLevel.ERROR)

    async def read_image(self, src_path: str) -> Optional[bytes]:
        """读取图片文件，返回 bytes 或 None"""
        if os.path.exists(src_path):
            try:
                async with aiofiles.open(src_path, "rb") as f:
                    return await f.read()
            except Exception as e:
                self.plugin_logger.log(f"{e}", PluginLoggerLevel.ERROR)

        else:
            self.plugin_logger.log(f"文件不存在,path: {src_path}", PluginLoggerLevel.ERROR)
            return None

    async def read_json(self, src_path: str) -> Dict[str, Any]:
        """读取 JSON 文件，返回字典，失败返回空字典"""
        if not os.path.exists(src_path):
            self.plugin_logger.log(f"文件不存在,path: {src_path}", PluginLoggerLevel.ERROR)
            return {}

        try:
            async with aiofiles.open(src_path, 'r', encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            self.plugin_logger.log(f"读取json文件{src_path}时发生错误: {e}")
            return {}
