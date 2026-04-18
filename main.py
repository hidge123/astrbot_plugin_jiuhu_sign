from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
import random
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
import json
import os
import asyncio
import aiofiles
from enum import Enum
from .sign_config import SignData
from .plugin_logger import PluginLogger, PluginLoggerLevel
from .resources import ResourceManager


class TarotType(Enum):
    """塔罗牌的类别"""
    FOOL = "the_fool"
    MAGICIAN = "the_magician"
    HIGH_PRIESTESS = "the_high_priestess"
    EMPRESS = "the_empress"
    EMPEROR = "the_emperor"
    HIEROPHANT = "the_hierophant"
    LOVERS = "the_lovers"
    CHARIOT = "the_chariot"
    STRENGTH = "strength"
    HERMIT = "the_hermit"
    WHEEL_OF_FORTUNE = "wheel_of_fortune"
    JUSTICE = "justice"
    HANGED_MAN = "the_hanged_man"
    DEATH = "death"
    TEMPERANCE = "temperance"
    DEVIL = "the_devil"
    TOWER = "the_tower"
    STAR = "the_star"
    MOON = "the_moon"
    SUN = "the_sun"
    JUDGEMENT = "judgement"
    WORLD = "the_world"



class JiuHuSign(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        if config.get("debug_mode"):
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        self.user_data: SignData = SignData()   # 用于存储用户签到相关数据
        self.tarots_meaning = {}   # 用于存储塔罗牌的含义
        self.infinite_credit = bool(config.get("infinite_credit"))    # 存储无限饼干模式的状态

        # 此插件所在文件夹
        self.plugin_dir = os.path.join(get_astrbot_data_path(), "plugins", self.name)
        # 数据目录存放在 get_astrbot_data_path() 返回的 data 目录下的插件名文件夹中
        self.data_dir = os.path.join(get_astrbot_data_path(), "plugin_data", self.name)
        self.data_file = os.path.join(self.data_dir, "sign_data.json")
        # 塔罗牌功能需要文件的存放位置
        self.tarots_dir = os.path.join(self.plugin_dir, "tarots")
        self.tarots_meaning_file = os.path.join(self.tarots_dir, "tarot_meanings.json")
        
        # 注册资源管理器
        self.resource_manager = ResourceManager(self.name, config)

        # 存储塔罗牌类型对应的图片的文件名
        self.tarot_type = [
            TarotType.FOOL,
            TarotType.MAGICIAN,
            TarotType.HIGH_PRIESTESS,
            TarotType.EMPRESS,
            TarotType.EMPEROR,
            TarotType.HIEROPHANT,
            TarotType.LOVERS,
            TarotType.CHARIOT,
            TarotType.STRENGTH,
            TarotType.HERMIT,
            TarotType.WHEEL_OF_FORTUNE,
            TarotType.JUSTICE,
            TarotType.HANGED_MAN,
            TarotType.DEATH,
            TarotType.TEMPERANCE,
            TarotType.DEVIL,
            TarotType.TOWER,
            TarotType.STAR,
            TarotType.MOON,
            TarotType.SUN,
            TarotType.JUDGEMENT,
            TarotType.WORLD,
        ]

    async def initialize(self):
        """初始化插件，加载或创建用户数据文件"""
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.data_file):
            try:
                data = await self.resource_manager.read_json(self.data_file)
                # 使用 Pydantic 验证数据格式
                self.user_data = SignData.model_validate(data)
                self.plugin_logger.log(f"已加载签到数据，共 {len(self.user_data.users)} 个用户", PluginLoggerLevel.INFO)
            except Exception as e:
                self.plugin_logger.log(f"签到数据文件格式错误，将重新创建: {e}", PluginLoggerLevel.WARNING)
                self.user_data = SignData()
                await self.resource_manager.save_json(self.user_data.model_dump(), self.data_file)
        else:
            await self._save_data()
            self.plugin_logger.log("已创建签到数据文件", PluginLoggerLevel.INFO)

        if os.path.exists(self.tarots_meaning_file):
            self.tarots_meaning = await self.resource_manager.read_json(self.tarots_meaning_file)
        else:
            self.plugin_logger.log("文件tarot_meaning.json缺失", PluginLoggerLevel.ERROR)

    async def _save_data(self):
        """保存用户数据到文件（异步，使用线程池避免阻塞）"""
        await self.resource_manager.save_data(self.user_data)

    def _init_user_credit(self, user_id):
        """获取或初始化用户的 credit"""
        if user_id not in self.user_data.users:
            from .sign_config import UserData
            self.user_data.users[user_id] = UserData(credit=0)

    @filter.command("sign")
    async def sign_handler(self, event: AstrMessageEvent):
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 确保用户的credit数据存在
        self._init_user_credit(user_id)

        # 签到获得 1-5 个小饼干
        gained = random.randint(1, 5)
        self.user_data.users[user_id].credit += gained

        if self.infinite_credit:
            current_credit = "infinite"
        else:
            current_credit = self.user_data.users[user_id].credit
        await self._save_data()

        # 构建返回消息
        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"{user_name}签到成功,获得{gained}个小饼干!\n当前共有 {current_credit} 个小饼干。")
        ]

        await event.send(message_result)

    @filter.command("tarot")
    async def tarot_handler(self, event: AstrMessageEvent):
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 获取塔罗牌的图片路径和占卜结果
        tarot = random.choice(self.tarot_type).value
        is_reversed = random.randint(0, 1)

        if is_reversed:
            meaning = self.tarots_meaning.get(f"{tarot}_r")
            image_path = os.path.join(self.tarots_dir, "image", f"{tarot}_r.png")
        else:
            meaning = self.tarots_meaning.get(f"{tarot}")
            image_path = os.path.join(self.tarots_dir, "image", f"{tarot}.png")

        # 确保用户的credit数据存在
        self._init_user_credit(user_id)

        # 构建返回消息
        message_result = event.make_result()
        if (self.user_data.users[user_id].credit <= 0 and not self.infinite_credit):
            message_result.chain = [
                Comp.Plain(f"小饼干不足咕,抽不了啦\n(小提示: 可以试着对酒狐说'/sign'来获取小饼干哦)"),
            ]
            
        elif os.path.exists(image_path):
            if self.infinite_credit:
                current_credit = "infinite"
            else:
                self.user_data.users[user_id].credit -= 1
                current_credit = self.user_data.users[user_id].credit

            message_result.chain = [
                Comp.Plain(f"让狐狐算算啊, {user_name}抽到的是"),
                Comp.Image.fromFileSystem(image_path),
                Comp.Plain(f"这张牌对应的结果是: {meaning}\n本次服务耗费1个小饼干, {user_name}你还剩{current_credit}个哦"),
            ]

            await self._save_data()

        else:
            self.plugin_logger.log(f"{image_path} 对应的图片不存在或存放位置不正确", PluginLoggerLevel.WARNING)

            message_result.chain = [
                Comp.Plain(f"让狐狐算算啊, {user_name}抽到的是\n哎!奇怪, 狐狸什么都没有抽到诶"),
            ]

        await event.send(message_result)

    @filter.command("fortune")
    async def fortune_handler(self, event: AstrMessageEvent):
        pass

    async def terminate(self):
        pass