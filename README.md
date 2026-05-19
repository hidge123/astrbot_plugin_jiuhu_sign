# 酒狐主题签到 (astrbot_plugin_jiuhu_sign)

一个简单的酒狐主题的 AstrBot 签到插件，提供每日签到、塔罗牌占卜和今日运势卡生成功能。

## 功能

| 指令 | 说明 |
|------|------|
| `/sign` | 每日签到，随机获得 1-5 个小饼干 |
| `/tarot` | 抽取一张塔罗牌（消耗 1 个小饼干），含正位/逆位 |
| `/fortune` | 生成今日运势卡（大吉/中吉/小吉/末吉/平/凶/大凶） |

## 安装

### 依赖

```bash
pip install -r requirements.txt
```

依赖项：
- `pydantic>=2.12.5` — 数据模型验证
- `aiofiles>=25.1.0` — 异步文件操作
- `aiohttp>=3.13.5` — 异步 HTTP 请求（下载头像）
- `pillow>=11.0.0` — 图片处理（塔罗牌翻转、运势卡生成）

## 配置

```json
{
  "sign_config": {
    "infinite_credit": false       // 无限饼干模式，开启后不消耗饼干
  },
  "fortune_config": {
    "delay_time": {
      "avatar": 60,               // 用户头像缓存时间（秒）
      "output": 60                // 运势卡/翻转塔罗牌缓存时间（秒）
    },
    "probability": {
      "ji": 10,                   // 吉的概率权重（1-10）
      "ping": 10,                 // 平的概率权重（1-10）
      "xiong": 10                 // 凶的概率权重（1-10）
    }
  },
  "other_config": {
    "debug_mode": false           // 开启调试日志
  }
}
```

## 自定义资源

- **塔罗牌图片**：替换 `tarots/image/` 目录下的 22 张大阿尔卡那图片（`.png` 格式），文件名对应 `TarotType` 枚举值（如 `the_fool.png`、`the_magician.png`）。逆位牌由插件自动旋转生成，无需额外准备。
- **塔罗牌含义**：编辑 `tarots/tarot_meanings.json` 自定义每张牌正/逆位的解释文本。
- **运势背景**：替换 `fortune/backgrounds/` 目录下的背景图片。
- **宜忌事项**：编辑 `fortune/fortune_text.json` 自定义黄历宜忌文本。
- **运势卡字体**：替换 `fortune/font/mengxin.TTF`。

## 目录结构

```
astrbot_plugin_jiuhu_sign/
├── main.py              # 插件主入口
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置项定义
├── requirements.txt     # 依赖
├── sign_config.py       # 数据模型
├── plugin_logger.py     # 日志工具
├── resources.py         # 资源管理（文件读写、下载、定时删除）
├── generator.py         # 运势卡图片生成器
├── fortune/
│   ├── font/            # 字体文件
│   ├── backgrounds/     # 运势卡背景图片
│   └── fortune_text.json
└── tarots/
    ├── image/           # 22张大阿尔卡那牌图片
    └── tarot_meanings.json
```

运行时数据目录：`plugin_data/astrbot_plugin_jiuhu_sign/`

## 其他

运势功能的实现参考了 [astrbot_plugin_jrys]("https://github.com/NINIYOYYO/astrbot_plugin_jrys?tab=AGPL-3.0-1-ov-file") 仓库

## 许可证

本项目基于 [GNU Affero General Public License v3.0](LICENSE) 开源。
