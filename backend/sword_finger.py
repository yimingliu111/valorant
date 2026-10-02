# -*- coding: utf-8 -*-
"""指尖元素 —— 摄像头实时特效主程序。

当前包含两种元素，运行时按 1 / 2 切换（逻辑分别在独立文件，方便单独修改）：
  1 风之飞镖（element_dart.py）：绕指尖旋转飞行，食指指向前方时发射
  2 火球    （element_fire.py）：摊开手掌即熊熊燃烧，收拢手掌熄灭

运行：source venv/bin/activate && python sword_finger.py
退出：按 Q / ESC 或关闭窗口。摄像头权限见 README。"""

import math
import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from fx_common import overlay_bgra, draw_burst
from element_dart import DartElement
from element_fire import FireElement

MODEL_PATH  = Path(__file__).parent / "hand_landmarker.task"
WINDOW_NAME = "指尖元素 · (1 飞镖 / 2 火球 / Q 退出)"


class SwordState:
    """每只手一份的特效状态（各元素共用字段，按需取用）。"""

    def __init__(self):
        self.alpha = 0.0
        self.target = 0.0
        self.spin = 0.0
        self.pos = np.array([0.0, 0.0])
        self.scale = 1.0
        self.was_up = False
        self.flashed = False
        self.particles = []          # [角度, 半径, 半径速度, 生命, 色相]
        self.flash_t0 = -10.0        # 召唤大字闪现起始时间
        self.flash_pos = (0.0, 0.0)
        self.mode = "hold"           # hold=跟随手部, fly=发射飞行（仅飞镖）
        self.fly_pos = np.array([0.0, 0.0])
        self.align_deg = 0.0
        self.fly_t = 0.0
        self.fly_scale = 1.0
        self.trail = []              # 飞行残影 [(x, y, 绝对缩放, 对准角)]
        self.burst_t0 = -10.0        # 发射/爆燃冲击波起始时间
        self.burst_pos = (0.0, 0.0)
        self.cooldown_until = 0.0
        self.orbit_ang = np.random.rand() * math.tau   # 绕指尖公转相位
        self.orbit_pos = (0.0, 0.0)                    # 当前公转/悬浮位置
        self.pointing = False        # 食指是否指向前方（飞镖）
        self.palm_open = False       # 手掌是否摊开（火球）
        self.last_seen = 0.0         # 上一次检测到手的时间（丢失宽限用）


def fake_hand(t, point_forward):
    """构造一只虚拟手（21 点，仅含主循环用到的关键点）。

    用于无摄像头时的演示：默认手指竖起；point_forward=True 时食指指向镜头。"""
    class P:
        pass

    lm = []
    for _ in range(21):
        p = P()
        p.x, p.y, p.z = 0.5, 0.78, 0.0
        lm.append(p)
    wx, wy = 0.5 + math.sin(t / 900) * 0.18, 0.78

    def seti(i, dx, dy):
        lm[i].x, lm[i].y = wx + dx, wy + dy

    seti(0, 0, 0)                                       # 手腕
    for i, (dx, dy) in ((5, -0.03, -0.12), (9, 0.0, -0.13),
                        (13, 0.03, -0.12), (17, 0.06, -0.10)):
        seti(i, dx, dy)                                 # 四指根
    for tip, dx in ((8, -0.06), (12, 0.0), (16, 0.03), (20, 0.06)):
        seti(tip, dx, -0.30)                            # 指尖（伸展）
    for pip, dx in ((6, -0.045), (10, 0.0), (14, 0.03), (18, 0.06)):
        seti(pip, dx, -0.19)                            # 第二指节
    seti(2, -0.02, -0.06)                               # 拇指关节
    seti(4, -0.07, -0.16)                               # 拇指外张
    if point_forward:                                   # 食指指向镜头：投影缩短
        seti(8, -0.02, -0.10)
    return lm


MIN_HAND_SEP = 0.15        # 两个手部检测相距小于屏宽的这个比例 → 视为同一只手的重复检测


def pair_hands(swords, hands, W, H):
    """把每只手配给一个特效状态。

    1) 去重：快速移动时一只手常被识别成两个相距很近的检测结果，
       距离小于 MIN_HAND_SEP×屏宽 的检测视为同一只手，只保留一个，
       否则一只手会出现两个特效。
    2) 活跃中（alpha 高）的特效优先认领离它最近的手——手快速移动时
       不会被闲置状态抢走而出现一淡一显两个特效。"""
    hand_for = [None] * len(swords)
    used = [False] * len(hands)

    # ---- 第一步：近邻检测去重 ----
    min_sep = MIN_HAND_SEP * W
    kept_pos, kept = [], []
    for hi, lm in enumerate(hands):
        tip = lm[8]
        hx, hy = (1 - tip.x) * W, tip.y * H
        if all(math.hypot(hx - kx, hy - ky) >= min_sep for kx, ky in kept_pos):
            kept.append(hi)
            kept_pos.append((hx, hy))

    # ---- 第二步：活跃特效优先认领最近的手 ----
    order = sorted(range(len(swords)),
                   key=lambda si: 0 if swords[si].alpha > 0.05 else 1)
    for si in order:
        sw = swords[si]
        best, best_d = None, None
        for hi in kept:
            if used[hi]:
                continue
            tip = hands[hi][8]
            d = math.hypot((1 - tip.x) * W - sw.pos[0], tip.y * H - sw.pos[1])
            if best is None or d < best_d:
                best, best_d = hi, d
        if best is not None:
            hand_for[si] = hands[best]
            used[best] = True
    return hand_for


def main():
    elements = {"wind": DartElement(), "fire": FireElement()}
    for el in elements.values():
        el.prepare()
    element = elements["wind"]

    if not MODEL_PATH.exists():
        raise SystemExit(f"缺少模型文件 {MODEL_PATH}，请先运行 download_model.sh 或手动下载 hand_landmarker.task")

    options = vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(
            model_asset_path=str(MODEL_PATH),
            # 显式用 CPU：默认的 Metal GPU 委托在某些环境会初始化失败直接崩溃
            delegate=mp_tasks.BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        raise SystemExit("无法打开摄像头。请在「系统设置 > 隐私与安全性 > 相机」中给终端/VSCode 授权后重试。")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1100, 619)

    swords = [SwordState(), SwordState()]
    prev_t, t_start = time.perf_counter(), time.perf_counter()
    fps = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            print("摄像头读取失败，退出。")
            break
        frame = cv2.flip(frame, 1)                     # 自拍镜像
        H, W = frame.shape[:2]
        now = time.perf_counter()
        dt = min(0.05, now - prev_t)
        prev_t = now
        fps = 0.9 * fps + 0.1 / dt if dt > 0 else fps

        # ---- 手部检测 ----
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect_for_video(mp_img, int((now - t_start) * 1000))
        hands = result.hand_landmarks or []

        # ---- 手与特效状态配对：MediaPipe 返回的手序可能逐帧交换，
        #      按“与上次位置最近”贪心配对，避免双手互换导致特效跳变 ----
        hand_for = pair_hands(swords, hands, W, H)

        # ---- 各手状态更新（交给当前元素）----
        for si, sw in enumerate(swords):
            # 粒子寿命每帧衰减（与是否检测到手无关）
            for p in sw.particles:
                p[3] -= dt * 1.4
            sw.particles = [p for p in sw.particles if p[3] > 0]

            lm = hand_for[si]
            if lm is not None:
                sw.last_seen = now
            # 手快速移动时检测偶尔掉帧：宽限期内原地保持（火球继续烧、飞镖继续转），不闪断
            lost = (now - sw.last_seen) if sw.last_seen else 1e9
            if lm is None:
                if sw.mode == "hold" and sw.alpha > 0.03 and lost < HAND_LOST_GRACE:
                    continue
                if sw.mode == "hold":
                    sw.target = 0.0
                sw.pointing = False
                sw.palm_open = False
                sw.alpha += (sw.target - sw.alpha) * 0.18
                continue
            tip = lm[8]
            wrist = lm[0]
            px, py = (1 - tip.x) * W, tip.y * H    # 食指尖（飞镖锚点）
            # 掌心中心（手腕 + 四指根的中点）：火球等掌心特效的稳定锚点
            pcx = (1 - sum(lm[k].x for k in (0, 5, 9, 13, 17)) / 5) * W
            pcy = (sum(lm[k].y for k in (0, 5, 9, 13, 17)) / 5) * H
            size = math.hypot(tip.x - wrist.x, tip.y - wrist.y) * W
            element.update(sw, lm, px, py, pcx, pcy, size, now, dt)
            sw.was_up = sw.target > 0.5
            if sw.mode == "hold":
                sw.alpha += (sw.target - sw.alpha) * 0.18

        # ---- 飞行阶段（仅飞镖元素有）----
        if element.has_fly:
            for sw in swords:
                if sw.mode != "fly":
                    continue
                if not element.update_fly(sw, now, dt):
                    element.reset(sw)              # 飞行结束 → 回到指尖重新凝聚
                    sw.burst_t0 = now
                    sw.burst_pos = (float(sw.pos[0]), float(sw.pos[1]))
                    continue
                element.draw_fly(frame, sw, now)

        # ---- 悬停/燃烧阶段 ----
        for sw in swords:
            if sw.mode != "hold" or sw.alpha <= 0.03:
                continue
            element.draw_hold(frame, sw, now, t_start)

        # ---- 发射/爆燃冲击波（两个元素都用）----
        for sw in swords:
            draw_burst(frame, sw, now)

        # ---- 召唤大字 + 扩散光环 ----
        for sw in swords:
            ft = now - sw.flash_t0
            if 0 <= ft <= 1.2 and sw.alpha > 0.1:
                p = ft / 1.2
                if element.flash_img is not None:
                    fx, fy = W / 2, H * 0.16 - p * H * 0.05
                    overlay_bgra(frame, element.flash_img, fx, fy, (1 - p) * 0.95)
                ring_r = 20 + 190 * p
                ring_a = (1 - p) * 0.8
                layer = np.zeros((int(ring_r * 2 + 8),) * 2 + (4,), np.uint8)
                c = ring_r + 4
                cv2.circle(layer, (int(c), int(c)), int(ring_r),
                           (200, 255, 190, int(255 * ring_a)), 3, cv2.LINE_AA)
                overlay_bgra(frame, layer, sw.flash_pos[0], sw.flash_pos[1], 1.0)

        # ---- 提示条与帧率 ----
        if element.hint_img is not None:
            overlay_bgra(frame, element.hint_img,
                         W / 2, H - element.hint_img.shape[0] / 2 - 18, 0.92)
        cv2.putText(frame, f"{fps:.0f} fps",
                    (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        if key in (ord("1"), ord("2")):
            new_el = elements["wind"] if key == ord("1") else elements["fire"]
            if new_el is not element:
                element = new_el
                for sw in swords:
                    element.reset(sw)

    cap.release()
    cv2.destroyAllWindows()
    landmarker.close()


if __name__ == "__main__":
    main()
