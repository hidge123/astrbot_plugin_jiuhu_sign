from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
import random
import os
import asyncio
from enum import Enum
from PIL import Image
from .sign_config import SignData
from .plugin_logger import PluginLogger, PluginLoggerLevel
from .resources import ResourceManager
from .generator import FortuneCardGenerator


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

class FortuneType(Enum):
    """运势的等级"""
    DA_JI = "大吉"
    ZHONG_JI = "中吉"
    XIAO_JI = "小吉"
    MO_JI = "末吉"
    PING = "平"
    XIONG = "凶"
    DA_XIONG = "大凶"


class JiuHuSign(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        self.user_data: SignData = SignData()   # 用于存储用户签到相关数据
        self.tarots_meaning = {}   # 用于存储塔罗牌的含义
        self.fortune_text = {}  # 用于存储宜忌事项
        self.background_urls: list[str] = []   # 用于存储运势卡背景图的url
        
        self.infinite_credit = config["sign_config"]["infinite_credit"]    # 存储无限饼干模式的状态
        self.avatar_delay_time = config["fortune_config"]["delay_time"]["avatar"]   # 头像缓存时间
        self.output_delay_time = config["fortune_config"]["delay_time"]["output"]   # 运势卡缓存时间

        _delay_min = 60
        _delay_max = 3600
        if not (_delay_min <= self.avatar_delay_time <= _delay_max):
            self.plugin_logger.log(f"avatar_delay_time {self.avatar_delay_time} 超出范围，已调整为 {_delay_min if self.avatar_delay_time < _delay_min else _delay_max}")
            self.avatar_delay_time = max(_delay_min, min(self.avatar_delay_time, _delay_max))
        if not (_delay_min <= self.output_delay_time <= _delay_max):
            self.plugin_logger.log(f"output_delay_time {self.output_delay_time} 超出范围，已调整为 {_delay_min if self.output_delay_time < _delay_min else _delay_max}")
            self.output_delay_time = max(_delay_min, min(self.output_delay_time, _delay_max))

        # 注册资源管理器
        self.resource_manager = ResourceManager(self.name, config)
        # 注册吉凶卡生成器
        self.generator = FortuneCardGenerator(self.name, config)

        # 此插件所在文件夹
        self.plugin_dir = self.resource_manager.plugin_dir
        # 数据目录存放在 get_astrbot_data_path() 返回的 data 目录下的插件名文件夹中
        self.data_dir = self.resource_manager.data_dir
        self.signdata_file = self.resource_manager.signdata_file
        # 塔罗牌功能需要文件的路径
        self.tarots_dir = self.resource_manager.tarots_dir
        self.tarots_meaning_file = self.resource_manager.tarots_meaning_file
        # 今日运势相关功能所需文件的路径
        self.fortune_dir = self.resource_manager.fortune_dir
        self.background = self.resource_manager.background
        self.output_dir = self.resource_manager.output_dir
        self.avatar_dir = self.resource_manager.avatar_dir
        self.fortune_text_file = self.resource_manager.fortune_text_file

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
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)

        if os.path.exists(self.signdata_file):
            try:
                data = await self.resource_manager.read_json(self.signdata_file)
                # 使用 Pydantic 验证数据格式
                self.user_data = SignData.model_validate(data)
                self.plugin_logger.log(
                    f"已加载签到数据, 共{len(self.user_data.groups)}个群组, 共{sum(len(v.users) for k, v in self.user_data.groups.items())}个用户"
                )
            except Exception as e:
                self.plugin_logger.log(f"签到数据文件格式错误，将重新创建: {e}", PluginLoggerLevel.WARNING)
                self.user_data = SignData()
                await self.resource_manager.save_json(self.user_data.model_dump(), self.signdata_file)
        else:
            await self._save_data()
            self.plugin_logger.log("已创建签到数据文件", PluginLoggerLevel.INFO)

        if os.path.exists(self.tarots_meaning_file):
            self.tarots_meaning = await self.resource_manager.read_json(self.tarots_meaning_file)
        else:
            self.plugin_logger.log("文件tarot_meaning.json缺失", PluginLoggerLevel.ERROR)

        if os.path.exists(self.fortune_text_file):
            self.fortune_text = await self.resource_manager.read_json(self.fortune_text_file)
        else:
            self.plugin_logger.log("文件fortune_text.json缺失", PluginLoggerLevel.ERROR)

        if os.path.exists(self.background):
            background_json = await self.resource_manager.read_json(self.background)
            self.background_urls = background_json.get("urls", [])
            if not self.background_urls:
                self.plugin_logger.log("background.json 中 urls 为空或不存在", PluginLoggerLevel.WARNING)
        else:
            self.plugin_logger.log("文件background.json缺失", PluginLoggerLevel.ERROR)


    async def _save_data(self):
        """保存用户数据到文件（异步，使用线程池避免阻塞）"""
        await self.resource_manager.save_data(self.user_data)

    def _init_user(self, group_id, user_id):
        """确保用户数据存在，不存在则初始化"""
        if group_id not in self.user_data.groups:
            from .sign_config import GroupData
            self.user_data.groups[group_id] = GroupData(users={})

        if user_id not in self.user_data.groups[group_id].users:
            from .sign_config import UserData
            self.user_data.groups[group_id].users[user_id] = UserData()

    def _get_fortune(self) -> FortuneType:
        """根据配置的概率获取运势结果"""
        max_val = 10
        min_val = 1

        # 从配置中读取每个运势等级的概率
        good = self.config["fortune_config"]["probability"]["ji"]
        normal = self.config["fortune_config"]["probability"]["ping"]
        bad = self.config["fortune_config"]["probability"]["xiong"]

        # 检查每个运势的概率是否超出范围
        if (good < min_val or good > max_val):
            good = 5
            self.plugin_logger.log("吉的概率超出范围")
        if (normal < min_val or normal > max_val):
            normal = 10
            self.plugin_logger.log("平的概率超出范围")
        if (bad < min_val or bad > max_val):
            bad = 5
            self.plugin_logger.log("凶的概率超出范围")

        rand = random.randint(1, good + normal + bad)
        if (rand <= bad):
            candidate = [FortuneType.XIONG, FortuneType.DA_XIONG]
            fortune = random.choice(candidate)
        elif (rand <= bad + normal):
            candidate = [FortuneType.MO_JI, FortuneType.PING]
            fortune = random.choice(candidate)
        else:
            candidate = [FortuneType.DA_JI, FortuneType.ZHONG_JI, FortuneType.XIAO_JI]
            fortune = random.choice(candidate)

        return fortune

    @filter.command("sign")
    async def sign_handler(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 确保用户的credit数据存在
        self._init_user(group_id, user_id)

        # 检查今日是否已签到
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        last_date = self.user_data.groups[group_id].users[user_id].last_sign_date
        if last_date == today:
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(f"{user_name} 今天已经签到过了哦，一天只能领一次小饼干 0v0\n明天再来找我玩吧~"),
            ]
            await event.send(message_result)
            return

        # 签到获得 1-5 个小饼干
        gained = random.randint(1, 5)
        self.user_data.groups[group_id].users[user_id].credit += gained
        self.user_data.groups[group_id].users[user_id].last_sign_date = today

        if self.infinite_credit:
            current_credit = "infinite"
        else:
            current_credit = self.user_data.groups[group_id].users[user_id].credit
        await self._save_data()

        # 构建返回消息
        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"唔...闻到香香的味道了~ {user_name} 签到拿到 {gained} 个小饼干啦！放在我这里帮你保管好不好呀 0v0\n你现在一共攒了 {current_credit} 个小饼干了，分我吃一口嘛~")
        ]

        await event.send(message_result)

    @filter.command("tarot")
    async def tarot_handler(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 确保用户的credit数据存在
        self._init_user(group_id, user_id)

        # 检查小饼干是否足够
        if self.user_data.groups[group_id].users[user_id].credit <= 0 and not self.infinite_credit:
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(f"诶...你的小饼干不够了呀，这点零食还想骗我干活 QAQ？\n快去发个 '/sign' 领点小饼干再来找我玩嘛~"),
            ]
            await event.send(message_result)
            return

        # 抽取塔罗牌
        tarot = random.choice(self.tarot_type).value
        is_reversed = random.randint(0, 1)

        if is_reversed:
            meaning = self.tarots_meaning.get(f"{tarot}_r")
        else:
            meaning = self.tarots_meaning.get(f"{tarot}")

        # 从 CDN 下载正向牌图片
        image_url = f"{self.resource_manager.tarots_cdn_base}/{tarot}.png"
        download_filename = f"tarot_{tarot}_{self.resource_manager.generate_filename()}.png"
        download_path = os.path.join(self.output_dir, download_filename)
        downloaded = await self.resource_manager.download_image(image_url, download_path)

        if downloaded is None:
            self.plugin_logger.log(f"从 CDN 下载塔罗牌失败: {image_url}", PluginLoggerLevel.WARNING)
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(f"唔...让狐狐帮 {user_name} 摸摸看是什么~\n诶？居然是空的！绝对不是我弄坏了哦 QAQ，是真的什么都没有捞到 www"),
            ]
            await event.send(message_result)
            return

        # 翻转牌：用 Pillow 旋转下载的正向图片生成临时文件
        image_path = ""
        if is_reversed:
            img = Image.open(downloaded)
            rotated = img.rotate(180)
            output_filename = f"{tarot}_reversed_{self.resource_manager.generate_filename()}.png"
            image_path = os.path.join(self.output_dir, output_filename)
            rotated.save(image_path)
        else:
            image_path = downloaded

        # 扣除小饼干
        if not self.infinite_credit:
            self.user_data.groups[group_id].users[user_id].credit -= 1
            current_credit = self.user_data.groups[group_id].users[user_id].credit
        else:
            current_credit = "infinite"

        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"唔...让我看看 {user_name} 抽到了什么好东西~"),
            Comp.Image.fromFileSystem(image_path),
            Comp.Plain(f"结果出来啦：{meaning} www\n作为报酬，这1个小饼干我就嗷呜一口吃掉啦！你现在还剩 {current_credit} 个小饼干哦 0v0"),
        ]

        await self._save_data()
        await event.send(message_result)

        # 发送完毕后清理临时文件
        self.resource_manager.schedule_delete(image_path, 0)
        if is_reversed:
            self.resource_manager.schedule_delete(downloaded, 0)

    @filter.command("fortune")
    async def fortune_handler(self, event: AstrMessageEvent):
        # 获取用户基本信息
        user_id = event.get_session_id()
        user_name = event.get_sender_name()

        # 下载运势卡背景图片
        if not self.background_urls:
            self.plugin_logger.log("背景图片 URL 列表为空", PluginLoggerLevel.WARNING)
            message_result = event.make_result()
            message_result.chain = [Comp.Plain(f"呜哇，看运势的牌牌好像卡住了 0v0！绝对不是因为狐狐觉得算命太麻烦才弄坏的哦 QAQ，总之现在暂时算不了啦~")]
            await event.send(message_result)
            return

        image_url = random.choice(self.background_urls)
        download_filename = f"fortune_background_{self.resource_manager.generate_filename()}.png"
        download_path = os.path.join(self.output_dir, download_filename)
        downloaded = await self.resource_manager.download_image(image_url, download_path)

        # 下载用户头像并缓存
        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        avatar_path = os.path.join(self.avatar_dir, f"{user_id}.png")
        avatar_path = await self.resource_manager.download_image(avatar_url, avatar_path)

        # 根据概率选择运势文本
        fortune = self._get_fortune()
        YI = self.fortune_text["yi"]
        JI = self.fortune_text["ji"]

        title = fortune.value
        yi_text = ""
        ji_text = ""

        if (fortune is FortuneType.DA_JI):
            yi_text = "诸事皆宜"
            ji_text = "无"
        elif (fortune is FortuneType.ZHONG_JI or fortune is FortuneType.XIAO_JI):
            yi_choices = random.sample(range(len(YI)), 3)
            for i in yi_choices:
                yi_text += YI[i] + " "

            ji_choices = random.sample(range(len(JI)), 1)
            for i in ji_choices:
                ji_text += JI[i] + " "
        elif (fortune is FortuneType.MO_JI or fortune is FortuneType.PING):
            yi_choices = random.sample(range(len(YI)), 2)
            for i in yi_choices:
                yi_text += YI[i] + " "

            ji_choices = random.sample(range(len(JI)), 2)
            for i in ji_choices:
                ji_text += JI[i] + " "
        else:
            yi_choices = random.sample(range(len(YI)), 1)
            for i in yi_choices:
                yi_text += YI[i] + " "

            ji_choices = random.sample(range(len(JI)), 3)
            for i in ji_choices:
                ji_text += JI[i] + " " 

        # 生成运势卡
        output_path = await self.generator.generate(
            input_path=downloaded,
            title=title,
            yi_text=yi_text.strip(),
            ji_text=ji_text.strip(),
            avatar_path=avatar_path
        )

        if output_path is None:
            self.plugin_logger.log("生成运势卡时出现错误", PluginLoggerLevel.ERROR)
            message_result = event.make_result()
            message_result.chain = [Comp.Plain(f"呜哇，看运势的牌牌好像卡住了 0v0！绝对不是因为狐狐觉得算命太麻烦才弄坏的哦 QAQ，总之现在暂时算不了啦~")]
            await event.send(message_result)
            return 

        # 构建返回消息
        message_result = event.make_result()
        message_result.chain = [
            Comp.Image.fromFileSystem(output_path)
        ]  

        await event.send(message_result)

        # 延时删除生成的卡片、背景原图和缓存的头像图片
        self.resource_manager.schedule_delete(output_path, self.output_delay_time)
        self.resource_manager.schedule_delete(downloaded, 0)
        self.resource_manager.schedule_delete(avatar_path, self.avatar_delay_time)

    async def terminate(self):
        # 删除缓存的用户头像和运势卡片
        tasks = []
        for f_path in self.resource_manager.get_files(self.avatar_dir):
            task = self.resource_manager.schedule_delete(f_path, 0)
            if task:
                tasks.append(task)

        for f_path in self.resource_manager.get_files(self.output_dir):
            task = self.resource_manager.schedule_delete(f_path, 0)
            if task:
                tasks.append(task)

        # 阻塞直到所有删除任务完成
        if tasks:
            await asyncio.gather(*tasks)
