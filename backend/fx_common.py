# -*- coding: utf-8 -*-
"""特效通用工具：BGRA 叠加、径向光斑、HSV 转换、PIL 文字渲染、爆发冲击波。

各元素（element_dart / element_fire / ...）与主程序共用这里的内容。"""
import math

import cv2
import numpy as np

SWORD_LEN       = 240.0   # 特效本体的基准长度（像素，随手的远近自动缩放）
HAND_REF_SIZE   = 200.0   # 手腕到指尖的参考像素距离（用于随远近缩放）
LAUNCH_COOLDOWN = 0.9     # 发射冷却（秒）


def _hsv2bgr(h, s, v):
    """单点 HSV(H:0-179) 转 BGR，用于粒子配色。"""
    px = np.uint8([[[h, s, v]]])
    return tuple(int(c) for c in cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0, 0])


def build_radial_sprite(size, color):
    """圆形径向光斑：中心不透明向外衰减，BGRA。"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    alpha = np.clip(1.0 - d, 0, 1) ** 1.8 * 255
    sprite = np.zeros((size, size, 4), np.uint8)
    sprite[..., 0], sprite[..., 1], sprite[..., 2] = color
    sprite[..., 3] = alpha.astype(np.uint8)
    return sprite


WHITE_RADIAL = build_radial_sprite(64, (255, 255, 255))   # 枪口闪光核心


def overlay_bgra(frame, sprite, cx, cy, alpha=1.0):
    """把 BGRA 精灵以 (cx,cy) 为中心混合到目标图上（BGR 帧或 BGRA 层均可），
    自动裁剪越界部分。"""
    if sprite is None or alpha <= 0.01:
        return
    h, w = sprite.shape[:2]
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    x1, y1 = x0 + w, y0 + h
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return
    sp = sprite[sy0:sy0 + y1 - y0, sx0:sx0 + x1 - x0].astype(np.float32)
    a = (sp[..., 3:4] / 255.0) * alpha
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    if frame.shape[2] == 4:                    # 目标是 BGRA 层：alpha 通道也参与混合
        frame[y0:y1, x0:x1] = (sp * a + roi * (1 - a)).astype(np.uint8)
    else:
        frame[y0:y1, x0:x1] = (sp[..., :3] * a + roi * (1 - a)).astype(np.uint8)


def draw_burst(frame, sw, now):
    """发射/爆燃时的枪口火光：白色闪光核心 + 扩散圆环 + 放射速度线。"""
    ft = now - sw.burst_t0
    if not (0 <= ft <= 0.45):
        return
    if ft <= 0.12:
        q = ft / 0.12
        core_r = 26 + 90 * q
        core = cv2.resize(WHITE_RADIAL, (int(core_r * 2), int(core_r * 2)),
                          interpolation=cv2.INTER_AREA)
        overlay_bgra(frame, core, sw.burst_pos[0], sw.burst_pos[1], (1 - q) * 0.9)
    p = ft / 0.45
    R = 16 + 150 * p
    a = (1 - p) * 0.85
    size = int(R * 2 + 8)
    layer = np.zeros((size, size, 4), np.uint8)
    c = size // 2
    cv2.circle(layer, (c, c), int(R), (200, 255, 190, int(255 * a)), 3, cv2.LINE_AA)
    for k in range(14):
        ang = k * (math.tau / 14) + 0.2
        r0, r1 = R * 0.55, R * 0.95
        cv2.line(layer,
                 (int(c + math.cos(ang) * r0), int(c + math.sin(ang) * r0)),
                 (int(c + math.cos(ang) * r1), int(c + math.sin(ang) * r1)),
                 (210, 255, 200, int(255 * a * 0.8)), 2, cv2.LINE_AA)
    overlay_bgra(frame, layer, sw.burst_pos[0], sw.burst_pos[1], 1.0)


def _pick_font(size):
    """按优先级找一个可用的中文系统字体。"""
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return None


def build_flash_text(text, size=96, stroke=(80, 200, 120)):
    """渲染带描边的大字（如「风来！」），返回 BGRA（失败返回 None）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        font = _pick_font(size)
        if font is None:
            return None
        tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        step = tmp.textlength(text[0], font=font) + size * 0.15      # 字间距
        w = int(step * len(text) + size)
        img = Image.new("RGBA", (w, int(size * 1.7)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = size * 0.4
        for ch in text:
            d.text((x, size * 0.25), ch, font=font, fill=(225, 255, 215, 255),
                   stroke_width=6, stroke_fill=stroke + (255,))
            x += step
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)
    except Exception:
        return None


def build_hint_pill(text, size=26):
    """底部半透明提示条，返回 BGRA。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        font = _pick_font(size)
        if font is None:
            return None
        tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        tw = int(tmp.textlength(text, font=font))
        pad_x, pad_y = 26, 12
        img = Image.new("RGBA", (tw + pad_x * 2, size + pad_y * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                            radius=(size + pad_y * 2) // 2,
                            fill=(14, 26, 45, 158), outline=(90, 200, 255, 120), width=1)
        d.text((pad_x, pad_y - 2), text, font=font, fill=(210, 240, 255, 255))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)
    except Exception:
        return None
