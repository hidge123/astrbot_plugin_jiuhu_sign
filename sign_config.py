"""签到插件数据模型"""
from pydantic import BaseModel, Field


class UserData(BaseModel):
    """单个用户的数据模型"""
    credit: int = Field(default=0, ge=0, description="用户的小饼干数量")


class SignData(BaseModel):
    """签到数据模型"""
    users: dict[str, UserData] = Field(default_factory=dict, description="用户数据字典")
