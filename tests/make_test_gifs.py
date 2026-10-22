#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_test_gifs.py — 生成覆盖各种场景的测试 GIF"""

import os
import random
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(OUT, exist_ok=True)


def noise_frame(w, h, mode="RGB", seed=None):
    rnd = random.Random(seed)
    if mode == "RGB":
        data = bytes(rnd.randrange(256) for _ in range(w * h * 3))
        return Image.frombytes("RGB", (w, h), data)
    raise ValueError(mode)


def transparent_noise_frame(w, h, seed=None):
    rnd = random.Random(seed)
    data = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            data[y * w + x] = 0 if (x - w // 2) ** 2 + (y - h // 2) ** 2 > (min(w, h) // 3) ** 2 else rnd.randrange(1, 256)
    im = Image.frombytes("P", (w, h), bytes(data))
    pal = [0, 0, 0]
    for _ in range(255):
        pal += [rnd.randrange(256) for _ in range(3)]
    im.putpalette(pal)
    return im


def save_gif(frames, path, delays, transparency=None):
    first = frames[0]
    kwargs = dict(save_all=True, append_images=frames[1:], duration=delays, loop=0, optimize=True)
    if transparency is not None:
        kwargs["transparency"] = transparency
    first.save(path, **kwargs)


def flat_anim(w, h, n, delay=40, bg=(245, 246, 248), fg=(7, 193, 96)):
    """平坦色块动画(模拟 UI 录屏), 体积小; 方块每帧严格移动 1px, 避免 Pillow 丢帧"""
    frames = []
    span = max(2, w - 80)
    for i in range(n):
        im = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(im)
        x = 40 + (i % span)
        d.rounded_rectangle([x, h // 2 - 20, x + 60, h // 2 + 20], radius=8, fill=fg)
        d.rectangle([20, 20, w - 20, 46], fill=(220, 224, 230))
        frames.append(im)
    return frames


def ui_anim(w, h, n, delay=40):
    """模拟屏幕录制: 窗口 + 移动光标 + 局部噪点(体积偏大)"""
    frames = []
    rnd = random.Random(42)
    for i in range(n):
        im = Image.new("RGB", (w, h), (30, 32, 38))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([80, 60, w - 80, h - 60], radius=10, fill=(250, 250, 252))
        d.rectangle([80, 60, w - 80, 96], fill=(238, 240, 244))
        for r in range(96, h - 80, 34):
            d.rectangle([100, r, 240, r + 14], fill=(210, 214, 222))
            d.rectangle([260, r, w - 120, r + 14], fill=(228, 231, 236))
        cx = 120 + int((w - 260) * i / max(1, n - 1))
        cy = 140 + (i % 40) * 4
        d.polygon([(cx, cy), (cx, cy + 18), (cx + 12, cy + 12)], fill=(20, 20, 20))
        strip = noise_frame(w - 160, 30, seed=rnd.randrange(1 << 30))
        im.paste(strip, (80, h - 50))
        frames.append(im)
    return frames


def dark_ui_recording(path, odd_delays=False, n=215, w=922, h=1048):
    """深色 UI 录屏风格样本(12/13 号): 大面积渐变底 + 每帧都在动的元素。

    odd_delays=True 时只改个别帧的延迟(10ms), 像素不变 —— 用来复现
    「延迟归一化用 Pillow 重编码, 抹掉差异区域优化, 体积反而膨胀」的问题。
    """
    from PIL import ImageFilter
    base = Image.new("RGB", (w, h), (10, 12, 14))
    bd = ImageDraw.Draw(base)
    for y in range(h):
        c = int(10 + 22 * (1 - abs(y - 260) / 520)) if abs(y - 260) < 520 else 10
        bd.line([(0, y), (w, y)], fill=(c, c + 3, c + 2))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([200, 40, 720, 380], fill=(8, 60, 44))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    base = Image.composite(glow, base, Image.new("L", (w, h), 90))

    frames, delays = [], []
    for i in range(n):
        im = base.copy()
        d = ImageDraw.Draw(im)
        for r in range(30):
            x, y = 20 + (r % 4) * 220, 420 + (r // 4) * 70
            d.rounded_rectangle([x, y, x + 200, y + 56], radius=8,
                                fill=(20, 23, 26), outline=(44, 49, 54))
            for k in range(18):
                d.line([x + 10 + k * 9, y + 14, x + 15 + k * 9, y + 14],
                       fill=(120 + (k * 7) % 60, 128, 136))
                d.line([x + 10 + k * 9, y + 30, x + 13 + k * 9, y + 30],
                       fill=(80, 88 + (k * 5) % 40, 96))
        off = (i * 13) % 260
        for r in range(12):
            yy = 90 + r * 24 - off % 24
            d.rectangle([60, yy, 60 + 300 + (r * 37 + i * 5) % 200, yy + 10],
                        fill=(30 + (i + r) % 40, 70, 60))
        sel = (i // 3) % 30
        sx, sy = 20 + (sel % 4) * 220, 420 + (sel // 4) * 70
        d.rounded_rectangle([sx, sy, sx + 200, sy + 56], radius=8,
                            outline=(43, 229, 160), width=3)
        mx, my = 60 + (i * 41) % (w - 120), 80 + (i * 29) % (h - 160)
        d.polygon([(mx, my), (mx + 14, my + 16), (mx + 5, my + 16), (mx, my + 26)],
                  fill=(245, 245, 245))
        frames.append(im)
        delays.append(10 if (odd_delays and i % 40 == 7) else 53)
    # 逐帧独立量化(局部调色板), 与常见录屏工具一致
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=delays, loop=0, optimize=False)


def finder_dialog_recording(path, n=48, w=640, h=720):
    """「首帧调色板陷阱」样本(14 号): 首段是深色页面(只有灰黑 + 绿色强调),
    后段弹出浅色访达窗口, 里面有蓝色文件夹。

    复现用户反馈: 处理后访达文件夹从蓝色变成青绿色 —— 如果整段动画只用第 1 帧的
    调色板, 第 1 帧里没有蓝色, 后面的蓝色就会被映射到最接近的青绿。
    """
    FOLDER_BODY = (104, 178, 234)   # 访达文件夹蓝
    FOLDER_TOP = (138, 201, 246)
    frames = []
    for i in range(n):
        im = Image.new("RGB", (w, h), (10, 12, 14))
        d = ImageDraw.Draw(im)
        # 深色页面: 灰黑底 + 绿色强调(与我们自己的工具界面一致)
        for r in range(9):
            d.rounded_rectangle([40, 60 + r * 64, w - 40, 60 + r * 64 + 48], radius=8,
                                fill=(20, 23, 26), outline=(44, 49, 54))
            d.rectangle([56, 76 + r * 64, 56 + 120 + (r * 23) % 160, 84 + r * 64],
                        fill=(43, 229, 160) if r % 3 == 0 else (110, 118, 126))
        if i >= 6:
            # 压暗背景 + 访达窗口淡入
            dim = Image.new("RGB", (w, h), (70, 74, 76))
            im = Image.blend(im, dim, 0.55)
            d = ImageDraw.Draw(im)
            wx, wy, ww, wh = 70, 180, w - 140, 380
            for s in range(18, 0, -1):    # 软阴影
                c = 70 - int(30 * (1 - s / 18))
                d.rounded_rectangle([wx - s, wy - s + 8, wx + ww + s, wy + wh + s + 8],
                                    radius=16 + s, outline=(c, c + 2, c + 3))
            d.rounded_rectangle([wx, wy, wx + ww, wy + wh], radius=16, fill=(243, 244, 246))
            for k in range(8):
                cx = wx + 40 + (k % 4) * 130
                cy = wy + 50 + (k // 4) * 150
                d.rounded_rectangle([cx, cy + 12, cx + 84, cy + 76], radius=8, fill=FOLDER_BODY)
                d.rounded_rectangle([cx, cy, cx + 36, cy + 20], radius=6, fill=FOLDER_TOP)
                d.rectangle([cx, cy + 22, cx + 84, cy + 30], fill=FOLDER_TOP)
                d.line([cx + 6, cy + 94, cx + 70, cy + 94], fill=(70, 74, 80), width=3)
        # 每帧都在动的鼠标指针
        mx, my = 80 + (i * 37) % (w - 160), 120 + (i * 29) % (h - 240)
        d.polygon([(mx, my), (mx + 12, my + 14), (mx + 4, my + 14), (mx, my + 22)],
                  fill=(250, 250, 250), outline=(20, 20, 20))
        frames.append(im)
    # 逐帧独立量化(局部调色板), 与常见录屏工具一致
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=[80] * n, loop=0, optimize=False)


def main():
    made = []

    # 1) 已合规的小 GIF -> 应直通
    frames = flat_anim(240, 160, 40)
    save_gif(frames, os.path.join(OUT, "01_small_ok.gif"), [40] * 40)
    made.append("01_small_ok.gif")

    # 2) 帧数超限(600帧), 体积不大 -> 只需抽帧
    frames = flat_anim(320, 240, 600, delay=33)
    save_gif(frames, os.path.join(OUT, "02_too_many_frames.gif"), [33] * 600)
    made.append("02_too_many_frames.gif")

    # 3) 体积超限(噪点难压缩), 帧数正常 -> 只需减体积
    frames = [noise_frame(640, 360, seed=i) for i in range(90)]
    save_gif(frames, os.path.join(OUT, "03_too_big.gif"), [40] * 90)
    made.append("03_too_big.gif")

    # 4) 体积和帧数都超限
    frames = [noise_frame(400, 225, seed=1000 + i) for i in range(320)]
    save_gif(frames, os.path.join(OUT, "04_big_and_many.gif"), [33] * 320)
    made.append("04_big_and_many.gif")

    # 5) 高清录屏风(1920x1080)
    frames = ui_anim(1920, 1080, 150)
    save_gif(frames, os.path.join(OUT, "05_hires_screen.gif"), [40] * 150)
    made.append("05_hires_screen.gif")

    # 6) 透明背景 GIF(中等体积, 测试透明保留)
    frames = [transparent_noise_frame(500, 500, seed=2000 + i) for i in range(120)]
    save_gif(frames, os.path.join(OUT, "06_transparent.gif"), [40] * 120, transparency=0)
    made.append("06_transparent.gif")

    # 7) 静态大图(单帧)
    noise_frame(2000, 1400, seed=7).convert("P").save(os.path.join(OUT, "07_static_big.gif"))
    made.append("07_static_big.gif")

    # 8) 帧延迟异常(全 0)
    frames = flat_anim(300, 200, 50)
    save_gif(frames, os.path.join(OUT, "08_bad_delays.gif"), [0] * 50)
    made.append("08_bad_delays.gif")

    # 9) 损坏文件
    with open(os.path.join(OUT, "09_broken.gif"), "wb") as f:
        f.write(b"GIF89a" + os.urandom(2048))
    made.append("09_broken.gif")

    # 10) 非 GIF 文件
    Image.new("RGB", (100, 100), (255, 0, 0)).save(os.path.join(OUT, "10_not_gif.png"))
    made.append("10_not_gif.png")

    # 11) 录屏工具常见的「带 alpha 通道帧」GIF: 读入后 transparency 可能是 RGB 元组,
    #     曾导致 Pillow 保存时抛 unsupported operand type(s) for &: 'tuple' and 'int'
    frames = []
    for i in range(60):
        rgba = Image.new("RGBA", (480, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(rgba)
        x = int(380 * i / 59)
        d.rounded_rectangle([x, 100, x + 90, 200], radius=14, fill=(7, 193, 96, 255))
        d.rectangle([20, 20, 460, 50], fill=(60, 60, 70, 255))
        frames.append(rgba)
    frames[0].save(os.path.join(OUT, "11_tuple_transparency.gif"), save_all=True,
                   append_images=frames[1:], duration=[40] * 60, loop=0,
                   disposal=2, transparency=0)
    made.append("11_tuple_transparency.gif")

    # 12) 深色 UI 录屏(延迟正常) / 13) 同一份像素但个别帧延迟异常
    dark_ui_recording(os.path.join(OUT, "12_dark_ui_recording.gif"))
    made.append("12_dark_ui_recording.gif")
    dark_ui_recording(os.path.join(OUT, "13_dark_ui_odd_delays.gif"), odd_delays=True)
    made.append("13_dark_ui_odd_delays.gif")

    # 14) 首帧调色板陷阱: 首段深色页面, 后段出现蓝色文件夹(颜色保真回归用)
    finder_dialog_recording(os.path.join(OUT, "14_finder_blue_folders.gif"))
    made.append("14_finder_blue_folders.gif")

    for name in made:
        p = os.path.join(OUT, name)
        print("%-28s %8.2f MB" % (name, os.path.getsize(p) / 1048576))


if __name__ == "__main__":
    main()
