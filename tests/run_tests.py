#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests.py — 全场景验证: 每个测试 GIF 过一遍引擎, 校验公众号约束"""

import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gif_engine import (analyze, process_gif, OPTIONS_META,  # noqa: E402
                        _save_frames_pil, _strip_transparency,
                        _rewrite_delays_lossless, _pil_encode)

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

MB = 1048576


def fmt(b):
    return "%.2fMB" % (b / MB)


def check(name, src, target_mb=9.5, max_frames=300, expect_error=False, **kw):
    dst = os.path.join(OUT, name.replace(".gif", "") + "_out.gif")
    print("=" * 72)
    print("用例: %s   (目标 %.1fMB / %d帧)" % (name, target_mb, max_frames))
    try:
        rep = process_gif(src, dst, target_mb=target_mb, max_frames=max_frames, **kw)
    except Exception as e:
        if expect_error:
            print("  预期内错误: %s" % e)
            print("  结果: [PASS] 错误被友好处理")
            return True
        print("  未预期错误: %s" % e)
        traceback.print_exc()
        return False
    if expect_error:
        print("  结果: [FAIL] 本该报错却处理成功了")
        return False
    b, a = rep["before"], rep["after"]
    print("  体积: %s -> %s (省 %.1f%%)" % (fmt(b["size_bytes"]), fmt(a["size_bytes"]), rep["saved_pct"]))
    print("  帧数: %d -> %d" % (b["frames"], a["frames"]))
    print("  尺寸: %dx%d -> %dx%d" % (b["width"], b["height"], a["width"], a["height"]))
    print("  手段: %s" % " | ".join(rep["techniques"]))
    if rep["warnings"]:
        print("  警告: %s" % "; ".join(rep["warnings"]))
    print("  耗时: %.1fs  引擎: %s  ok=%s" % (rep["elapsed_s"], rep["engine"], rep["ok"]))
    problems = []
    if rep["ok"]:
        if a["size_bytes"] >= target_mb * MB:
            problems.append("体积仍超标 %s" % fmt(a["size_bytes"]))
        if a["frames"] > max_frames:
            problems.append("帧数仍超限 %d" % a["frames"])
    try:
        info = analyze(dst)
        if info["size_bytes"] != a["size_bytes"]:
            problems.append("报告体积与实际不符")
        if info["frames"] != a["frames"]:
            problems.append("报告帧数与实际不符")
    except Exception as e:
        problems.append("输出文件无法解析: %s" % e)
    if problems:
        print("  结果: [FAIL] %s" % "; ".join(problems))
        return False
    print("  结果: [PASS]")
    return True


def main():
    cases = [
        # ---- 智能模式 ----
        ("01_small_ok.gif", 9.5, 300, False, {"mode": "auto"}),
        ("02_too_many_frames.gif", 9.5, 300, False, {"mode": "auto"}),
        ("03_too_big.gif", 9.5, 300, False, {"mode": "auto"}),
        ("04_big_and_many.gif", 9.5, 300, False, {"mode": "auto"}),
        ("05_hires_screen.gif", 9.5, 300, False, {"mode": "auto"}),
        ("06_transparent.gif", 9.5, 300, False, {"mode": "auto"}),
        ("07_static_big.gif", 1.0, 300, False, {"mode": "auto"}),
        ("08_bad_delays.gif", 9.5, 300, False, {"mode": "auto"}),
        ("09_broken.gif", 9.5, 300, True, {"mode": "auto"}),
        ("10_not_gif.png", 9.5, 300, True, {"mode": "auto"}),
        # ---- 手动模式 ----
        # 单帧 GIF 抽帧(曾经触发 ffmpeg 丢帧 bug 的场景)
        ("07_static_big.gif[手动:每隔1帧丢1帧]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "1in2", "scale": 0.7,
                                       "colors": 96, "dither": 0}}),
        # 手动: 只抽帧, 其他不动
        ("02_too_many_frames.gif[手动:只抽帧]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "1in2", "scale": 1.0,
                                       "colors": 256, "dither": 0}}),
        # 手动: 三件套强力组合
        ("03_too_big.gif[手动:强力三件套]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "1in2", "scale": 0.7,
                                       "colors": 128, "dither": 3}}),
        # 手动: 温和组合
        ("05_hires_screen.gif[手动:温和三件套]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "2in3", "scale": 0.9,
                                       "colors": 192, "dither": 5}}),
        # 手动: 极弱参数 -> 允许不达标, 但必须给出警告且不崩溃
        ("03_too_big.gif[手动:全部关闭]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "keep_all", "scale": 1.0,
                                       "colors": 256, "dither": 0}}),
        # 手动: 透明保留
        ("06_transparent.gif[手动:1in2+80%+128色]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "1in2", "scale": 0.8,
                                       "colors": 128, "dither": 0}}),
        # 手动: 极限小帧率(验证安全下限)
        ("04_big_and_many.gif[手动:1in2+50%+48色]", 9.5, 300, False,
         {"mode": "manual", "manual": {"frame_drop": "1in2", "scale": 0.5,
                                       "colors": 48, "dither": 0}}),
    ]
    results = []
    for name, tgt, mf, err, kw in cases:
        src = os.path.join(FIX, name.split("[")[0])
        results.append(check(name, src, tgt, mf, err, **kw))
    print("=" * 72)
    print("透明保留检查:")
    dst = os.path.join(OUT, "06_transparent_out.gif")
    if os.path.exists(dst):
        info = analyze(dst)
        print("  输出 transparency = %s (期望 True)" % info["transparency"])
        results.append(info["transparency"] is True)
    print("=" * 72)
    print("选项元数据自检:")
    for group in ("frame_drop", "scale", "colors", "dither"):
        opts = OPTIONS_META[group]["options"]
        missing = [k for k, v in opts.items() if not v.get("pros") or not v.get("cons")]
        print("  %-12s %d 个选项, 优缺点完整: %s" % (group, len(opts), "是" if not missing else "缺 %s" % missing))
        results.append(not missing)
    print("=" * 72)
    print("畸形元数据防御(录屏 GIF 的元组透明信息):")
    # 复现 Pillow 崩溃: 帧上带元组 transparency 时, C 编码层做位与会抛
    # unsupported operand type(s) for &: 'tuple' and 'int'
    from PIL import Image
    src_tp = os.path.join(FIX, "05_hires_screen.gif")
    bad = []
    with Image.open(src_tp) as im:
        for i in range(3):
            im.seek(i)
            f = im.convert("RGB")
            f.info["transparency"] = (0, 0, 0)  # 模拟畸形元数据
            bad.append(f)
    out_bad = os.path.join(OUT, "11_tuple_transparency.gif")
    try:
        _save_frames_pil(bad, [40, 40, 40], out_bad, colors=128)
        ok = os.path.isfile(out_bad) and os.path.getsize(out_bad) > 0
        print("  带元组 transparency 的帧序列保存: %s" % ("成功" if ok else "失败"))
    except Exception as e:
        print("  带元组 transparency 的帧序列保存: 崩溃 -> %s" % e)
        ok = False
    results.append(ok)
    # 完整流程: 同一份帧走 _strip_transparency 后不得残留非法类型
    qf = bad[:1]
    _strip_transparency(qf)
    tp = qf[0].info.get("transparency")
    legal = tp is None or (isinstance(tp, int) and not isinstance(tp, bool) and 0 <= tp <= 255)
    print("  清理后 transparency = %r (合法: %s)" % (tp, "是" if legal else "否"))
    results.append(legal)
    print("=" * 72)
    print("延迟归一化不得膨胀体积(用户反馈: 每隔1帧丢1帧, 帧数减半体积反而 +12%):")
    import tempfile
    from PIL import ImageChops, Image as _Image
    odd = os.path.join(FIX, "13_dark_ui_odd_delays.gif")
    if os.path.exists(odd):
        a = analyze(odd)
        tmpd = tempfile.mkdtemp()
        norm = os.path.join(tmpd, "norm.gif")
        _rewrite_delays_lossless(odd, norm)
        b = analyze(norm)
        ok1 = b["frames"] == a["frames"] and not b["bad_delays"]
        print("  无损改写: %d帧 -> %d帧, 延迟异常 %s -> %s" % (
            a["frames"], b["frames"], a["bad_delays"], b["bad_delays"]))
        results.append(ok1)
        ok2 = b["size_bytes"] <= a["size_bytes"] * 1.01
        print("  改写后体积 %.2fMB (原 %.2fMB), 不得膨胀: %s" % (
            b["size_bytes"] / MB, a["size_bytes"] / MB, "是" if ok2 else "否"))
        results.append(ok2)
        bad_px = 0
        with _Image.open(odd) as x, _Image.open(norm) as y:
            for i in range(0, a["frames"], 7):
                x.seek(i); y.seek(i)
                if ImageChops.difference(x.convert("RGB"), y.convert("RGB")).getbbox():
                    bad_px += 1
        print("  抽查帧像素差异数: %d (期望 0)" % bad_px)
        results.append(bad_px == 0)
        # 端到端: 手动「每隔1帧丢1帧」, 体积必须下降而不是上升
        out = os.path.join(tmpd, "o.gif")
        rep = process_gif(odd, out, target_mb=9.5, max_frames=300, mode="manual",
                          manual={"frame_drop": "1in2", "scale": "1.0",
                                  "colors": "256", "dither": "none"})
        ok3 = rep["after"]["size_bytes"] < rep["before"]["size_bytes"] \
            and rep["after"]["frames"] <= rep["before"]["frames"] * 0.55
        print("  手动抽帧: %.2fMB -> %.2fMB, %d -> %d 帧, 体积下降且帧数减半: %s" % (
            rep["before"]["size_bytes"] / MB, rep["after"]["size_bytes"] / MB,
            rep["before"]["frames"], rep["after"]["frames"], "是" if ok3 else "否"))
        results.append(ok3)
        shutil.rmtree(tmpd, ignore_errors=True)
    else:
        print("  (跳过: 缺少 13_dark_ui_odd_delays.gif, 先运行 make_test_gifs.py)")
    print("=" * 72)
    print("颜色保真(用户反馈: 访达蓝色文件夹处理后变青绿 —— 首帧调色板陷阱):")
    import math
    fin = os.path.join(FIX, "14_finder_blue_folders.gif")
    if os.path.exists(fin):
        PT, BLUE = (152, 280), (104, 178, 234)

        def _px(path, idx):
            with _Image.open(path) as im:
                im.seek(min(idx, im.n_frames - 1))
                return im.convert("RGB").getpixel(PT)

        def _dev(c):
            return math.sqrt(sum((a - b) ** 2 for a, b in zip(c, BLUE)))

        tmpc = tempfile.mkdtemp()
        # 1) 完整流程: 手动「每隔1帧丢1帧」
        out = os.path.join(tmpc, "o.gif")
        process_gif(fin, out, target_mb=9.5, max_frames=300, mode="manual",
                    manual={"frame_drop": "1in2", "scale": "1.0",
                            "colors": "256", "dither": "none"})
        c = _px(out, 15)
        ok = _dev(c) < 12
        print("  ffmpeg 路径: 文件夹色 %s, 偏差 %.1f (须 < 12): %s" % (c, _dev(c), "是" if ok else "否"))
        results.append(ok)
        # 2) Pillow 兜底路径
        out2 = os.path.join(tmpc, "p.gif")
        _pil_encode(fin, out2, width=None, colors=256, fps=None)
        c2 = _px(out2, 30)
        ok2 = _dev(c2) < 25
        print("  Pillow 路径: 文件夹色 %s, 偏差 %.1f (须 < 25): %s" % (c2, _dev(c2), "是" if ok2 else "否"))
        results.append(ok2)
        shutil.rmtree(tmpc, ignore_errors=True)
    else:
        print("  (跳过: 缺少 14_finder_blue_folders.gif, 先运行 make_test_gifs.py)")
    print("=" * 72)
    passed = sum(1 for r in results if r)
    print("总计: %d/%d 通过" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
