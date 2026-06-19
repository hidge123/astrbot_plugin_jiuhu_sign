import asyncio
import os
import random
from datetime import datetime
from enum import Enum

from PIL import Image

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star
from astrbot.core.exceptions import ProviderNotFoundError

from .generator import FortuneCardGenerator
from .plugin_logger import PluginLogger, PluginLoggerLevel
from .resources import ResourceManager
from .sign_config import GroupData, SignData, UserData


# ---------------------------------------------------------------------------
# 枚举定义
# ---------------------------------------------------------------------------

class TarotType(Enum):
    """塔罗牌类别"""
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
    """运势等级"""
    DA_JI = "大吉"
    ZHONG_JI = "中吉"
    XIAO_JI = "小吉"
    MO_JI = "末吉"
    PING = "平"
    XIONG = "凶"
    DA_XIONG = "大凶"


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 头像/输出缓存时间范围（秒）
DELAY_MIN = 60
DELAY_MAX = 3600

# 每次抽塔罗牌消耗的小饼干数
COST_PER_TAROT_CARD = 1

# 运势概率范围
PROBABILITY_MIN = 1
PROBABILITY_MAX = 10

# 签到每次获得的小饼干范围
SIGN_CREDIT_MIN = 1
SIGN_CREDIT_MAX = 5

# 塔罗牌抽取数量范围
TAROT_CARDS_MIN = 1
TAROT_CARDS_MAX = 3

# 默认概率（配置值越界时回退）
DEFAULT_JI_PROB = 5
DEFAULT_PING_PROB = 10
DEFAULT_XIONG_PROB = 5


# ---------------------------------------------------------------------------
# 插件主类
# ---------------------------------------------------------------------------

class JiuHuSign(Star):
    """酒狐主题签到插件：每日签到、塔罗牌占卜、今日运势卡生成。"""

    # 所有塔罗牌类型列表，供随机抽取使用
    ALL_TAROT_CARDS: list[TarotType] = list(TarotType)

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config: AstrBotConfig = config

        # ---- 日志 ----
        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        # ---- 用户数据 ----
        self.user_data: SignData = SignData()

        # ---- 资源数据（由 initialize() 从文件加载）----
        self.tarots_meaning: dict[str, str] = {}
        self.fortune_text: dict[str, list[str]] = {}
        self.background_urls: list[str] = []

        # ---- 配置项 ----
        self.infinite_credit: bool = config["sign_config"]["infinite_credit"]
        self.avatar_delay_time: int = config["fortune_config"]["delay_time"]["avatar"]
        self.output_delay_time: int = config["fortune_config"]["delay_time"]["output"]

        # 校验并修正缓存时间范围
        self.avatar_delay_time = self._clamp_delay_with_log(self.avatar_delay_time, "avatar_delay_time")
        self.output_delay_time = self._clamp_delay_with_log(self.output_delay_time, "output_delay_time")

        # ---- 资源管理器和生成器 ----
        self.resource_manager = ResourceManager(self.name, config)
        self.generator = FortuneCardGenerator(self.name, config)

        # ---- 目录与文件路径 ----
        self.plugin_dir: str = self.resource_manager.plugin_dir
        self.data_dir: str = self.resource_manager.data_dir
        self.signdata_file: str = self.resource_manager.signdata_file

        self.tarots_dir: str = self.resource_manager.tarots_dir
        self.tarots_meaning_file: str = self.resource_manager.tarots_meaning_file

        self.fortune_dir: str = self.resource_manager.fortune_dir
        self.background: str = self.resource_manager.background
        self.output_dir: str = self.resource_manager.output_dir
        self.avatar_dir: str = self.resource_manager.avatar_dir
        self.fortune_text_file: str = self.resource_manager.fortune_text_file

    # ------------------------------------------------------------------
    # 初始化 & 数据持久化
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """初始化插件：加载或创建用户数据及资源文件。"""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)

        # 加载签到数据
        if os.path.exists(self.signdata_file):
            try:
                data = await self.resource_manager.read_json(self.signdata_file)
                self.user_data = SignData.model_validate(data)
                self.plugin_logger.log(
                    f"已加载签到数据, 共{len(self.user_data.groups)}个群组, "
                    f"共{sum(len(v.users) for v in self.user_data.groups.values())}个用户"
                )
            except Exception as e:
                self.plugin_logger.log(
                    f"签到数据文件格式错误，将重新创建: {e}", PluginLoggerLevel.WARNING
                )
                self.user_data = SignData()
                await self.resource_manager.save_json(
                    self.user_data.model_dump(), self.signdata_file
                )
        else:
            await self._save_data()
            self.plugin_logger.log("已创建签到数据文件", PluginLoggerLevel.INFO)

        # 加载塔罗牌含义
        if os.path.exists(self.tarots_meaning_file):
            self.tarots_meaning = await self.resource_manager.read_json(self.tarots_meaning_file)
        else:
            self.plugin_logger.log("文件 tarot_meanings.json 缺失", PluginLoggerLevel.ERROR)

        # 加载宜忌事项
        if os.path.exists(self.fortune_text_file):
            self.fortune_text = await self.resource_manager.read_json(self.fortune_text_file)
        else:
            self.plugin_logger.log("文件 fortune_text.json 缺失", PluginLoggerLevel.ERROR)

        # 加载背景图 URL 列表
        if os.path.exists(self.background):
            background_json = await self.resource_manager.read_json(self.background)
            self.background_urls = background_json.get("urls", [])
            if not self.background_urls:
                self.plugin_logger.log(
                    "background.json 中 urls 为空或不存在", PluginLoggerLevel.WARNING
                )
        else:
            self.plugin_logger.log("文件 background.json 缺失", PluginLoggerLevel.ERROR)

    async def _save_data(self) -> None:
        """将用户签到数据异步写入文件。"""
        await self.resource_manager.save_data(self.user_data)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _clamp_delay_with_log(self, value: int, name: str) -> int:
        """钳制缓存时间并记录日志。"""
        clamped = max(DELAY_MIN, min(value, DELAY_MAX))
        if clamped != value:
            self.plugin_logger.log(
                f"{name} {value} 超出范围，已调整为 {clamped}"
            )
        return clamped

    def _init_user(self, group_id: str, user_id: str) -> None:
        """确保指定群组和用户的数据结构已初始化。"""
        if group_id not in self.user_data.groups:
            self.user_data.groups[group_id] = GroupData(users={})
        if user_id not in self.user_data.groups[group_id].users:
            self.user_data.groups[group_id].users[user_id] = UserData()

    @staticmethod
    def _today() -> str:
        """返回今日日期字符串，格式 YYYY-MM-DD。"""
        return datetime.now().strftime("%Y-%m-%d")

    def _get_fortune(self, rng: random.Random) -> FortuneType:
        """根据配置的概率随机获取运势等级。"""
        ji_prob = self.config["fortune_config"]["probability"]["ji"]
        ping_prob = self.config["fortune_config"]["probability"]["ping"]
        xiong_prob = self.config["fortune_config"]["probability"]["xiong"]

        # 校验并修正越界概率
        if not (PROBABILITY_MIN <= ji_prob <= PROBABILITY_MAX):
            ji_prob = DEFAULT_JI_PROB
            self.plugin_logger.log("吉的概率超出范围")
        if not (PROBABILITY_MIN <= ping_prob <= PROBABILITY_MAX):
            ping_prob = DEFAULT_PING_PROB
            self.plugin_logger.log("平的概率超出范围")
        if not (PROBABILITY_MIN <= xiong_prob <= PROBABILITY_MAX):
            xiong_prob = DEFAULT_XIONG_PROB
            self.plugin_logger.log("凶的概率超出范围")

        rand = rng.randint(1, ji_prob + ping_prob + xiong_prob)

        if rand <= xiong_prob:
            fortune = rng.choice([FortuneType.XIONG, FortuneType.DA_XIONG])
        elif rand <= xiong_prob + ping_prob:
            fortune = rng.choice([FortuneType.MO_JI, FortuneType.PING])
        else:
            fortune = rng.choice([FortuneType.DA_JI, FortuneType.ZHONG_JI, FortuneType.XIAO_JI])

        return fortune

    async def _get_tarot_meaning(
        self,
        event: AstrMessageEvent,
        tarot_cards: list[str],
        is_reversed: list[int],
    ) -> str:
        """调用 LLM 解析塔罗牌含义。"""
        unified_msg_origin = event.unified_msg_origin
        provider_id: str = self.config["tarot_config"]["llm_provider_id"]

        if not provider_id:
            self.plugin_logger.log("未配置塔罗牌含义解释模型, 使用 astrbot 默认模型")
            provider_id = await self.context.get_current_chat_provider_id(unified_msg_origin)

        prompt: str = self.config["tarot_config"]["llm_prompt"] + "\n"

        for card, reversed_flag in zip(tarot_cards, is_reversed, strict=True):
            key = f"{card}_r" if reversed_flag else card
            local_meaning = self.tarots_meaning.get(key, "")
            if local_meaning:
                direction = "逆位" if reversed_flag else "正位"
                prompt += f"{card}: {direction} (参考含义: {local_meaning})\n"
            else:
                direction = "逆位" if reversed_flag else "正位"
                prompt += f"{card}: {direction}\n"

        try:
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            return llm_resp.completion_text
        except ProviderNotFoundError as e:
            self.plugin_logger.log(f"未找到塔罗牌含义解析模型: {e}", PluginLoggerLevel.ERROR)
            return "不知道"
        except Exception as e:
            self.plugin_logger.log(f"调用模型解析塔罗牌含义时出现错误: {e}", PluginLoggerLevel.ERROR)
            return "不知道"

    # ------------------------------------------------------------------
    # 指令处理器
    # ------------------------------------------------------------------

    @filter.command("sign")
    async def sign_handler(self, event: AstrMessageEvent) -> None:
        """签到指令：每日签到获取小饼干。"""
        group_id: str = event.get_group_id()
        user_id: str = event.get_session_id()
        user_name: str = event.get_sender_name()

        self._init_user(group_id, user_id)

        # 检查今日是否已签到
        today = self._today()
        last_date = self.user_data.groups[group_id].users[user_id].last_sign_date
        if last_date == today:
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(
                    f"{user_name} 今天已经签到过了哦，一天只能领一次小饼干 0v0\n"
                    f"明天再来找我玩吧~"
                ),
            ]
            await event.send(message_result)
            return

        # 随机获得小饼干
        gained = random.randint(SIGN_CREDIT_MIN, SIGN_CREDIT_MAX)
        self.user_data.groups[group_id].users[user_id].credit += gained
        self.user_data.groups[group_id].users[user_id].last_sign_date = today

        current_credit: str | int = (
            "infinite"
            if self.infinite_credit
            else self.user_data.groups[group_id].users[user_id].credit
        )
        await self._save_data()

        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(
                f"唔...闻到香香的味道了~ {user_name} 签到拿到 {gained} 个小饼干啦！"
                f"放在我这里帮你保管好不好呀 0v0\n"
                f"你现在一共攒了 {current_credit} 个小饼干了，分我吃一口嘛~"
            )
        ]
        await event.send(message_result)

    @filter.command("tarot")
    async def tarot_handler(self, event: AstrMessageEvent, cards: int = 1) -> None:
        """塔罗牌占卜指令：消耗小饼干抽取塔罗牌。"""
        group_id: str = event.get_group_id()
        user_id: str = event.get_session_id()
        user_name: str = event.get_sender_name()

        # 限制抽牌数量
        if not (TAROT_CARDS_MIN <= cards <= TAROT_CARDS_MAX):
            cards = max(TAROT_CARDS_MIN, min(cards, TAROT_CARDS_MAX))
            self.plugin_logger.log(
                f"抽取卡牌的数量超出范围, 已重新调整为 {cards}", PluginLoggerLevel.WARNING
            )

        self._init_user(group_id, user_id)

        # 检查小饼干是否足够
        user_credit = self.user_data.groups[group_id].users[user_id].credit
        if not self.infinite_credit and user_credit < cards * COST_PER_TAROT_CARD:
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(
                    f"诶...你的小饼干不够了呀，这点零食还想骗我干活 QAQ？\n"
                    f"快去发个 '/sign' 领点小饼干再来找我玩嘛~"
                ),
            ]
            await event.send(message_result)
            return

        # 抽取塔罗牌（fix_random 开启时同用户同天结果固定）
        if self.config["tarot_config"]["fix_random"]:
            seed = f"{self._today()}_{user_id}"
            rng = random.Random(seed)
        else:
            rng = random.Random()

        tarot_cards: list[str] = [
            card.value for card in rng.sample(self.ALL_TAROT_CARDS, cards)
        ]
        reversed_flags: list[int] = [rng.randint(0, 1) for _ in range(cards)]

        # 并发：LLM 解析含义 与 CDN 下载图片同时进行
        meaning_task = asyncio.create_task(
            self._get_tarot_meaning(event, tarot_cards, reversed_flags)
        )

        # 构建下载任务列表
        cdn_base = self.resource_manager.tarots_cdn_base
        image_urls: list[str] = [f"{cdn_base}/{name}.png" for name in tarot_cards]
        download_filenames: list[str] = [
            f"tarot_{name}_{self.resource_manager.generate_filename()}.png"
            for name in tarot_cards
        ]
        download_paths: list[str] = [
            os.path.join(self.output_dir, filename) for filename in download_filenames
        ]

        download_tasks = [
            self.resource_manager.download_image(url, path)
            for url, path in zip(image_urls, download_paths, strict=True)
        ]
        download_results: list[str | None] = await asyncio.gather(*download_tasks)

        # 任一图片下载失败则终止
        for result, url in zip(download_results, image_urls, strict=True):
            if result is None:
                self.plugin_logger.log(
                    f"从 CDN 下载塔罗牌失败: {url}", PluginLoggerLevel.WARNING
                )
                # 清理已下载的临时文件
                for path in download_results:
                    if path is not None:
                        self.resource_manager.schedule_delete(path, 0)
                message_result = event.make_result()
                message_result.chain = [
                    Comp.Plain(
                        f"唔...让狐狐帮 {user_name} 摸摸看是什么~\n"
                        f"诶？居然是空的！绝对不是我弄坏了哦 QAQ，是真的什么都没有捞到 www"
                    ),
                ]
                await event.send(message_result)
                return

        # 生成正向/逆位图片路径（逆位牌需要旋转 180°）
        image_paths: list[str] = []
        # 前面已确保全部下载成功，此处做类型窄化
        for downloaded_path, reversed_flag, card_name in zip(
            download_results, reversed_flags, tarot_cards, strict=True
        ):
            assert downloaded_path is not None
            if reversed_flag:
                img = Image.open(downloaded_path)
                rotated = img.rotate(180)
                output_filename = (
                    f"{card_name}_reversed_{self.resource_manager.generate_filename()}.png"
                )
                image_path = os.path.join(self.output_dir, output_filename)
                rotated.save(image_path)
            else:
                image_path = downloaded_path
            image_paths.append(image_path)

        # 等待 LLM 含义解析
        meaning = await meaning_task

        # 扣除小饼干
        if not self.infinite_credit:
            self.user_data.groups[group_id].users[user_id].credit -= cards * COST_PER_TAROT_CARD
            current_credit: str | int = self.user_data.groups[group_id].users[user_id].credit
        else:
            current_credit = "infinite"

        # 构建并发送回复
        message_result = event.make_result()
        message_result.chain = [
            Comp.Plain(f"唔...让我看看 {user_name} 抽到了什么好东西~")
        ]
        for image_path in image_paths:
            message_result.chain.append(Comp.Image.fromFileSystem(image_path))
        message_result.chain.append(
            Comp.Plain(
                f"结果出来啦：{meaning} www\n"
                f"作为报酬，这{cards}个小饼干我就嗷呜一口吃掉啦！"
                f"你现在还剩 {current_credit} 个小饼干哦 0v0"
            )
        )

        await self._save_data()
        await event.send(message_result)

        # 发送完毕后清理临时文件
        for downloaded_path, image_path, reversed_flag in zip(
            download_results, image_paths, reversed_flags, strict=True
        ):
            self.resource_manager.schedule_delete(image_path, 0)
            if reversed_flag:
                self.resource_manager.schedule_delete(downloaded_path, 0)

    @filter.command("fortune")
    async def fortune_handler(self, event: AstrMessageEvent) -> None:
        """运势卡指令：生成今日运势卡片。"""
        user_id: str = event.get_session_id()

        # 检查背景图列表
        if not self.background_urls:
            self.plugin_logger.log("背景图片 URL 列表为空", PluginLoggerLevel.WARNING)
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(
                    f"呜哇，看运势的牌牌好像卡住了 0v0！"
                    f"绝对不是因为狐狐觉得算命太麻烦才弄坏的哦 QAQ，总之现在暂时算不了啦~"
                )
            ]
            await event.send(message_result)
            return

        # fix_random 开启时同用户同天结果固定
        if self.config["fortune_config"]["fix_random"]:
            seed = f"{self._today()}_{user_id}"
            rng = random.Random(seed)
        else:
            rng = random.Random()

        # 随机选背景图并下载
        background_url = rng.choice(self.background_urls)
        download_filename = (
            f"fortune_background_{self.resource_manager.generate_filename()}.png"
        )
        download_path = os.path.join(self.output_dir, download_filename)
        downloaded_bg = await self.resource_manager.download_image(
            background_url, download_path
        )

        # 下载用户头像
        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        avatar_path = os.path.join(self.avatar_dir, f"{user_id}.png")
        avatar_path = await self.resource_manager.download_image(avatar_url, avatar_path)

        # 根据概率获取运势并选择宜忌文本
        fortune = self._get_fortune(rng)
        yi_items: list[str] = self.fortune_text["yi"]
        ji_items: list[str] = self.fortune_text["ji"]

        title = fortune.value
        yi_text = ""
        ji_text = ""

        if fortune is FortuneType.DA_JI:
            yi_text = "诸事皆宜"
            ji_text = "无"
        elif fortune in (FortuneType.ZHONG_JI, FortuneType.XIAO_JI):
            yi_text = " ".join(rng.sample(yi_items, 3))
            ji_text = " ".join(rng.sample(ji_items, 1))
        elif fortune in (FortuneType.MO_JI, FortuneType.PING):
            yi_text = " ".join(rng.sample(yi_items, 2))
            ji_text = " ".join(rng.sample(ji_items, 2))
        else:
            yi_text = " ".join(rng.sample(yi_items, 1))
            ji_text = " ".join(rng.sample(ji_items, 3))

        # 生成运势卡图片
        output_path = await self.generator.generate(
            input_path=downloaded_bg,
            title=title,
            yi_text=yi_text.strip(),
            ji_text=ji_text.strip(),
            avatar_path=avatar_path,
        )

        if output_path is None:
            self.plugin_logger.log("生成运势卡时出现错误", PluginLoggerLevel.ERROR)
            message_result = event.make_result()
            message_result.chain = [
                Comp.Plain(
                    f"呜哇，看运势的牌牌好像卡住了 0v0！"
                    f"绝对不是因为狐狐觉得算命太麻烦才弄坏的哦 QAQ，总之现在暂时算不了啦~"
                )
            ]
            await event.send(message_result)
            return

        # 发送运势卡
        message_result = event.make_result()
        message_result.chain = [Comp.Image.fromFileSystem(output_path)]
        await event.send(message_result)

        # 延时清理临时文件
        self.resource_manager.schedule_delete(output_path, self.output_delay_time)
        self.resource_manager.schedule_delete(downloaded_bg, 0)
        self.resource_manager.schedule_delete(avatar_path, self.avatar_delay_time)

    async def terminate(self) -> None:
        """插件销毁时清理缓存的头像和运势卡片。"""
        delete_tasks: list[asyncio.Task] = []

        for file_path in self.resource_manager.get_files(self.avatar_dir):
            task = self.resource_manager.schedule_delete(file_path, 0)
            if task:
                delete_tasks.append(task)

        for file_path in self.resource_manager.get_files(self.output_dir):
            task = self.resource_manager.schedule_delete(file_path, 0)
            if task:
                delete_tasks.append(task)

        if delete_tasks:
            await asyncio.gather(*delete_tasks)
