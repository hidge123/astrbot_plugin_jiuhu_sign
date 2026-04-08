from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
import random
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
import json
import os
from enum import Enum
from .sign_config import SignData

class PluginLoggerLevel(Enum):
    """用于插件控制日志输出的等级"""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4

class TarotType(Enum):
    """塔罗牌的类别"""
    


class PluginLogger:
    """用于插件控制日志输出的类"""

    def __init__(self, level: PluginLoggerLevel) -> None:
        self.level = level

    def _should_log(self, level: PluginLoggerLevel) -> bool:
        return self.level.value <= level.value

    def log(self, msg: str, level: PluginLoggerLevel = PluginLoggerLevel.INFO) -> None:
        if self._should_log(level):
            if level == PluginLoggerLevel.DEBUG:
                logger.debug(msg)
            elif level == PluginLoggerLevel.INFO:
                logger.info(msg)
            elif level == PluginLoggerLevel.WARNING:
                logger.warning(msg)
            elif level == PluginLoggerLevel.ERROR:
                logger.error(msg)


class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        if config.get("debug_mode"):
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        # 数据目录存放在 get_astrbot_data_path() 返回的 data 目录下的插件名文件夹中
        self.data_dir = os.path.join(
            get_astrbot_data_path(), "plugin_data", self.name
        )
        self.data_file = os.path.join(self.data_dir, "sign_data.json")
        self.user_data: SignData = SignData()

    async def initialize(self):
        """初始化插件，加载或创建用户数据文件"""
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 使用 Pydantic 验证数据格式
                self.user_data = SignData.model_validate(data)
                self.plugin_logger.log(f"已加载签到数据，共 {len(self.user_data.users)} 个用户", PluginLoggerLevel.INFO)
            except Exception as e:
                self.plugin_logger.log(f"签到数据文件格式错误，将重新创建: {e}", PluginLoggerLevel.WARNING)
                self.user_data = SignData()
                self._save_data()
        else:
            self._save_data()
            self.plugin_logger.log("已创建签到数据文件", PluginLoggerLevel.INFO)

    def _save_data(self):
        """保存用户数据到文件"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.user_data.model_dump(), f, ensure_ascii=False, indent=2)

    @filter.command("sign")
    async def sign_handler(self, event: AstrMessageEvent):
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 获取或初始化用户的 credit
        if user_id not in self.user_data.users:
            from .sign_config import UserData
            self.user_data.users[user_id] = UserData(credit=0)

        # 签到获得 1-5 个小饼干
        gained = random.randint(1, 5)
        self.user_data.users[user_id].credit += gained
        current_credit = self.user_data.users[user_id].credit
        self._save_data()

        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"{user_name}签到成功,获得{gained}个小饼干!\n当前共有 {current_credit} 个小饼干。")
        ]

        await event.send(message_result)

    @filter.command("tarot")
    async def tarot_handler(self, event: AstrMessageEvent):
        user_id = event.get_session_id()
        user_name = event.get_sender_name()



    async def terminate(self):
        pass