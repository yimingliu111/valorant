# -*- coding: utf-8 -*-
"""火球元素：摊开手掌时掌心上方熊熊燃烧的火球
（旋转断续火环 + 摇曳火舌 + 白热光球 + 上升余烬），收拢手掌即淡出。"""
import math

import cv2
import numpy as np

from fx_common import HAND_REF_SIZE, overlay_bgra, build_radial_sprite, _hsv2bgr, \
    build_flash_text, build_hint_pill


class FireElement:
    """火球。摊开手掌（五指伸展）触发，收拢即熄。"""

    name = "fire"
    label = "火球"
    has_fly = False

    def __init__(self):
        # 火球光球三层径向：外层橙 → 中层黄 → 内核白热
        self.radials = (build_radial_sprite(128, (60, 160, 255)),
                        build_radial_sprite(128, (110, 220, 255)),
                        build_radial_sprite(128, (235, 245, 255)))
        self.flash_img = build_flash_text("火来！", stroke=(255, 120, 60))
        self.hint_img = build_hint_pill("来吧，走起")

    def prepare(self):
        pass

    def reset(self, sw):
        """切换元素时重置该手的状态。"""
        sw.mode = "hold"
        sw.alpha = 0.0
        sw.target = 0.0
        sw.flashed = False
        sw.palm_open = False
        sw.trail = []

    # ---------------- 状态更新 ----------------

    def update(self, sw, lm, px, py, pcx, pcy, size, now, dt):
        wrist = lm[0]
        d = lambda a, b: math.hypot(a.x - b.x, a.y - b.y)
        # 摊手判定（对任意手势朝向稳健）：四指伸展 + 拇指外张，带迟滞
        ext = sum(1 for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18))
                  if d(lm[tip], wrist) > d(lm[pip], wrist) * 1.08)
        thumb_out = d(lm[4], lm[5]) > d(lm[2], lm[5]) * 1.15
        open_now = (ext >= 3) if sw.palm_open else (ext >= 4 and thumb_out)
        if open_now:
            if not sw.palm_open and sw.alpha < 0.2:
                sw.burst_t0 = now              # 掌心爆燃
                sw.burst_pos = (pcx, pcy - 90 * sw.scale)
            sw.target = 1.0
            if sw.alpha < 0.2:
                sw.pos[:] = (pcx, pcy)
            # 锚定掌心中心（而非食指尖）：手掌转动时火球依然稳定
            sw.pos += (np.array([pcx, pcy]) - sw.pos) * 0.3
            sw.scale = float(np.clip(size / HAND_REF_SIZE, 0.7, 2.2))
            # 火球悬浮在掌心上方，随呼吸轻微起伏
            sw.orbit_pos = (sw.pos[0], sw.pos[1] - 90 * sw.scale
                            + math.sin(now * 2.6) * 6 * sw.scale)
            if len(sw.particles) < 36:         # 上升余烬
                sw.particles.append([np.random.rand() * math.tau,
                                     6 + np.random.rand() * 10,
                                     6 + np.random.rand() * 10,
                                     1.0, 14 + np.random.rand() * 16])
        else:
            sw.target = 0.0
        sw.palm_open = open_now

    # ---------------- 绘制 ----------------

    def draw_hold(self, frame, sw, now, t_start):
        self.draw_fireball(frame, sw, now, sw.alpha)
        # 上升余烬
        ccx, ccy = sw.orbit_pos
        for ang, r, _, life, hue in sw.particles:
            pr = r * sw.scale
            x = ccx + math.cos(ang + (now - t_start) * 3) * pr
            y = ccy - ((1 - life) * 70 * sw.scale
                       + math.sin(ang + (now - t_start) * 2) * pr * 0.4)
            col = _hsv2bgr(int(hue * 0.5), 255, 235)
            k = max(1, int(2.0 * sw.scale * life + 0.5))
            cv2.circle(frame, (int(x), int(y)), k,
                       tuple(int(c * sw.alpha * life) for c in col), -1, cv2.LINE_AA)

    def draw_fireball(self, frame, sw, now, alpha):
        """火球本体：断续旋转火环 + 摇曳火舌 + 白热光球，逐帧闪烁。"""
        scale = sw.scale
        cx, cy = sw.orbit_pos
        S = 44 * scale
        size = (int(S * 5.6) // 2) * 2
        layer = np.zeros((size, size, 4), np.uint8)
        c = size // 2
        # 1) 外圈火环：断续弧线缓慢旋转
        Rr = S * 1.5 * (1 + 0.04 * math.sin(now * 6))
        for k in range(14):
            a0 = (k * (360 / 14) + now * 50) % 360
            cv2.ellipse(layer, (c, c), (int(Rr), int(Rr)), a0, 0, 12 + (k % 3) * 5,
                        (70, 180, 255, int(150 * alpha)), 2 + (k % 3), cv2.LINE_AA)
        # 2) 火舌：顶部主火舌 + 三片侧火舌，随机摇曳
        tongues = ((-90, 2.0, 10), (-25, 1.4, 2), (150, 1.3, 4), (215, 1.35, 6))
        for base, ln, ph in tongues:
            fl = 0.7 + 0.3 * math.sin(now * 9 + ph) + 0.12 * math.sin(now * 21 + ph * 2)
            a = math.radians(base + 6 * math.sin(now * 3 + ph))
            tip_r = S * 1.5 * ln * fl
            pa, pb = a + 0.17, a - 0.17
            for rr, col in ((0.85, (90, 200, 255, int(150 * alpha))),      # 外焰橙
                            (0.62, (140, 230, 255, int(180 * alpha)))):    # 内焰黄
                p1 = (int(c + math.cos(pa) * Rr * rr), int(c + math.sin(pa) * Rr * rr))
                p2 = (int(c + math.cos(pb) * Rr * rr), int(c + math.sin(pb) * Rr * rr))
                ti = (int(c + math.cos(a) * tip_r * rr), int(c + math.sin(a) * tip_r * rr))
                cv2.fillPoly(layer, [np.array([p1, ti, p2], np.int32)], col)
        # 3) 光球：白热核心 → 黄 → 橙，半径闪烁
        flick = 1 + 0.08 * math.sin(now * 11) + 0.05 * math.sin(now * 29 + 1.7)
        orb_r = max(4, int(S * flick))
        for spr, rad in zip(self.radials, (2.1, 1.35, 0.8)):
            rr = max(4, int(orb_r * rad))
            small = cv2.resize(spr, (rr * 2, rr * 2), interpolation=cv2.INTER_AREA)
            overlay_bgra(layer, small, c, c, 1.0)
        overlay_bgra(frame, layer, cx, cy, alpha)
