"""签到插件数据模型"""
from pydantic import BaseModel, Field


class UserData(BaseModel):
    """单个用户的数据模型"""
    credit: int = Field(default=0, ge=0, description="用户的小饼干数量")
    last_sign_date: str = Field(default="", description="上次签到日期，格式 YYYY-MM-DD")

class GroupData(BaseModel):
    """每个消息群所有用户的数据模型"""
    users: dict[str, UserData] = Field(default_factory=dict, description="用户字典数据")

class SignData(BaseModel):
    """签到数据模型"""
    groups: dict[str, GroupData] = Field(default_factory=dict, description="群组数据字典")
