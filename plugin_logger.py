"""签到插件日志控制器"""
from enum import Enum
from astrbot.api import logger


class PluginLoggerLevel(Enum):
    """用于插件控制日志输出的等级"""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4


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