#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gif_engine.py — 公众号 GIF 处理引擎

目标约束(微信公众号):
  - 文件体积 < 10MB
  - 总帧数 <= 300 帧

两种模式:
  auto  (智能):  分析 -> 延迟归一化 -> 已合规直通 -> 策略阶梯逐级加压, 达标即停
  manual(手动):  用户自选 抽帧/缩放/色彩数/抖动, 单次精确编码, 实时看到真实结果

所有优化选项的优缺点元数据集中在 OPTIONS_META, 前端直接渲染, 保证口径一致。

引擎优先级: ffmpeg(首选) -> gifsicle(后处理增强, 可选) -> Pillow(兜底)
已知坑: ffmpeg 的 fps 过滤器在「总时长x目标帧率 < 0.5」时会丢弃唯一帧,
        因此帧率必须带安全下限(见 _resolve_fps)。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # 录屏 GIF 可能很大, 关闭像素上限保护

MB = 1024 * 1024

DEFAULT_TARGET_MB = 9.5        # 留 0.5MB 余量, 防止平台计量误差
DEFAULT_MAX_FRAMES = 300
MIN_DELAY_MS = 20              # 低于此值浏览器按 100ms 渲染, 属于异常
BROWSER_MIN_DELAY_MS = 100     # 浏览器对 <20ms 延迟的实际渲染值
MAX_DELAY_MS = 1000            # 单帧延迟封顶, 修复导出器写出的超大延迟
FALLBACK_DELAY_MS = 40         # 延迟完全缺失时的默认值(约 25fps)

# ---------------------------------------------------------------------------
# 优化选项元数据: 前端渲染与报告描述共用同一份定义
# ---------------------------------------------------------------------------

OPTIONS_META = {
    "frame_drop": {
        "label": "抽帧",
        "desc": "按固定间隔丢弃帧, 直接减少帧数与文件体积",
        "options": {
            "keep_all": {
                "label": "不丢弃", "keep": 1.00,
                "pros": "动画节奏与原文件完全一致, 最流畅",
                "cons": "帧数不减, 长录屏容易超过 300 帧上限",
                "impact": "帧数不变",
            },
            "9in10": {
                "label": "每隔9帧丢1帧", "keep": 0.90,
                "pros": "几乎无感知, 只省 10% 体积",
                "cons": "节省有限, 一般只用于微调帧数",
                "impact": "帧数约 x0.9",
            },
            "4in5": {
                "label": "每隔4帧丢1帧", "keep": 0.80,
                "pros": "观感基本无变化, 帧数更安全",
                "cons": "体积只减少约 20%",
                "impact": "帧数约 x0.8",
            },
            "3in4": {
                "label": "每隔3帧丢1帧", "keep": 0.75,
                "pros": "流畅度影响很小, 体积减少 25%",
                "cons": "极快的连续动作可能有轻微卡顿感",
                "impact": "帧数约 x0.75",
            },
            "2in3": {
                "label": "每隔2帧丢1帧", "keep": 2 / 3,
                "pros": "体积减少约 1/3, 大多数录屏看不出区别",
                "cons": "帧率降为 2/3, 高速滚动场景略有不连贯",
                "impact": "帧数约 x0.67",
            },
            "1in2": {
                "label": "每隔1帧丢1帧", "keep": 0.50,
                "pros": "体积直接减半, 30fps 变 15fps 通常仍可接受",
                "cons": "帧率减半, 快速动画/滚动会明显卡顿",
                "impact": "帧数约 x0.5",
            },
        },
    },
    "scale": {
        "label": "缩放",
        "desc": "按比例缩小分辨率, 对体积的影响最大(像素面积决定数据量)",
        "options": {
            "1.0": {"label": "100% 原始尺寸", "value": 1.00,
                    "pros": "清晰度最高, 细节完整保留",
                    "cons": "体积最大, 高清录屏几乎必然超标",
                    "impact": "体积约不变"},
            "0.9": {"label": "90%", "value": 0.90,
                    "pros": "体积约减 19%, 肉眼几乎无差别",
                    "cons": "极小字号边缘略糊",
                    "impact": "体积约 x0.81"},
            "0.8": {"label": "80%", "value": 0.80,
                    "pros": "体积约减 36%, 常规推荐档位",
                    "cons": "小字可能略糊, 需留意可读性",
                    "impact": "体积约 x0.64"},
            "0.7": {"label": "70%", "value": 0.70,
                    "pros": "体积约减 51%, 文字仍大多可读",
                    "cons": "细节损失可见, 不适合小字号内容",
                    "impact": "体积约 x0.49"},
            "0.6": {"label": "60%", "value": 0.60,
                    "pros": "体积约减 64%, 适合内容简单的演示",
                    "cons": "文字边缘明显发虚",
                    "impact": "体积约 x0.36"},
            "0.5": {"label": "50%", "value": 0.50,
                    "pros": "体积约减 75%, 最后的清晰度保留档",
                    "cons": "仅适合演示动效, 不适合阅读型内容",
                    "impact": "体积约 x0.25"},
            "0.4": {"label": "40%", "value": 0.40,
                    "pros": "体积约减 84%",
                    "cons": "明显模糊, 只用于极限达标",
                    "impact": "体积约 x0.16"},
        },
    },
    "colors": {
        "label": "色彩数",
        "desc": "GIF 最多 256 色, 减少色彩数可压缩调色板与数据量",
        "options": {
            "256": {"label": "256 色(原始)", "value": 256,
                    "pros": "色彩无损, 照片/视频内容最保真",
                    "cons": "体积最大",
                    "impact": "体积约不变"},
            "192": {"label": "192 色", "value": 192,
                    "pros": "体积约减 8%, 肉眼几乎无差别",
                    "cons": "极端丰富的渐变色可能有细微色带",
                    "impact": "体积约 x0.78"},
            "128": {"label": "128 色", "value": 128,
                    "pros": "体积约减 20%, UI 录屏/纯色内容几乎无感知",
                    "cons": "照片类内容渐变处可能出现色带",
                    "impact": "体积约 x0.60"},
            "96": {"label": "96 色", "value": 96,
                    "pros": "体积约减 30%, 适合色彩简单的界面演示",
                    "cons": "照片/彩色插画失真可见",
                    "impact": "体积约 x0.52"},
            "64": {"label": "64 色", "value": 64,
                    "pros": "体积约减 40%, 纯色 UI 依然干净",
                    "cons": "彩色内容明显色带, 仅建议 UI 录屏使用",
                    "impact": "体积约 x0.43"},
            "48": {"label": "48 色", "value": 48,
                    "pros": "体积约减 48%",
                    "cons": "色彩丰富内容严重失真",
                    "impact": "体积约 x0.37"},
            "32": {"label": "32 色", "value": 32,
                    "pros": "体积约减 55%, 极限压缩档",
                    "cons": "仅适合极少色彩的图形动画",
                    "impact": "体积约 x0.30"},
        },
    },
    "dither": {
        "label": "抖动",
        "desc": "用有限颜色模拟更多色彩的方式, 影响渐变区域的表现",
        "options": {
            "none": {"label": "无抖动", "value": 0,
                     "pros": "文件更小, 文字和 UI 边缘最干净",
                     "cons": "渐变区域出现明显色带",
                     "impact": "同色彩数下体积最小"},
            "slight": {"label": "轻微抖动", "value": 5,
                       "pros": "体积与观感平衡, 通用推荐",
                       "cons": "平坦区域可能有极细微噪点",
                       "impact": "体积略增"},
            "medium": {"label": "明显抖动", "value": 3,
                       "pros": "渐变更自然, 适合照片类内容",
                       "cons": "文件略大, 细文字边缘有噪点",
                       "impact": "体积增加约 5-15%"},
            "strong": {"label": "强烈抖动", "value": 1,
                       "pros": "渐变最平滑",
                       "cons": "文件明显变大, 文字边缘毛糙",
                       "impact": "体积增加约 15-30%"},
        },
    },
}

FRAME_DROP_ORDER = ["keep_all", "9in10", "4in5", "3in4", "2in3", "1in2"]
SCALE_ORDER = ["1.0", "0.9", "0.8", "0.7", "0.6", "0.5", "0.4"]
COLORS_ORDER = ["256", "192", "128", "96", "64", "48", "32"]
DITHER_ORDER = ["none", "slight", "medium", "strong"]

# 手动模式常用组合(一键设置全部选项)
COMBO_PRESETS = [
    {"id": "frame_only", "name": "只抽帧", "desc": "画质不动, 靠减帧达标",
     "params": {"frame_drop": "1in2", "scale": "1.0", "colors": "256", "dither": "none"}},
    {"id": "scale_only", "name": "只缩放", "desc": "帧率不动, 缩小分辨率",
     "params": {"frame_drop": "keep_all", "scale": "0.8", "colors": "256", "dither": "none"}},
    {"id": "color_only", "name": "只减色", "desc": "尺寸帧率不动, 降色彩数",
     "params": {"frame_drop": "keep_all", "scale": "1.0", "colors": "128", "dither": "none"}},
    {"id": "mild", "name": "温和三件套", "desc": "轻度抽帧+缩放+减色",
     "params": {"frame_drop": "2in3", "scale": "0.9", "colors": "192", "dither": "slight"}},
    {"id": "aggressive", "name": "强力三件套", "desc": "抽帧+缩放+减色一起上",
     "params": {"frame_drop": "1in2", "scale": "0.8", "colors": "128", "dither": "slight"}},
]

# 智能模式策略阶梯: (缩放比例, 色彩数, 帧率保留比例)
LADDERS = {
    "balanced": [
        (1.00, 256, 1.00),
        (0.90, 256, 1.00),
        (0.90, 192, 1.00),
        (0.80, 192, 0.67),
        (0.80, 128, 0.67),
        (0.70, 128, 0.50),
        (0.70, 96, 0.50),
        (0.60, 96, 0.40),
        (0.60, 64, 0.40),
        (0.50, 64, 0.33),
        (0.45, 48, 0.33),
        (0.40, 32, 0.27),
    ],
    "quality": [
        (1.00, 256, 1.00),
        (0.95, 256, 1.00),
        (0.90, 256, 1.00),
        (0.90, 192, 1.00),
        (0.85, 192, 1.00),
        (0.85, 128, 1.00),
        (0.80, 128, 1.00),
        (0.80, 96, 1.00),
        (0.75, 96, 0.80),
        (0.70, 96, 0.80),
        (0.70, 64, 0.67),
        (0.60, 64, 0.67),
        (0.60, 48, 0.50),
        (0.50, 48, 0.50),
        (0.45, 32, 0.40),
        (0.40, 32, 0.40),
    ],
    "extreme": [
        (1.00, 256, 0.67),
        (0.80, 192, 0.67),
        (0.80, 128, 0.50),
        (0.70, 96, 0.50),
        (0.60, 64, 0.40),
        (0.50, 48, 0.33),
        (0.45, 32, 0.33),
        (0.40, 24, 0.27),
        (0.30, 16, 0.20),
    ],
}

PRESET_NAMES = {"balanced": "均衡", "quality": "画质优先", "extreme": "极限压缩"}


def _predict_size(size0: float, scale: float, colors: int, fps_ratio: float) -> float:
    """粗略体积模型: 像素面积 ~ scale^2, 色彩收益 ~ (colors/256)^0.75, 帧数线性"""
    return size0 * (scale ** 2) * ((colors / 256.0) ** 0.75) * fps_ratio


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def _which(name: str):
    return shutil.which(name)


def detect_engines() -> dict:
    """探测本机可用的压缩引擎"""
    engines = {"ffmpeg": None, "gifsicle": None, "pillow": True}
    if _which("ffmpeg"):
        try:
            out = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                                 text=True, timeout=10).stdout
            first = out.splitlines()[0] if out else "ffmpeg"
            engines["ffmpeg"] = first.split("Copyright")[0].strip() or "ffmpeg"
        except Exception:
            engines["ffmpeg"] = "ffmpeg"
    if _which("gifsicle"):
        engines["gifsicle"] = "gifsicle"
    return engines


def analyze(path: str) -> dict:
    """分析 GIF, 返回结构化信息; 文件有问题时抛异常, 由上层转换为友好错误"""
    if not os.path.isfile(path):
        raise ValueError("文件不存在")
    if os.path.getsize(path) == 0:
        raise ValueError("文件是空的(0 字节), 可能没有保存成功")
    with Image.open(path) as im:
        if im.format != "GIF":
            raise ValueError("不是 GIF 文件(检测到格式: %s), 本工具只处理 GIF" % im.format)
        width, height = im.size
        frames = 0
        durations = []
        transparency = False
        try:
            while True:
                im.seek(frames)
                durations.append(int(im.info.get("duration") or 0))
                if im.info.get("transparency") is not None:
                    transparency = True
                frames += 1
        except EOFError:
            pass
        if frames == 0:
            raise ValueError("GIF 中没有任何帧, 文件可能已损坏")
    duration_ms = sum(durations)
    duration_s = duration_ms / 1000.0
    fps = frames / duration_s if duration_s > 0 else 0.0
    bad_delays = (
        duration_ms <= 0
        or any(d <= 0 for d in durations)
        or any(d < MIN_DELAY_MS for d in durations)
        or any(d > 5000 for d in durations)
    )
    return {
        "path": path,
        "size_bytes": os.path.getsize(path),
        "width": width,
        "height": height,
        "frames": frames,
        "durations": durations,
        "duration_ms": duration_ms,
        "duration_s": duration_s,
        "fps": fps,
        "transparency": transparency,
        "bad_delays": bad_delays,
    }


def _summarize(info: dict) -> dict:
    return {
        "size_bytes": info["size_bytes"],
        "frames": info["frames"],
        "width": info["width"],
        "height": info["height"],
        "duration_s": round(info["duration_s"], 1),
        "fps": round(info["fps"], 1),
    }


# ---------------------------------------------------------------------------
# 帧延迟归一化(Pillow)
# ---------------------------------------------------------------------------


def _clamp_delay(d) -> int:
    if d is None or d <= 0:
        return FALLBACK_DELAY_MS
    if d < MIN_DELAY_MS:
        return BROWSER_MIN_DELAY_MS
    if d > MAX_DELAY_MS:
        return MAX_DELAY_MS
    return int(d)


def _normalize_delays(src: str, dst: str) -> None:
    """重写所有帧的延迟(Pillow 兜底路径, 会重新量化像素, 体积与画质都有损)

    仅在无损改写失败时才会走到这里, 见 _rewrite_delays_lossless。
    """
    with Image.open(src) as im:
        n, _ = _count_frames(im)
        frames, delays = [], []
        for i in range(n):
            im.seek(i)
            frames.append(im.convert("RGB"))
            delays.append(_clamp_delay(im.info.get("duration")))
    _save_frames_pil(frames, delays, dst, colors=256)


def _skip_sub_blocks(data: bytes, p: int) -> int:
    """跳过一串数据子块, 返回终止符之后的位置"""
    while data[p] != 0:
        p += data[p] + 1
    return p + 1


def _rewrite_delays_lossless(src: str, dst: str) -> None:
    """无损修复帧延迟: 直接改写 GIF 字节流里的 Graphic Control Extension

    为什么不用 Pillow 重新保存: 重存会把每一帧解码成 RGB 再重新量化(还带抖动),
    录屏工具原本做好的「只存差异区域」优化被整个抹掉, 实测 7.98MB 的 GIF 被撑到
    12.67MB, 后续再抽帧也压不回来, 用户看到的就是「帧数减半、体积反而变大」。
    延迟只是几个字节, 直接改字节, 像素数据一位不动。

    没有 GCE 的帧(延迟缺失)会补一个最简 GCE(无透明、无处置), 不影响画面。
    """
    with open(src, "rb") as f:
        data = f.read()
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("不是 GIF 字节流")

    def delay_bytes(cs: int) -> bytes:
        cs = max(1, min(65535, cs))
        return bytes((cs & 0xFF, cs >> 8))

    try:
        pos = 13
        if data[10] & 0x80:                      # 全局调色板
            pos += 3 * (2 << (data[10] & 7))
        out = bytearray(data[:pos])
        have_gce = False
        closed = False
        while pos < len(data):
            b = data[pos]
            if b == 0x3B:                        # 文件结尾
                out.append(0x3B)
                closed = True
                break
            if b == 0x21:                        # 扩展块
                if data[pos + 1] == 0xF9 and data[pos + 2] == 4:
                    old_ms = (data[pos + 4] | (data[pos + 5] << 8)) * 10
                    new_cs = round(_clamp_delay(old_ms) / 10)
                    out += data[pos:pos + 4]
                    out += delay_bytes(new_cs)
                    out += data[pos + 6:pos + 8]
                    have_gce = True
                    pos += 8
                else:
                    end = _skip_sub_blocks(data, pos + 2)
                    out += data[pos:end]
                    pos = end
            elif b == 0x2C:                      # 图像块
                if not have_gce:
                    out += b"\x21\xF9\x04\x00" + delay_bytes(
                        round(FALLBACK_DELAY_MS / 10)) + b"\x00\x00"
                packed = data[pos + 9]
                p = pos + 10
                if packed & 0x80:                # 局部调色板
                    p += 3 * (2 << (packed & 7))
                p += 1                           # LZW 最小码长
                end = _skip_sub_blocks(data, p)
                out += data[pos:end]
                pos = end
                have_gce = False
            else:
                raise ValueError("未知块标识 0x%02X @%d" % (b, pos))
        if not closed:
            out.append(0x3B)
    except IndexError:
        raise ValueError("GIF 字节流被截断, 无法无损改写")
    with open(dst, "wb") as f:
        f.write(out)


# ---------------------------------------------------------------------------
# 编码器
# ---------------------------------------------------------------------------


def _ffmpeg_encode(src: str, dst: str, *, width=None, colors=256, fps=None,
                   dither_scale=5, reserve_transparent=False, timeout=900):
    """ffmpeg 编码: fps 抽帧 + lanczos 缩放 + 全局调色板 + 差异区域编码"""
    with Image.open(src) as im:
        src_w = im.size[0]
    vf = []
    if fps and fps > 0:
        vf.append("fps=%g" % fps)
    if width and width < src_w:
        vf.append("scale=%d:-1:flags=lanczos" % int(width))
    # stats_mode=full: 统计整段动画的颜色分布, 生成一张真正的全局调色板。
    # 不能用 single: 它给每帧各出一张调色板, 但 paletteuse 默认只取第一张,
    # 结果整段动画只用「第 1 帧」的 256 色。第 1 帧是深色页面、后面才弹出访达窗口时,
    # 蓝色文件夹会被映射成最接近的灰/青绿(实测偏差 124, 改 full 后为 0)。
    palgen = "palettegen=max_colors=%d:stats_mode=full" % int(colors)
    if reserve_transparent:
        palgen += ":reserve_transparent=1"
    if dither_scale and dither_scale > 0:
        dither = "dither=bayer:bayer_scale=%d" % int(dither_scale)
    else:
        dither = "dither=none"
    paletteuse = "paletteuse=%s:diff_mode=rectangle" % dither
    vf.append("split[a][b];[a]%s[p];[b][p]%s" % (palgen, paletteuse))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", src, "-vf", ",".join(vf), "-loop", "0", "-f", "gif", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        raise RuntimeError("ffmpeg 编码失败: %s" % (proc.stderr.strip()[:300] or "未知错误"))


def _resample(delays, fps):
    """按目标帧率重采样(与 ffmpeg fps 过滤器同语义): 返回 (保留帧下标, 新延迟)"""
    if not fps or fps <= 0:
        return list(range(len(delays))), list(delays)
    keep, new_delays = [], []
    t = 0.0
    last_bucket = -1
    bucket_start = 0.0
    for i, d in enumerate(delays):
        b = int(t * fps / 1000.0)
        if b > last_bucket:
            if keep:
                new_delays.append(max(MIN_DELAY_MS, int(round(t - bucket_start))))
            keep.append(i)
            bucket_start = t
            last_bucket = b
        t += d
    if keep:
        new_delays.append(max(MIN_DELAY_MS, int(round(t - bucket_start))))
    return keep, new_delays


def _pil_encode(src: str, dst: str, *, width=None, colors=256, fps=None,
                max_frames=None) -> None:
    """Pillow 兜底编码: 重采样抽帧 + 缩放 + 全序列统一调色板"""
    with Image.open(src) as im:
        n, delays = _count_frames(im)
        total_ms = sum(delays) or (n * FALLBACK_DELAY_MS)
        src_fps = n / (total_ms / 1000.0) if total_ms > 0 else 25.0
        if fps and fps > 0 and src_fps > fps * 1.01:
            idxs, out_delays = _resample(delays, fps)
        else:
            idxs, out_delays = list(range(n)), list(delays)
        # 双保险: 仍超帧数上限就再隔帧抽
        if max_frames and len(idxs) > max_frames:
            step = -(-len(idxs) // max_frames)  # 向上取整
            idxs = idxs[::step]
            out_delays = [out_delays[i] * step for i in range(0, len(out_delays), step)]
        frames = []
        for i in idxs:
            im.seek(i)
            f = im.convert("RGB")
            if width and f.width > width:
                h = max(1, round(f.height * width / f.width))
                f = f.resize((width, h), Image.LANCZOS)
            frames.append(f)
    _save_frames_pil(frames, out_delays, dst, colors=colors)


def _strip_transparency(frames) -> None:
    """清理帧上的 transparency 元数据

    部分录屏/导出工具生成的 GIF, 其 transparency 会被 Pillow 读成 RGB 元组
    (如 (0,0,0))。GIF 只支持「调色板索引」这种整数透明度, 元组在保存时会走到
    Pillow 的 C 编码层做位与, 直接抛:
        unsupported operand type(s) for &: 'tuple' and 'int'
    这里统一清成合法整数索引, 非法值直接移除。
    """
    for f in frames:
        tp = f.info.get("transparency")
        if tp is None:
            continue
        if isinstance(tp, bool) or not isinstance(tp, int) or tp < 0 or tp > 255:
            f.info.pop("transparency", None)


def _global_palette_image(frames_rgb, n_colors: int, samples: int = 24):
    """从整段动画均匀抽样, 拼成一张「色卡」再量化, 得到覆盖全片的全局调色板

    只用第 1 帧取色会丢掉后面才出现的颜色(例如开头是深色页面、中途弹出的蓝色
    访达文件夹), 那些颜色会被映射成最接近的灰/青绿。
    """
    n = len(frames_rgb)
    k = min(samples, n)
    idxs = sorted({round(i * (n - 1) / max(1, k - 1)) for i in range(k)})
    thumbs = []
    for i in idxs:
        t = frames_rgb[i].copy()
        t.thumbnail((320, 320))
        thumbs.append(t)
    tw = max(t.width for t in thumbs)
    th = max(t.height for t in thumbs)
    cols = 1
    while cols * cols < len(thumbs):
        cols += 1
    rows = -(-len(thumbs) // cols)
    sheet = Image.new("RGB", (cols * tw, rows * th))
    for j, t in enumerate(thumbs):
        sheet.paste(t, ((j % cols) * tw, (j // cols) * th))
    return sheet.quantize(colors=n_colors, method=Image.MEDIANCUT)


def _save_frames_pil(frames_rgb, delays, dst: str, *, colors: int = 256) -> None:
    """用统一调色板保存帧序列(避免逐帧调色板导致的体积膨胀与闪烁)"""
    n_colors = max(2, min(256, int(colors)))
    pal = _global_palette_image(frames_rgb, n_colors)
    qframes = [f.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for f in frames_rgb]
    _strip_transparency(qframes)
    try:
        qframes[0].save(dst, save_all=True, append_images=qframes[1:],
                        duration=delays, loop=0, optimize=True)
    except (TypeError, ValueError):
        # 兜底: 个别畸形元数据在编码层仍可能报错, 清空全部元数据重试一次
        for f in qframes:
            f.info.clear()
        qframes[0].save(dst, save_all=True, append_images=qframes[1:],
                        duration=delays, loop=0, optimize=True)


def _gifsicle_optimize(src: str, dst: str, lossy: int = 30, timeout=300) -> None:
    """gifsicle 后处理增强(仅当本机安装了 gifsicle 才会走到)"""
    cmd = ["gifsicle", "-O3", "--lossy=%d" % lossy, "-i", src, "-o", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        raise RuntimeError("gifsicle 处理失败: %s" % proc.stderr.strip()[:200])


def _count_frames(im):
    n = 0
    durations = []
    try:
        while True:
            im.seek(n)
            durations.append(int(im.info.get("duration") or 0))
            n += 1
    except EOFError:
        pass
    return n, durations


# ---------------------------------------------------------------------------
# 参数解析: 把用户选项换算成具体的 fps / 目标宽度
# ---------------------------------------------------------------------------


def _resolve_fps(info: dict, keep_ratio: float, fps_limit) -> float | None:
    """
    计算目标帧率。三条约束:
      1. 不超过源帧率(只准抽, 不准补)
      2. 不超过 300 帧对应的帧率上限(留 2% 余量)
      3. 不低于 1/总时长 的安全下限(规避 ffmpeg fps 过滤器丢唯一帧的 bug)
    """
    base_fps = info["fps"] if info["fps"] > 0 else 25.0
    f = base_fps * keep_ratio
    if fps_limit and fps_limit < base_fps:
        f = min(f, fps_limit * 0.98)
    if info["duration_s"] > 0:
        min_safe = 1.0 / info["duration_s"] + 0.01
        f = max(f, min_safe)
    if f < base_fps - 0.01:
        return round(f, 1)
    return None


def _resolve_width(info: dict, scale: float, max_width):
    if scale >= 1.0 and not max_width:
        return None
    w = max(16, int(round(info["width"] * scale)))
    if max_width:
        w = min(w, int(max_width))
    if w < info["width"]:
        return w
    return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def process_gif(src: str, dst: str, *, target_mb: float = DEFAULT_TARGET_MB,
                max_frames: int = DEFAULT_MAX_FRAMES, max_width=None,
                preset: str = "balanced", dither: int = 5,
                mode: str = "auto", manual: dict | None = None,
                progress=None) -> dict:
    """
    把 src 处理成符合公众号要求的 GIF, 写入 dst, 返回处理报告。
    mode="auto"   智能模式: 策略阶梯自动加压
    mode="manual" 手动模式: 按 manual 指定参数单次编码
    progress(phase, pct, message) 为可选进度回调。
    """
    t0 = time.time()
    target_bytes = int(float(target_mb) * MB)
    max_frames = max(1, int(max_frames))
    if max_width:
        max_width = int(max_width)
    engines = detect_engines()
    techniques, warnings = [], []

    def rep(phase, pct, msg=""):
        if progress:
            try:
                progress(phase, pct, msg)
            except Exception:
                pass

    rep("analyzing", 3, "正在分析 GIF 结构")
    info = analyze(src)
    before = _summarize(info)

    tmpdir = tempfile.mkdtemp(prefix="gif_engine_")
    work_src = src
    try:
        # --- 1. 帧延迟归一化 ---
        if info["bad_delays"]:
            rep("analyzing", 8, "检测到帧延迟异常, 正在归一化")
            norm = os.path.join(tmpdir, "normalized.gif")
            try:
                # 首选: 只改延迟字节, 像素与差异编码原样保留
                _rewrite_delays_lossless(src, norm)
                norm_info = analyze(norm)
                if norm_info["frames"] != info["frames"]:
                    raise ValueError("帧数在改写后发生变化")
            except Exception:
                # 兜底: 字节流异常的畸形文件才走 Pillow 重编码
                _normalize_delays(src, norm)
                norm_info = analyze(norm)
            info = norm_info
            work_src = norm
            techniques.append("帧延迟归一化(修复卡顿与时序异常)")

        # --- 2. 帧数硬约束对应的帧率上限 ---
        fps_limit = (max_frames / info["duration_s"]) if info["duration_s"] > 0 else None
        frames_ok = info["frames"] <= max_frames

        # --- 3. 已合规 -> 直通(仅智能模式; 手动模式严格按用户参数编码) ---
        if mode != "manual" and info["size_bytes"] <= target_bytes and frames_ok:
            shutil.copyfile(work_src, dst)
            return _report(ok=True, passthrough=True, engine="passthrough",
                           before=before, after=_summarize(info),
                           techniques=techniques + ["文件已符合公众号要求, 原样保留"],
                           warnings=[], elapsed=time.time() - t0, settings=None)

        if mode == "manual":
            return _process_manual(src=work_src, dst=dst, info=info, before=before,
                                   target_bytes=target_bytes, target_mb=target_mb,
                                   max_frames=max_frames, max_width=max_width,
                                   fps_limit=fps_limit, manual=manual or {},
                                   engines=engines, techniques=techniques,
                                   warnings=warnings, tmpdir=tmpdir, rep=rep, t0=t0)
        return _process_auto(src=work_src, dst=dst, info=info, before=before,
                             target_bytes=target_bytes, target_mb=target_mb,
                             max_frames=max_frames, max_width=max_width,
                             fps_limit=fps_limit, preset=preset, dither=dither,
                             engines=engines, techniques=techniques,
                             warnings=warnings, tmpdir=tmpdir, rep=rep, t0=t0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _encode_once(work_src, out, *, width, colors, fps, dither_scale,
                 reserve_transparent, engines, info, max_frames):
    """编码一次; 若带抽帧的 ffmpeg 编码失败, 自动重试为不抽帧"""
    if engines["ffmpeg"]:
        try:
            _ffmpeg_encode(work_src, out, width=width, colors=colors, fps=fps,
                           dither_scale=dither_scale,
                           reserve_transparent=reserve_transparent)
        except Exception:
            if fps:
                # 规避个别极端情况下 fps 过滤器丢帧的问题: 去掉抽帧重试
                _ffmpeg_encode(work_src, out, width=width, colors=colors, fps=None,
                               dither_scale=dither_scale,
                               reserve_transparent=reserve_transparent)
            else:
                raise
    else:
        if info["transparency"]:
            pass  # 警告由调用方统一添加
        _pil_encode(work_src, out, width=width, colors=colors, fps=fps,
                    max_frames=max_frames)


def _opt_value(group: str, raw, default):
    """把手动选项翻译成数值。

    前端传的是选项 ID(如 dither="none"/"slight", colors="128", scale="0.7"),
    CLI 和旧调用方传的是数字本身; 这里两种都接受, 并对非法值回落到默认值,
    避免一个脏参数让整个任务失败。
    """
    if raw is None or raw == "":
        return default
    opts = OPTIONS_META[group]["options"]
    if isinstance(raw, str) and raw in opts and "value" in opts[raw]:
        return opts[raw]["value"]
    try:
        return float(raw) if group == "scale" else int(float(raw))
    except (TypeError, ValueError):
        return default


def _process_manual(*, src, dst, info, before, target_bytes, target_mb, max_frames,
                    max_width, fps_limit, manual, engines, techniques, warnings,
                    tmpdir, rep, t0):
    """手动模式: 严格按用户选择的参数编码一次"""
    rep("compressing", 30, "正在按你的设置编码")
    frame_drop = manual.get("frame_drop", "keep_all")
    scale = float(_opt_value("scale", manual.get("scale"), 1.0))
    colors = int(_opt_value("colors", manual.get("colors"), 256))
    dither = int(_opt_value("dither", manual.get("dither"), 0))

    keep = OPTIONS_META["frame_drop"]["options"].get(frame_drop, {}).get("keep", 1.0)
    drop_label = OPTIONS_META["frame_drop"]["options"].get(frame_drop, {}).get("label", "不丢弃")
    fps = _resolve_fps(info, keep, fps_limit)
    width = _resolve_width(info, scale, max_width)

    # 300 帧是硬约束: 用户选择会导致超帧时, 自动补刀并明确告知
    forced = False
    if fps is None and fps_limit and fps_limit < info["fps"]:
        fps = _resolve_fps(info, 0.5, fps_limit)
        forced = True

    if engines["ffmpeg"] is None and info["transparency"]:
        warnings.append("当前使用 Pillow 兜底引擎, 透明区域已合并为白底")

    out = os.path.join(tmpdir, "manual.gif")
    _encode_once(src, out, width=width, colors=colors, fps=fps,
                 dither_scale=dither, reserve_transparent=info["transparency"],
                 engines=engines, info=info, max_frames=max_frames)
    out_info = analyze(out)
    rep("finalizing", 92, "正在写入结果")

    settings = {
        "frame_drop": frame_drop, "frame_drop_label": drop_label,
        "scale": scale, "colors": colors, "dither": dither,
        "fps": fps, "width": width,
    }
    techniques.extend(_describe_manual(settings, info, engines))
    if info["transparency"]:
        techniques.append("透明区域已保留")
    if forced:
        warnings.append("你选择了不抽帧, 但原文件帧数超过 %d 帧上限, 已自动抽帧至 %d 帧"
                        % (max_frames, out_info["frames"]))
    if out_info["frames"] > max_frames:
        warnings.append("输出仍有 %d 帧, 超过 %d 帧上限, 请提高抽帧强度"
                        % (out_info["frames"], max_frames))
    if out_info["size_bytes"] > before["size_bytes"] * 1.02:
        warnings.append("处理后(%.2fMB)比原文件(%.2fMB)还大: 原文件已经是录屏工具优化过的紧凑编码, "
                        "按当前设置重新编码反而更占空间。建议加大缩放/减色, 或改用智能模式"
                        % (out_info["size_bytes"] / MB, before["size_bytes"] / MB))
    ok = out_info["size_bytes"] <= target_bytes and out_info["frames"] <= max_frames
    if not ok and out_info["size_bytes"] > target_bytes:
        warnings.append("按当前设置体积为 %.1fMB, 仍超出 %.1fMB 目标; 可加大抽帧/缩放/减色, 或点「智能压缩」自动达标"
                        % (out_info["size_bytes"] / MB, target_mb))
    return _finish(dst, out, out_info, info, before, engines, techniques,
                   warnings, max_frames, t0, rep, ok=ok, settings=settings)


def _process_auto(*, src, dst, info, before, target_bytes, target_mb, max_frames,
                  max_width, fps_limit, preset, dither, engines, techniques,
                  warnings, tmpdir, rep, t0):
    """智能模式: 策略阶梯逐级加压, 达标即停"""
    rep("compressing", 12, "开始压缩")
    ladder = LADDERS.get(preset, LADDERS["balanced"])
    base_fps = info["fps"] if info["fps"] > 0 else 25.0
    best = None  # (size, path, params_desc)

    def attempt_params(idx):
        """把阶梯参数换算成具体的 fps / 目标宽度 / 色彩数"""
        scale, colors, fps_ratio = ladder[idx]
        fps = _resolve_fps(info, fps_ratio, fps_limit)
        width = _resolve_width(info, scale, max_width)
        return (scale, colors, fps, width)

    def run_attempt(idx):
        scale, colors, fps, width = attempt_params(idx)
        out = os.path.join(tmpdir, "attempt_%02d.gif" % idx)
        _encode_once(src, out, width=width, colors=colors, fps=fps,
                     dither_scale=dither, reserve_transparent=info["transparency"],
                     engines=engines, info=info, max_frames=max_frames)
        return out, analyze(out), (scale, colors, fps, width)

    # --- 4a. 基线尝试: 纯优化(全局调色板 + 差异编码), 不动任何画质参数 ---
    rep("compressing", 15, "第 1/%d 级压缩: 纯优化(不损失画质)" % len(ladder))
    try:
        out, out_info, params = run_attempt(0)
        if out_info["frames"] <= max_frames:
            best = (out_info["size_bytes"], out, params)
            if out_info["size_bytes"] <= target_bytes:
                return _hit_finish(dst, out, out_info, params, info, before,
                                   engines, techniques, warnings, max_frames,
                                   base_fps, t0, rep)
    except Exception as e:
        warnings.append("基线压缩失败: %s" % e)

    # --- 4b. 体积模型预测: 跳过明显不够劲的级别 ---
    size0 = best[0] if best else info["size_bytes"]
    pred_idx = 1
    if size0 > target_bytes:
        for i in range(1, len(ladder)):
            s, c, rho = ladder[i]
            if _predict_size(size0, s, c, rho) <= target_bytes:
                pred_idx = i
                break
        else:
            pred_idx = len(ladder) - 1

    # --- 4c. 从预测级别开始, 成对并行尝试, 达标即停 ---
    remaining = list(range(pred_idx, len(ladder)))
    pool = ThreadPoolExecutor(max_workers=2)
    hit = None
    try:
        while remaining and hit is None:
            batch = remaining[:2]
            remaining = remaining[2:]
            futs = {pool.submit(run_attempt, i): i for i in batch}
            hits = []
            for fut in as_completed(futs):
                i = futs[fut]
                params = attempt_params(i)
                rep("compressing", 20 + int(72 * i / max(1, len(ladder))),
                    "第 %d/%d 级压缩: %dpx / %d 色 / %s" % (
                        i + 1, len(ladder), params[3] or info["width"], params[1],
                        ("%.4gfps" % params[2]) if params[2] else "原始帧率"))
                try:
                    out, out_info, params = fut.result()
                except Exception as e:
                    warnings.append("第 %d 级编码失败: %s" % (i + 1, e))
                    continue
                if out_info["frames"] > max_frames:
                    continue  # 帧数仍超限, 继续加压
                if best is None or out_info["size_bytes"] < best[0]:
                    best = (out_info["size_bytes"], out, params)
                if out_info["size_bytes"] <= target_bytes:
                    hits.append((i, out, out_info, params))
            if hits:
                hits.sort(key=lambda h: h[0])  # 同级并行时取画质更好(更不激进)的
                hit = hits[0]
    finally:
        pool.shutdown(wait=True)

    # --- 5. 收尾: 达标 or 尽力而为 ---
    if hit is None:
        if best is None:
            raise RuntimeError("所有压缩策略都失败了, 请检查文件是否损坏")
        size, out, params = best
        warnings.append("已使用极限压缩, 但仍为 %.1fMB, 超出目标 %.1fMB; 建议缩短录制时长或降低录制分辨率"
                        % (size / MB, target_mb))
        shutil.copyfile(out, dst)
        final_info = analyze(dst)
        techniques.extend(_describe_auto(params, info, base_fps, engines,
                                         max_frames, final_info["frames"]))
        if info["transparency"]:
            techniques.append("透明区域已保留")
        return _report(ok=False, passthrough=False,
                       engine="ffmpeg" if engines["ffmpeg"] else "pillow",
                       before=before, after=_summarize(final_info),
                       techniques=techniques, warnings=warnings,
                       elapsed=time.time() - t0, settings=_auto_settings(params, info))
    return _hit_finish(dst, hit[1], hit[2], hit[3], info, before, engines,
                       techniques, warnings, max_frames, base_fps, t0, rep)


def _auto_settings(params, info):
    scale, colors, fps, width = params
    return {"scale": scale, "colors": colors, "fps": fps, "width": width}


def _hit_finish(dst, out, out_info, params, info, before, engines, techniques,
                warnings, max_frames, base_fps, t0, rep):
    """智能模式达标: 补充压缩手段描述后走统一收尾"""
    techniques.extend(_describe_auto(params, info, base_fps, engines,
                                     max_frames, out_info["frames"]))
    if info["transparency"]:
        techniques.append("透明区域已保留")
    return _finish(dst, out, out_info, info, before, engines, techniques,
                   warnings, max_frames, t0, rep, ok=True,
                   settings=_auto_settings(params, info))


def _finish(dst, out, out_info, info, before, engines, techniques, warnings,
            max_frames, t0, rep, ok, settings):
    """达标路径: gifsicle 增强(可选) + 落盘 + 生成报告"""
    rep("finalizing", 96, "正在写入结果")
    if engines["gifsicle"]:
        try:
            gs = os.path.join(os.path.dirname(out), "gifsicle.gif")
            _gifsicle_optimize(out, gs)
            gi = analyze(gs)
            if gi["frames"] <= max_frames and gi["size_bytes"] < out_info["size_bytes"]:
                out, out_info = gs, gi
                techniques.append("gifsicle 后处理增强")
        except Exception:
            pass
    shutil.copyfile(out, dst)
    final_info = analyze(dst)
    rep("finalizing", 100, "完成")
    return _report(ok=ok, passthrough=False,
                   engine="ffmpeg" if engines["ffmpeg"] else "pillow",
                   before=before, after=_summarize(final_info),
                   techniques=techniques, warnings=warnings,
                   elapsed=time.time() - t0, settings=settings)


def _describe_manual(settings, info, engines) -> list:
    """手动模式: 精确描述用户选择的每一项"""
    out = []
    if engines["ffmpeg"]:
        out.append("全局调色板 + 差异区域编码")
    fd = settings["frame_drop"]
    if fd != "keep_all":
        out.append("%s(保留 %d%%)" % (settings["frame_drop_label"],
                                      round(OPTIONS_META["frame_drop"]["options"][fd]["keep"] * 100)))
    elif settings.get("fps"):
        out.append("自动抽帧以满足 300 帧上限")
    if settings.get("width"):
        out.append("分辨率缩放 %d→%dpx(%d%%)" % (info["width"], settings["width"],
                                                round(settings["scale"] * 100)))
    if settings["colors"] < 256:
        out.append("色彩数降至 %d" % settings["colors"])
    d = {0: "无", 5: "轻微", 3: "明显", 1: "强烈"}.get(settings["dither"], "轻微")
    out.append("抖动: %s" % d)
    return out


def _describe_auto(params, info, base_fps, engines, max_frames, after_frames) -> list:
    """智能模式: 把生效的参数翻译成人类可读的压缩手段"""
    scale, colors, fps, width = params
    out = []
    if engines["ffmpeg"]:
        out.append("全局调色板 + 差异区域编码")
    if width and width < info["width"]:
        out.append("分辨率缩放 %d→%dpx(%d%%)" % (info["width"], width, round(scale * 100)))
    if colors < 256:
        out.append("色彩数 256→%d" % colors)
    if fps and fps < base_fps - 0.01:
        out.append("帧率 %.4g→%.4gfps(自动抽帧)" % (base_fps, fps))
    if info["frames"] > max_frames:
        out.append("帧数 %d→%d(满足 %d 帧上限)" % (info["frames"], after_frames, max_frames))
    return out


def _report(*, ok, passthrough, engine, before, after, techniques, warnings,
            elapsed, settings) -> dict:
    size_before = before["size_bytes"]
    size_after = after["size_bytes"]
    saved = (1 - size_after / size_before) * 100 if size_before else 0.0
    return {
        "ok": ok,
        "passthrough": passthrough,
        "engine": engine,
        "before": before,
        "after": after,
        "saved_pct": round(saved, 1),
        "techniques": techniques,
        "warnings": warnings,
        "elapsed_s": round(elapsed, 1),
        "settings": settings,
    }
