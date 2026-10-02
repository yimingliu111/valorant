# -*- coding: utf-8 -*-
"""风之飞镖元素：黑银叶形镖身持续绕指尖旋转飞行（不发射）。"""
import math

import cv2
import numpy as np

from fx_common import (SWORD_LEN, HAND_REF_SIZE, LAUNCH_COOLDOWN,
                       overlay_bgra, build_radial_sprite, _hsv2bgr,
                       build_flash_text, build_hint_pill)

TRIGGER_REL  = 1.05    # 伸展判定：指尖离腕距离 > 第二指节离腕距离 × 该系数
POINT_ENTER  = 0.13    # 投影小于此值 = 手指指向镜头（此时伸展判定会失效，仍视为激活）
ORBIT_RADIUS = 60.0    # 绕指尖公转半径（像素，随 scale 缩放）
ORBIT_SPEED  = 2.2     # 公转角速度（弧度/秒）
RUSH_TIME    = 0.55    # 冲向观看者的飞行时长（秒）


class DartElement:
    """风之飞镖。update/draw_hold 由主循环按状态调用。"""

    name = "wind"
    label = "飞镖"
    has_fly = False

    def __init__(self):
        self.sprite = None
        self.blade_end = 0
        self.radial = build_radial_sprite(128, (190, 255, 150))
        self.flash_img = build_flash_text("风来！", stroke=(80, 200, 120))
        self.hint_img = build_hint_pill("看招")

    def prepare(self):
        if self.sprite is None:
            self._build_sprite()

    def reset(self, sw):
        """切换元素时重置该手的状态。"""
        sw.mode = "hold"
        sw.alpha = 0.0
        sw.target = 0.0
        sw.flashed = False

    # ---------------- 状态更新 ----------------

    def update(self, sw, lm, px, py, pcx, pcy, size, now, dt):
        tip, pip, wrist = lm[8], lm[6], lm[0]
        d = lambda a, b: math.hypot(a.x - b.x, a.y - b.y)
        # 激活判定：手指伸展；指向镜头时投影很短、伸展判定会失效，故并入
        finger_up = (d(tip, wrist) > d(pip, wrist) * TRIGGER_REL) \
            or d(tip, wrist) < POINT_ENTER
        if finger_up:
            if not sw.was_up and sw.alpha < 0.2 and not sw.flashed:
                sw.flash_t0 = now              # 首次召唤 →「风来」
                sw.flash_pos = (px, py)
                sw.flashed = True
            sw.target = 1.0
            if sw.alpha < 0.2:
                sw.pos[:] = (px, py)
            sw.pos += (np.array([px, py]) - sw.pos) * 0.4
            sw.scale = float(np.clip(size / HAND_REF_SIZE, 0.7, 2.2))
            self._spawn(sw)
            # 公转推进
            sw.orbit_ang = (sw.orbit_ang + dt * ORBIT_SPEED * sw.alpha) % math.tau
            R = ORBIT_RADIUS * sw.scale
            ax_ = sw.pos[0]
            ay_ = sw.pos[1] - 14 * sw.scale + math.sin(now * 4.5) * 5 * sw.scale
            sw.orbit_pos = (ax_ + math.cos(sw.orbit_ang) * R,
                            ay_ - 46 * sw.scale + math.sin(sw.orbit_ang) * R * 0.42)
        else:
            sw.target = 0.0

    def _spawn(self, sw):
        if len(sw.particles) < 36:
            sw.particles.append([np.random.rand() * math.tau,
                                 8 + np.random.rand() * 14,
                                 8 + np.random.rand() * 12,
                                 1.0, 100 + np.random.rand() * 40])

    # ---------------- 绘制 ----------------

    def draw_hold(self, frame, sw, now, t_start):
        """悬停阶段：指尖风灵法阵 + 飞镖绕指尖公转（镖身沿轨道切线）。"""
        ax, ay = sw.pos[0], sw.pos[1] - 14 * sw.scale + math.sin(now * 4.5) * 5 * sw.scale
        self._draw_sigil(frame, ax, sw.pos[1], sw.scale, sw.alpha, now - t_start)
        ccx, ccy = ax, ay - 10 * sw.scale
        for ang, r, _, life, hue in sw.particles:
            pr = r * sw.scale
            x = ccx + math.cos(ang + (now - t_start) * 5) * pr
            y = ccy + math.sin(ang + (now - t_start) * 5) * pr * 0.45
            col = _hsv2bgr(int(hue * 0.5), 255, 230)
            k = max(1, int(2.2 * sw.scale * life + 0.5))
            cv2.circle(frame, (int(x), int(y)), k,
                       tuple(int(c * sw.alpha * life) for c in col), -1, cv2.LINE_AA)
        ox, oy = sw.orbit_pos
        vx, vy = -math.sin(sw.orbit_ang), 0.42 * math.cos(sw.orbit_ang)
        align = -math.degrees(math.atan2(vx, -vy))
        self._draw_dart_at(frame, ox, oy, sw.alpha, sw.scale, align)

    def _draw_sigil(self, frame, x, y, scale, alpha, t):
        """指尖风灵法阵：光晕 + 两圈反向旋转的虚线圆。"""
        if alpha <= 0.03:
            return
        R = max(10, int(34 * scale))
        p = R + 6
        layer = np.zeros((2 * p, 2 * p, 4), np.uint8)
        g = cv2.resize(self.radial, (2 * p, 2 * p), interpolation=cv2.INTER_AREA)
        layer[..., :3] = np.maximum(layer[..., :3], g[..., :3])
        layer[..., 3] = g[..., 3]
        rot = (t * 80) % 360
        for i in range(12):
            a0 = i * 30 + rot
            cv2.ellipse(layer, (p, p), (R, R), a0, 0, 16, (190, 255, 170, 235), 2, cv2.LINE_AA)
        r2 = int(R * 0.62)
        for i in range(8):
            a0 = i * 45 - rot * 1.4
            cv2.ellipse(layer, (p, p), (r2, r2), a0, 0, 14, (180, 255, 200, 220), 2, cv2.LINE_AA)
        overlay_bgra(frame, layer, x, y, alpha * 0.9)

    def _draw_dart_at(self, frame, ax, ay, alpha, S, align_deg, blade_only=False):
        """绘制飞镖。align_deg 给定时以 (ax,ay) 为镖身中心、镖尖沿该角度。"""
        L_now = SWORD_LEN * S
        scx, scy = ax, ay
        base = self.sprite[:self.blade_end] if blade_only else self.sprite
        w_scaled = max(4, int(base.shape[1] * S))
        h_scaled = max(4, int(base.shape[0] * S))
        sp = cv2.resize(base, (w_scaled, h_scaled), interpolation=cv2.INTER_AREA)
        if align_deg:
            M = cv2.getRotationMatrix2D((w_scaled / 2, h_scaled / 2), align_deg, 1.0)
            cos, sin = abs(M[0, 0]), abs(M[0, 1])
            nw, nh = int(h_scaled * sin + w_scaled * cos), int(h_scaled * cos + w_scaled * sin)
            M[0, 2] += nw / 2 - w_scaled / 2
            M[1, 2] += nh / 2 - h_scaled / 2
            sp = cv2.warpAffine(sp, M, (nw, nh), flags=cv2.INTER_LINEAR,
                                borderValue=(0, 0, 0, 0))
        overlay_bgra(frame, sp, scx, scy, alpha)

    def _build_sprite(self):
        """离屏绘制风元素飞镖：叶形镖身（黑底银边+白色菱孔）、圆环、缠绳柄。"""
        SS = 3                                   # 3 倍超采样抗锯齿
        L = SWORD_LEN * SS
        pad = int(0.19 * L)
        W = int(2 * (0.095 * L + pad))
        H = int(2 * pad + 1.06 * L)
        cx = W // 2
        canvas = np.zeros((H, W, 4), np.float32)

        def Y(f):                                # 0=镖尖, 1=柄底
            return pad + f * L

        black = (36, 36, 40, 255)                # 镖身哑黑 (BGR)
        black2 = (22, 22, 26, 255)               # 缠绳柄深黑
        silver = (242, 237, 232, 255)            # 银边 (#e8edf2)

        # 叶形镖身：黑底、银边、中央脊线、白色菱孔
        bw = 0.078 * L
        blade = np.array([
            [cx, Y(0.0)],
            [cx + bw * 0.62, Y(0.16)],
            [cx + bw, Y(0.36)],
            [cx + 0.045 * L, Y(0.50)],
            [cx + 0.052 * L, Y(0.545)],
            [cx + 0.026 * L, Y(0.585)],
            [cx - 0.026 * L, Y(0.585)],
            [cx - 0.052 * L, Y(0.545)],
            [cx - 0.045 * L, Y(0.50)],
            [cx - bw, Y(0.36)],
            [cx - bw * 0.62, Y(0.16)],
        ], np.float32)
        cv2.fillPoly(canvas, [blade.astype(np.int32)], black)
        cv2.polylines(canvas, [blade.astype(np.int32)], True, silver,
                      max(2, int(0.010 * L)), cv2.LINE_AA)
        cv2.line(canvas, (cx, int(Y(0.03))), (cx, int(Y(0.40))),
                 (120, 124, 130, 220), max(1, int(0.006 * L)), cv2.LINE_AA)
        dia = np.array([[cx, Y(0.36)], [cx + 0.017 * L, Y(0.43)],
                        [cx, Y(0.50)], [cx - 0.017 * L, Y(0.43)]], np.float32)
        cv2.fillPoly(canvas, [dia.astype(np.int32)], (250, 248, 244, 255))
        self.blade_end = int((0.19 + 0.53) * SWORD_LEN) + 4   # 残影只取镖身

        # 圆环（镖格）
        rc_y = int(Y(0.655))
        cv2.circle(canvas, (cx, rc_y), int(0.062 * L), black, -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, rc_y), int(0.028 * L), (0, 0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, rc_y), int(0.062 * L), silver, max(2, int(0.008 * L)), cv2.LINE_AA)
        cv2.circle(canvas, (cx, rc_y), int(0.028 * L), silver, max(2, int(0.008 * L)), cv2.LINE_AA)

        # 缠绳柄
        handle = np.array([
            [cx - 0.030 * L, Y(0.62)],
            [cx + 0.030 * L, Y(0.62)],
            [cx + 0.022 * L, Y(0.97)],
            [cx + 0.034 * L, Y(1.0)],
            [cx - 0.034 * L, Y(1.0)],
            [cx - 0.022 * L, Y(0.97)],
        ], np.float32)
        cv2.fillPoly(canvas, [handle.astype(np.int32)], black2)
        for f0 in (0.71, 0.79, 0.87, 0.94):
            cv2.line(canvas, (int(cx - 0.026 * L), int(Y(f0))),
                     (int(cx + 0.026 * L), int(Y(f0 + 0.05))),
                     (110, 115, 120, 230), max(2, int(0.012 * L)), cv2.LINE_AA)

        # 风元素青绿辉光：只垫在镖身周围
        solid = (canvas[..., 3] > 0).astype(np.float32)
        glow = cv2.GaussianBlur(solid, (0, 0), 0.075 * L)
        glow = np.clip(glow * 1.15, 0, 1)
        shape_a = np.clip(canvas[..., 3], 0, 255) / 255.0
        for ch, cval in enumerate((190, 255, 150)):            # #96ffbe 的 BGR
            canvas[..., ch] += glow * cval * (1 - shape_a)
        canvas[..., 3] = np.maximum(canvas[..., 3], glow * 140)

        out = np.clip(canvas, 0, 255).astype(np.uint8)
        self.sprite = cv2.resize(out, (W // SS, H // SS), interpolation=cv2.INTER_AREA)
