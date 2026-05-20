import asyncio
import json
import aiofiles
import aiohttp
import os
from datetime import datetime
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
        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        # 此插件所在文件夹
        self.plugin_dir = os.path.join(get_astrbot_data_path(), "plugins", name)
        # 数据目录存放在 get_astrbot_data_path() 返回的 data 目录下的插件名文件夹中
        self.data_dir = os.path.join(get_astrbot_data_path(), "plugin_data", name)
        self.signdata_file = os.path.join(self.data_dir, "sign_data.json")
        # 塔罗牌功能需要文件路径
        self.tarots_dir = os.path.join(self.plugin_dir, "tarots")
        self.tarots_meaning_file = os.path.join(self.tarots_dir, "tarot_meanings.json")
        # 塔罗牌图片 CDN 地址
        self.tarots_cdn_base = "https://cdn.jsdelivr.net/gh/hidge123/astrbot_plugin_jiuhu_sign_images@main/tarots"
        # 今日运势相关功能所需文件路径
        self.fortune_dir = os.path.join(self.plugin_dir, "fortune")
        self.font_dir = os.path.join(self.fortune_dir, "font")
        self.background = os.path.join(self.fortune_dir, "background.json")
        self.output_dir = os.path.join(self.data_dir, "output")
        self.avatar_dir = os.path.join(self.data_dir, "avatar")
        self.fortune_text_file = os.path.join(self.fortune_dir, "fortune_text.json")

    async def save_image(self, src: bytes, save_path: str | None) -> Optional[str]:
        """保存图片到指定路径"""
        if not save_path:
            self.plugin_logger.log("保存图片失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        if os.path.exists(save_path):
            self.plugin_logger.log(f"图片已存在，跳过保存: {save_path}", PluginLoggerLevel.WARNING)
            return save_path

        try:
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(src)
                return save_path
        except Exception as e:
            self.plugin_logger.log(f"保存图片失败: {save_path} | {e}", PluginLoggerLevel.ERROR)
            return None

    async def save_json(self, src: Dict[str, Any], save_path: str | None) -> Optional[str]:
        """将字典数据保存为 JSON 文件"""
        if not save_path:
            self.plugin_logger.log("保存JSON失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        try:
            async with aiofiles.open(save_path, "w", encoding="utf-8") as f:
                content = json.dumps(src, ensure_ascii=False, indent=4)
                await f.write(content)
                return save_path
        except Exception as e:
            self.plugin_logger.log(f"保存JSON失败: {save_path} | {e}", PluginLoggerLevel.ERROR)
            return None

    async def save_data(self, src: SignData) -> None:
        """保存 SignData 对象到 data_file"""
        try:
            async with aiofiles.open(self.signdata_file, "w", encoding="utf-8") as f:
                content = json.dumps(src.model_dump(), ensure_ascii=False, indent=4)
                await f.write(content)
        except Exception as e:
            self.plugin_logger.log(f"保存签到数据失败: {self.signdata_file} | {e}", PluginLoggerLevel.ERROR)

    async def download_image(
            self, url: str | None,
            save_path: str | None,
            timeout: int = 30
        ) -> Optional[str]:
        """从 URL 下载图片并保存"""
        if not url:
            self.plugin_logger.log("下载图片失败: URL 参数为 None", PluginLoggerLevel.ERROR)
            return None
        if not save_path:
            self.plugin_logger.log("下载图片失败: 保存路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    return await self.save_image(await resp.read(), save_path)
            except Exception as e:
                self.plugin_logger.log(f"下载图片失败: {url} | {e}", PluginLoggerLevel.ERROR)
                return None

    async def read_image(self, src_path: str | None) -> Optional[bytes]:
        """读取图片文件，返回 bytes 或 None"""
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

    async def read_json(self, src_path: str | None) -> Dict[str, Any]:
        """读取 JSON 文件，返回字典，失败返回空字典"""
        if not src_path:
            self.plugin_logger.log("读取JSON失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return {}
        if not os.path.exists(src_path):
            self.plugin_logger.log(f"读取JSON失败: 文件不存在 {src_path}", PluginLoggerLevel.ERROR)
            return {}

        try:
            async with aiofiles.open(src_path, 'r', encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            self.plugin_logger.log(f"读取JSON失败: {src_path} | {e}", PluginLoggerLevel.ERROR)
            return {}

    def get_files(self, folder: str | None) -> list[str]:
        """不递归的列出所给文件夹下的所有文件"""
        if not folder:
            self.plugin_logger.log("列出文件失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return []
        if not os.path.isdir(folder):
            self.plugin_logger.log(f"列出文件失败: 文件夹不存在 {folder}", PluginLoggerLevel.WARNING)
            return []
        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f))
        ]

        return files

    def schedule_delete(self, path: str | None, delay: float) -> Optional[asyncio.Task]:
        """定时删除文件，经过 delay 秒后删除指定路径的文件"""
        if not path:
            self.plugin_logger.log("定时删除失败: 路径参数为 None", PluginLoggerLevel.ERROR)
            return None
        if not os.path.exists(path):
            self.plugin_logger.log(f"定时删除跳过: 文件不存在 {path}", PluginLoggerLevel.WARNING)
            return None

        async def _delete():
            await asyncio.sleep(delay)
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.plugin_logger.log(f"定时删除成功: {path}", PluginLoggerLevel.INFO)
                else:
                    self.plugin_logger.log(f"定时删除跳过: 文件已不存在 {path}", PluginLoggerLevel.WARNING)
            except Exception as e:
                self.plugin_logger.log(f"定时删除失败: {path} | {e}", PluginLoggerLevel.ERROR)

        return asyncio.create_task(_delete())

    def generate_filename(self) -> str:
        """依据当前时间生成一段用于文件名的字符串"""
        now = datetime.now()
        formatted = now.strftime("%Y%m%d_%H%M%S")

        return formatted
