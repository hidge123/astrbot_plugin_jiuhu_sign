"""插件日志控制器 —— 支持按等级过滤日志输出。"""

from enum import IntEnum

from astrbot.api import logger


class PluginLoggerLevel(IntEnum):
    """日志输出等级（继承 IntEnum 以便直接比较大小）。"""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4


class PluginLogger:
    """根据配置的日志等级决定是否输出日志消息。"""

    def __init__(self, level: PluginLoggerLevel) -> None:
        self._level: PluginLoggerLevel = level

    def log(self, message: str, level: PluginLoggerLevel = PluginLoggerLevel.INFO) -> None:
        """按等级输出日志；低于当前配置等级的消息将被静默。"""
        if level < self._level:
            return

        if level == PluginLoggerLevel.DEBUG:
            logger.debug(message)
        elif level == PluginLoggerLevel.INFO:
            logger.info(message)
        elif level == PluginLoggerLevel.WARNING:
            logger.warning(message)
        elif level == PluginLoggerLevel.ERROR:
            logger.error(message)
