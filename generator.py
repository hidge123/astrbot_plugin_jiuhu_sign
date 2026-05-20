from __future__ import annotations
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os
import asyncio
from .resources import ResourceManager
from .plugin_logger import PluginLogger, PluginLoggerLevel
from astrbot.api import AstrBotConfig
from io import BytesIO


class FortuneCardGenerator:
    """生成吉凶卡的工具类，负责背景处理、毛玻璃和文字排版。"""

    DEFAULT_RATIO = 9 / 16
    DEFAULT_SIZE = (1080, 1920)

    def __init__(
        self,
        name: str,
        config: AstrBotConfig,
        font_name: str = "mengxin.TTF",
    ) -> None:
        
        # 注册文件资源管理器
        self.resource_manager = ResourceManager(name, config)
        # 注册日志控制器
        if config["other_config"]["debug_mode"]:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.DEBUG)
        else:
            self.plugin_logger = PluginLogger(PluginLoggerLevel.WARNING)

        # 字体路径在实例创建时固定，方便外部重复调用。
        self.font_path = os.path.join(self.resource_manager.font_dir, font_name)
        self.target_size = self.DEFAULT_SIZE
        self.blur_radius = 30
        self.target_ratio = self.target_size[0] / self.target_size[1]


    def _crop_to_ratio(self, image: Image.Image) -> Image.Image:
        """将原图裁切到目标宽高比，避免拉伸变形。"""
        width, height = image.size
        current_ratio = width / height

        if abs(current_ratio - self.target_ratio) < 1e-6:
            return image

        if current_ratio > self.target_ratio:
            target_width = int(height * self.target_ratio)
            left = (width - target_width) // 2
            box = (left, 0, left + target_width, height)
        else:
            target_height = int(width / self.target_ratio)
            top = (height - target_height) // 2
            box = (0, top, width, top + target_height)

        return image.crop(box)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """按字号加载本地字体。"""
        return ImageFont.truetype(str(self.font_path), size=size)

    def _fit_font(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        max_width: int,
        start_size: int,
        min_size: int,
    ) -> ImageFont.FreeTypeFont:
        """从大到小尝试字号，确保文本不会超出指定宽度。"""
        for size in range(start_size, min_size - 1, -2):
            font = self._load_font(size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
        return self._load_font(min_size)

    def _add_frosted_glass(self, image: Image.Image) -> Image.Image:
        """对下三分之一做毛玻璃处理，增强文字可读性。"""
        width, height = image.size
        overlay_top = height * 2 // 3

        blurred = image.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
        glass_region = blurred.crop((0, overlay_top, width, height))

        mask = Image.new("L", (width, height - overlay_top), color=205)
        result = image.copy()
        result.paste(glass_region, (0, overlay_top))

        rgba_result = result.convert("RGBA")
        tint = Image.new("RGBA", (width, height - overlay_top), (255, 255, 255, 78))
        rgba_result.alpha_composite(tint, (0, overlay_top))

        region = rgba_result.crop((0, overlay_top, width, height))
        region.putalpha(mask)
        base = image.convert("RGBA")
        base.alpha_composite(region, (0, overlay_top))
        return base

    def _draw_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        center_x: int,
        top_y: int,
        fill: tuple[int, int, int, int],
    ) -> int:
        """按水平居中方式绘制单行文字，并返回下一行起始 y 坐标。"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = int(center_x - text_width / 2)
        draw.text((text_x, int(top_y)), text, font=font, fill=fill)
        return int(top_y + text_height)

    def _paste_avatar(
        self,
        image: Image.Image,
        avatar_path: str,
    ) -> Image.Image:
        """将头像贴到毛玻璃区域左上角。"""
        width, height = image.size
        overlay_top = height * 2 // 3
        overlay_height = height - overlay_top

        avatar_size = int(width * 0.16)
        left_margin = int(width * 0.06)
        top_margin = overlay_top + int(overlay_height * 0.08)

        with Image.open(avatar_path) as avatar:
            avatar = avatar.convert("RGBA").resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

        # 使用圆形蒙版裁剪头像，让展示效果更自然。
        avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
        avatar_draw = ImageDraw.Draw(avatar_mask)
        avatar_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
        avatar.putalpha(avatar_mask)

        # 给头像增加一圈描边，避免在亮背景上不够明显。
        border_size = 6
        frame_size = avatar_size + border_size * 2
        avatar_frame = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
        frame_mask = Image.new("L", (frame_size, frame_size), 0)
        frame_draw = ImageDraw.Draw(frame_mask)
        frame_draw.ellipse((0, 0, frame_size, frame_size), fill=255)
        frame_fill = Image.new("RGBA", (frame_size, frame_size), (255, 255, 255, 220))
        avatar_frame.alpha_composite(frame_fill)
        avatar_frame.putalpha(frame_mask)
        avatar_frame.alpha_composite(avatar, (border_size, border_size))

        image.alpha_composite(avatar_frame, (left_margin, top_margin))
        return image

    def _apply_rounded_corners(self, image: Image.Image, radius: int = 48) -> Image.Image:
        """给整张卡片应用圆角蒙版。"""
        rounded_mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(rounded_mask)
        mask_draw.rounded_rectangle((0, 0, image.size[0], image.size[1]), radius=radius, fill=255)
        rounded = image.copy()
        rounded.putalpha(rounded_mask)
        return rounded

    async def generate(
        self,
        input_path: str | None,
        title: str,
        yi_text: str,
        ji_text: str,
        avatar_path: str | None = None,
    ) -> str | None:
        """根据背景图和文案生成最终吉凶卡。"""
        if input_path is None:
            self.plugin_logger.log("背景图片路径为None", PluginLoggerLevel.WARNING)
            return None
        with Image.open(input_path) as original:
            image = self._crop_to_ratio(original.convert("RGB"))
            image = image.resize(self.target_size, Image.Resampling.LANCZOS).convert("RGBA")

        image = self._add_frosted_glass(image)
        if avatar_path and os.path.isfile(avatar_path):
            image = self._paste_avatar(image, avatar_path)
        else:
            self.plugin_logger.log(f"插入头像失败,{avatar_path}不存在")

        draw = ImageDraw.Draw(image)
        width, height = image.size
        overlay_top = height * 2 // 3
        overlay_height = height - overlay_top

        horizontal_padding = int(width * 0.1)
        text_area_width = width - horizontal_padding * 2
        text_center_x = width // 2

        title_font = self._fit_font(
            draw,
            title,
            text_area_width,
            start_size=int(width * 0.10),
            min_size=26,
        )
        body_sample = f"宜：{yi_text}"
        body_font = self._fit_font(
            draw,
            body_sample,
            text_area_width,
            start_size=int(width * 0.06),
            min_size=20,
        )

        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_height = title_bbox[3] - title_bbox[1]
        body_bbox = draw.textbbox((0, 0), "宜：示例文本", font=body_font)
        body_line_height = body_bbox[3] - body_bbox[1]

        gap_title_body = int(overlay_height * 0.12)
        gap_between_lines = int(overlay_height * 0.08)
        total_text_height = title_height + gap_title_body + body_line_height * 2 + gap_between_lines
        start_y = overlay_top + max(int(overlay_height * 0.14), (overlay_height - total_text_height) // 2)

        current_y = self._draw_centered_text(
            draw,
            title,
            title_font,
            text_center_x,
            int(start_y),
            (0, 0, 0, 255),
        )
        current_y += gap_title_body

        for line in (f"宜：{yi_text}", f"忌：{ji_text}"):
            current_y = self._draw_centered_text(
                draw,
                line,
                body_font,
                text_center_x,
                current_y,
                (0, 0, 0, 255),
            )
            current_y += gap_between_lines

        image = self._apply_rounded_corners(image)

        output_filename = self.resource_manager.generate_filename()
        output_path = os.path.join(
            self.resource_manager.output_dir,
            f"{output_filename}.png"
        )

        if output_path.lower().endswith((".jpg", ".jpeg")):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            background.save(output_path, quality=95)
        else:
            image.save(output_path)

        return output_path