"""签到插件数据模型 —— 基于 Pydantic 定义用户、群组及签到数据结构。"""

from pydantic import BaseModel, Field


class UserData(BaseModel):
    """单个用户的签到数据。"""

    credit: int = Field(
        default=0,
        ge=0,
        description="用户当前持有的小饼干数量（≥0）",
    )
    last_sign_date: str = Field(
        default="",
        description="上次签到日期，格式 YYYY-MM-DD",
    )


class GroupData(BaseModel):
    """单个群组内所有用户的签到数据集合。"""

    users: dict[str, UserData] = Field(
        default_factory=dict,
        description="群组内用户字典，key 为 user_id",
    )


class SignData(BaseModel):
    """全局签到数据，按群组组织。"""

    groups: dict[str, GroupData] = Field(
        default_factory=dict,
        description="群组数据字典，key 为 group_id",
    )
