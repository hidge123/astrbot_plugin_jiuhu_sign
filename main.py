from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from random import randint
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
import json
import os

from models import SignData


class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 数据文件存放在 get_astrbot_data_path() 返回的 data 目录下
        self.data_file = os.path.join(
            get_astrbot_data_path(), "plugin_data", self.name
        )
        self.user_data: SignData = SignData()

    async def initialize(self):
        """初始化插件，加载或创建用户数据文件"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 使用 Pydantic 验证数据格式
                self.user_data = SignData.model_validate(data)
                logger.info(f"已加载签到数据，共 {len(self.user_data.users)} 个用户")
            except Exception as e:
                logger.warning(f"签到数据文件格式错误，将重新创建: {e}")
                self.user_data = SignData()
                self._save_data()
        else:
            self._save_data()
            logger.info("已创建签到数据文件")

    def _save_data(self):
        """保存用户数据到文件"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.user_data.model_dump(), f, ensure_ascii=False, indent=2)

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    @filter.command("sign")
    async def sign_handler(self, event: AstrMessageEvent):
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 获取或初始化用户的 credit
        if user_id not in self.user_data.users:
            from models import UserData
            self.user_data.users[user_id] = UserData(credit=0)

        # 签到获得 1-5 个小饼干
        gained = randint(1, 5)
        self.user_data.users[user_id].credit += gained
        current_credit = self.user_data.users[user_id].credit
        self._save_data()

        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"{user_name}签到成功,获得{gained}个小饼干!\n当前共有 {current_credit} 个小饼干。")
        ]

        await event.send(message_result)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if os.path.exists(self.data_file):
            os.remove(self.data_file)
            logger.info("已删除签到数据文件")
