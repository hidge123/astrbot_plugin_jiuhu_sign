"""运势卡片生成器 —— 将背景图、文案、头像合成为最终的吉凶卡片。"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from astrbot.api import AstrBotConfig

from .plugin_logger import PluginLogger, PluginLoggerLevel
from .resources import ResourceManager


class FortuneCardGenerator:
    """运势卡生成器，负责背景裁切、毛玻璃效果、头像粘贴与文字排版。"""

    # ---- 卡片尺寸 ----
    TARGET_SIZE: tuple[int, int] = (1080, 1920)
    TARGET_RATIO: float = TARGET_SIZE[0] / TARGET_SIZE[1]  # 9:16

    # ---- 毛玻璃 ----
    BLUR_RADIUS: int = 30
    FROSTED_ALPHA: int = 205        # 毛玻璃区域蒙版透明度
    TINT_OPACITY: int = 78           # 白色遮罩透明度

    # ---- 头像 ----
    AVATAR_SIZE_RATIO: float = 0.16   # 头像宽度占卡片宽度的比例
    AVATAR_LEFT_RATIO: float = 0.06   # 头像左侧边距比例
    AVATAR_TOP_RATIO: float = 0.08    # 头像在毛玻璃区域内上边距比例
    AVATAR_BORDER_SIZE: int = 6       # 头像白色描边宽度（像素）
    AVATAR_BORDER_ALPHA: int = 220    # 描边透明度

    # ---- 文字排版 ----
    TEXT_HORIZONTAL_PADDING_RATIO: float = 0.1  # 左右留白比例
    TITLE_FONT_SIZE_RATIO: float = 0.10         # 标题起始字号比例
    BODY_FONT_SIZE_RATIO: float = 0.06          # 正文起始字号比例
    TITLE_MIN_SIZE: int = 26                     # 标题最小字号
    BODY_MIN_SIZE: int = 20                      # 正文最小字号
    GAP_TITLE_BODY_RATIO: float = 0.12          # 标题与正文间距比例
    GAP_BETWEEN_LINES_RATIO: float = 0.08       # 正文行间距比例
    TEXT_START_Y_RATIO: float = 0.14            # 首行文字在毛玻璃区域内起始位置比例

    # ---- 圆角 ----
    CORNER_RADIUS: int = 48

    # ---- 毛玻璃区域分割线 ----
    OVERLAY_RATIO: float = 2 / 3  # 毛玻璃覆盖区域起始位置（从高度的 2/3 处开始）

    def __init__(
        self,
        name: str,
        config: AstrBotConfig,
        font_name: str = "mengxin.TTF",
    ) -> None:
        self.resource_manager = ResourceManager(name, config)

        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        self.font_path: str = os.path.join(self.resource_manager.font_dir, font_name)

    # ------------------------------------------------------------------
    # 图片处理
    # ------------------------------------------------------------------

    def _crop_to_ratio(self, image: Image.Image) -> Image.Image:
        """将原图居中裁切到目标宽高比，避免拉伸变形。"""
        width, height = image.size
        current_ratio = width / height

        if abs(current_ratio - self.TARGET_RATIO) < 1e-6:
            return image

        if current_ratio > self.TARGET_RATIO:
            target_width = int(height * self.TARGET_RATIO)
            left = (width - target_width) // 2
            box = (left, 0, left + target_width, height)
        else:
            target_height = int(width / self.TARGET_RATIO)
            top = (height - target_height) // 2
            box = (0, top, width, top + target_height)

        return image.crop(box)

    def _add_frosted_glass(self, image: Image.Image) -> Image.Image:
        """对卡片下 1/3 做毛玻璃处理，增强上方文字的可读性。"""
        width, height = image.size
        overlay_top = int(height * self.OVERLAY_RATIO)
        overlay_height = height - overlay_top

        # 高斯模糊 → 裁出下 1/3
        blurred = image.filter(ImageFilter.GaussianBlur(radius=self.BLUR_RADIUS))
        glass_region = blurred.crop((0, overlay_top, width, height))

        # 半透明蒙版
        mask = Image.new("L", (width, overlay_height), color=self.FROSTED_ALPHA)
        result = image.copy()
        result.paste(glass_region, (0, overlay_top))

        # 白色遮罩增加层次感
        rgba_result = result.convert("RGBA")
        tint = Image.new("RGBA", (width, overlay_height), (255, 255, 255, self.TINT_OPACITY))
        rgba_result.alpha_composite(tint, (0, overlay_top))

        region = rgba_result.crop((0, overlay_top, width, height))
        region.putalpha(mask)

        base = image.convert("RGBA")
        base.alpha_composite(region, (0, overlay_top))
        return base

    def _paste_avatar(self, image: Image.Image, avatar_path: str) -> Image.Image:
        """将圆形裁切的用户头像贴到毛玻璃区域左上角（带白色描边）。"""
        width, height = image.size
        overlay_top = int(height * self.OVERLAY_RATIO)
        overlay_height = height - overlay_top

        avatar_size = int(width * self.AVATAR_SIZE_RATIO)
        left_margin = int(width * self.AVATAR_LEFT_RATIO)
        top_margin = overlay_top + int(overlay_height * self.AVATAR_TOP_RATIO)

        with Image.open(avatar_path) as avatar:
            avatar = avatar.convert("RGBA").resize(
                (avatar_size, avatar_size), Image.Resampling.LANCZOS
            )

        # 圆形蒙版裁剪
        avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
        avatar_mask_draw = ImageDraw.Draw(avatar_mask)
        avatar_mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
        avatar.putalpha(avatar_mask)

        # 白色描边
        border = self.AVATAR_BORDER_SIZE
        frame_size = avatar_size + border * 2
        avatar_frame = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))

        frame_mask = Image.new("L", (frame_size, frame_size), 0)
        frame_mask_draw = ImageDraw.Draw(frame_mask)
        frame_mask_draw.ellipse((0, 0, frame_size, frame_size), fill=255)

        frame_fill = Image.new("RGBA", (frame_size, frame_size), (255, 255, 255, self.AVATAR_BORDER_ALPHA))
        avatar_frame.alpha_composite(frame_fill)
        avatar_frame.putalpha(frame_mask)
        avatar_frame.alpha_composite(avatar, (border, border))

        image.alpha_composite(avatar_frame, (left_margin, top_margin))
        return image

    def _apply_rounded_corners(self, image: Image.Image) -> Image.Image:
        """给整张卡片应用圆角蒙版。"""
        rounded_mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(rounded_mask)
        mask_draw.rounded_rectangle(
            (0, 0, image.size[0], image.size[1]),
            radius=self.CORNER_RADIUS,
            fill=255,
        )
        rounded = image.copy()
        rounded.putalpha(rounded_mask)
        return rounded

    # ------------------------------------------------------------------
    # 字体
    # ------------------------------------------------------------------

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """按指定字号加载本地字体。"""
        return ImageFont.truetype(str(self.font_path), size=size)

    def _fit_font(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        max_width: int,
        start_size: int,
        min_size: int,
    ) -> ImageFont.FreeTypeFont:
        """从大到小递减字号，直到文本宽度不超过 max_width。"""
        for size in range(start_size, min_size - 1, -2):
            font = self._load_font(size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
        return self._load_font(min_size)

    # ------------------------------------------------------------------
    # 文字绘制
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_centered_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        center_x: int,
        top_y: int,
        fill: tuple[int, int, int, int],
    ) -> int:
        """水平居中绘制单行文字，返回下一行的起始 y 坐标。"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = int(center_x - text_width / 2)
        draw.text((text_x, top_y), text, font=font, fill=fill)
        return int(top_y + text_height)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def generate(
        self,
        input_path: str | None,
        title: str,
        yi_text: str,
        ji_text: str,
        avatar_path: str | None = None,
    ) -> str | None:
        """根据背景图、文案和头像生成最终的运势卡片图片。

        Returns:
            生成的卡片文件路径，失败返回 None。
        """
        if input_path is None:
            self.plugin_logger.log("背景图片路径为 None", PluginLoggerLevel.ERROR)
            return None

        # 1. 加载背景并裁切到目标尺寸
        with Image.open(input_path) as original:
            image = self._crop_to_ratio(original.convert("RGB"))
            image = image.resize(self.TARGET_SIZE, Image.Resampling.LANCZOS).convert("RGBA")

        # 2. 毛玻璃效果
        image = self._add_frosted_glass(image)

        # 3. 粘贴头像
        if avatar_path and os.path.isfile(avatar_path):
            image = self._paste_avatar(image, avatar_path)
        else:
            self.plugin_logger.log(f"插入头像失败, {avatar_path} 不存在")

        # 4. 排版与绘制文字
        draw = ImageDraw.Draw(image)
        width, height = image.size
        overlay_top = int(height * self.OVERLAY_RATIO)
        overlay_height = height - overlay_top

        horizontal_padding = int(width * self.TEXT_HORIZONTAL_PADDING_RATIO)
        text_area_width = width - horizontal_padding * 2
        text_center_x = width // 2

        # 自适应字号
        title_font = self._fit_font(
            draw, title, text_area_width,
            start_size=int(width * self.TITLE_FONT_SIZE_RATIO),
            min_size=self.TITLE_MIN_SIZE,
        )
        body_sample = f"宜：{yi_text}"
        body_font = self._fit_font(
            draw, body_sample, text_area_width,
            start_size=int(width * self.BODY_FONT_SIZE_RATIO),
            min_size=self.BODY_MIN_SIZE,
        )

        # 计算垂直布局
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_height = title_bbox[3] - title_bbox[1]

        body_bbox = draw.textbbox((0, 0), "宜：示例文本", font=body_font)
        body_line_height = body_bbox[3] - body_bbox[1]

        gap_title_body = int(overlay_height * self.GAP_TITLE_BODY_RATIO)
        gap_between_lines = int(overlay_height * self.GAP_BETWEEN_LINES_RATIO)
        total_text_height = (
            title_height + gap_title_body + body_line_height * 2 + gap_between_lines
        )
        start_y = overlay_top + int(max(
            int(overlay_height * self.TEXT_START_Y_RATIO),
            (overlay_height - total_text_height) // 2,
        ))

        # 逐行绘制
        current_y = self._draw_centered_text(
            draw, title, title_font, text_center_x, start_y, (0, 0, 0, 255)
        )
        current_y += gap_title_body

        for line_text in (f"宜：{yi_text}", f"忌：{ji_text}"):
            current_y = self._draw_centered_text(
                draw, line_text, body_font, text_center_x, current_y, (0, 0, 0, 255)
            )
            current_y += gap_between_lines

        # 5. 圆角
        image = self._apply_rounded_corners(image)

        # 6. 保存输出
        output_filename = self.resource_manager.generate_filename()
        output_path = os.path.join(
            self.resource_manager.output_dir, f"{output_filename}.png"
        )

        image.save(output_path)
        return output_path
