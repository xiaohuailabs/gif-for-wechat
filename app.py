#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — 公众号 GIF 工具: Web 服务 + CLI 双模式

启动 Web 服务:
    python3 app.py                # 默认 http://127.0.0.1:8600
    python3 app.py --port 9000    # 指定端口

命令行处理单个文件:
    python3 app.py input.gif                      # 智能压缩
    python3 app.py input.gif -o out.gif           # 指定输出
    python3 app.py input.gif --frame-drop 1in2 --scale 0.8 --colors 128
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_file, send_from_directory
from concurrent.futures import ThreadPoolExecutor

import gif_engine

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1GB, 录屏 GIF 可能很大

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

JOBS = {}


def _to_int(value, default):
    """把前端可能传来的任意值安全转成 int。

    前端选项是以字符串 ID 提交的(如 dither="none"、colors="128"), 直接 int() 会抛
    ValueError("invalid literal for int() with base 10: 'none'") 并让整个任务失败。
    这里统一兜住: None/空串/非法值都回落到默认值。
    """
    if value is None or value == "" or value == "none":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
JOBS_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2)


# ---------------------------------------------------------------------------
# 任务处理
# ---------------------------------------------------------------------------


def _start_processing(job, mode, params):
    """(重)启一个处理任务; run_id 用于丢弃被用户操作取代的旧任务"""
    with JOBS_LOCK:
        job["run_id"] = job.get("run_id", 0) + 1
        run_id = job["run_id"]
        job["status"] = "running"
        job["progress"] = 0
        job["phase"] = "queued"
        job["message"] = "排队中"
        job["error"] = None
    EXECUTOR.submit(_run_job, job["id"], run_id, mode, params)


def _run_job(job_id, run_id, mode, params):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return

    def superseded():
        return job.get("run_id") != run_id

    def progress(phase, pct, msg):
        if superseded():
            return
        job["phase"] = phase
        job["progress"] = pct
        job["message"] = msg

    try:
        dst = os.path.join(OUTPUT_DIR, job_id + ".gif")
        report = gif_engine.process_gif(
            job["src"], dst,
            target_mb=params.get("target_mb", gif_engine.DEFAULT_TARGET_MB),
            max_frames=params.get("max_frames", gif_engine.DEFAULT_MAX_FRAMES),
            max_width=params.get("max_width") or None,
            preset=params.get("preset", "balanced"),
            dither=_to_int(params.get("dither"), 5),
            mode=mode,
            manual=params.get("manual"),
            progress=progress,
        )
        if superseded():
            return
        report["result_url"] = "/api/result/%s" % job_id
        report["original_url"] = "/api/original/%s" % job_id
        report["download_url"] = "/api/download/%s" % job_id
        job["result"] = report
        job["status"] = "done"
        job["progress"] = 100
        job["message"] = "完成"
    except Exception as e:
        if superseded():
            return
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = "处理失败"


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/meta")
def api_meta():
    """前端渲染选项所需的一切元数据(与引擎共用同一份定义)"""
    return jsonify({
        "engines": gif_engine.detect_engines(),
        "options_meta": gif_engine.OPTIONS_META,
        "frame_drop_order": gif_engine.FRAME_DROP_ORDER,
        "scale_order": gif_engine.SCALE_ORDER,
        "colors_order": gif_engine.COLORS_ORDER,
        "dither_order": gif_engine.DITHER_ORDER,
        "combos": gif_engine.COMBO_PRESETS,
        "presets": gif_engine.PRESET_NAMES,
        "defaults": {
            "target_mb": gif_engine.DEFAULT_TARGET_MB,
            "max_frames": gif_engine.DEFAULT_MAX_FRAMES,
            "preset": "balanced",
        },
    })


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "没有收到文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext != ".gif":
        return jsonify({"error": "只支持 GIF 文件(收到 %s), 请先导出为 GIF" % (ext or "未知格式")}), 400

    job_id = uuid.uuid4().hex[:12]
    src = os.path.join(UPLOAD_DIR, job_id + ".gif")
    try:
        f.save(src)
    except Exception as e:
        return jsonify({"error": "文件保存失败: %s" % e}), 500

    # 立即分析, 有问题直接反馈, 不进入队列
    try:
        info = gif_engine.analyze(src)
    except Exception as e:
        os.unlink(src)
        return jsonify({"error": str(e)}), 400

    params = {
        "target_mb": float(request.form.get("target_mb") or gif_engine.DEFAULT_TARGET_MB),
        "max_frames": _to_int(request.form.get("max_frames"), gif_engine.DEFAULT_MAX_FRAMES),
        "max_width": _to_int(request.form.get("max_width"), 0) or None,
        "preset": request.form.get("preset") or "balanced",
        "dither": _to_int(request.form.get("dither"), 5),
    }
    mode = request.form.get("mode") or "auto"
    manual_raw = request.form.get("manual")
    manual = None
    if manual_raw:
        try:
            manual = json.loads(manual_raw)
        except (ValueError, TypeError):
            manual = None
    job = {
        "id": job_id,
        "name": f.filename,
        "src": src,
        "original": gif_engine._summarize(info),
        "status": "ready",
        "progress": 0,
        "phase": "ready",
        "message": "等待开始",
        "result": None,
        "error": None,
        "created": time.time(),
        "run_id": 0,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    # 上传只做分析与入队; 是否立刻开工由调用方决定(CLI 立刻跑, Web 端等用户点「开始」)
    if request.form.get("auto_start") == "1":
        _start_processing(job, mode, params if manual is None else dict(params, manual=manual))
    return jsonify({"job_id": job_id, "original": job["original"]})


@app.route("/api/process", methods=["POST"])
def api_process():
    """对手动模式重新编码: 同一文件换一套参数"""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在, 请重新上传文件"}), 404
    if not os.path.isfile(job["src"]):
        return jsonify({"error": "源文件已被清理, 请重新上传"}), 410
    mode = data.get("mode") or "manual"
    params = {
        "target_mb": float(data.get("target_mb") or gif_engine.DEFAULT_TARGET_MB),
        "max_frames": _to_int(data.get("max_frames"), gif_engine.DEFAULT_MAX_FRAMES),
        "max_width": _to_int(data.get("max_width"), 0) or None,
        "preset": data.get("preset") or "balanced",
        "dither": _to_int(data.get("dither"), 5),
        "manual": data.get("manual"),
    }
    _start_processing(job, mode, params)
    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/job/<job_id>")
def api_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({
        "id": job["id"],
        "name": job["name"],
        "original": job["original"],
        "status": job["status"],
        "progress": job["progress"],
        "phase": job["phase"],
        "message": job["message"],
        "error": job["error"],
        "result": job["result"],
    })


@app.route("/api/original/<job_id>")
def api_original(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not os.path.isfile(job["src"]):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(job["src"], mimetype="image/gif")


@app.route("/api/result/<job_id>")
def api_result(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    dst = os.path.join(OUTPUT_DIR, job_id + ".gif")
    if not os.path.isfile(dst):
        return jsonify({"error": "结果还没生成"}), 404
    return send_file(dst, mimetype="image/gif")


@app.route("/api/download/<job_id>")
def api_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    dst = os.path.join(OUTPUT_DIR, job_id + ".gif")
    if not os.path.isfile(dst):
        return jsonify({"error": "结果还没生成"}), 404
    stem = os.path.splitext(job["name"])[0] or "gif"
    download_name = "%s_公众号版.gif" % stem
    return send_file(dst, mimetype="image/gif", as_attachment=True,
                     download_name=download_name)


# ---------------------------------------------------------------------------
# CLI 模式
# ---------------------------------------------------------------------------


def _cli(argv):
    p = argparse.ArgumentParser(description="把 GIF 处理成公众号可粘贴的格式(<10MB, <=300帧)")
    p.add_argument("input", nargs="?", help="输入 GIF 文件")
    p.add_argument("-o", "--output", help="输出文件(默认: 输入文件名_公众号版.gif)")
    p.add_argument("--target", type=float, default=gif_engine.DEFAULT_TARGET_MB,
                   help="目标体积 MB(默认 9.5)")
    p.add_argument("--max-frames", type=int, default=gif_engine.DEFAULT_MAX_FRAMES,
                   help="最大帧数(默认 300)")
    p.add_argument("--max-width", type=int, default=0, help="最大宽度 px(0=不限制)")
    p.add_argument("--preset", default="balanced",
                   choices=["balanced", "quality", "extreme"], help="智能模式策略")
    p.add_argument("--dither", type=int, default=5, help="抖动强度 0=无 5=轻微 3=明显 1=强烈")
    p.add_argument("--frame-drop", default=None,
                   choices=list(gif_engine.OPTIONS_META["frame_drop"]["options"].keys()),
                   help="手动模式抽帧选项, 如 1in2=每隔1帧丢1帧")
    p.add_argument("--scale", type=float, default=None, help="手动模式缩放比例, 如 0.8")
    p.add_argument("--colors", type=int, default=None, help="手动模式色彩数, 如 128")
    p.add_argument("--port", type=int, default=8600, help="Web 服务端口")
    args = p.parse_args(argv)

    if not args.input:
        _serve(args.port)
        return 0

    src = args.input
    if not os.path.isfile(src):
        print("错误: 文件不存在 %s" % src)
        return 2
    dst = args.output
    if not dst:
        stem = os.path.splitext(src)[0]
        dst = "%s_公众号版.gif" % stem

    manual = None
    mode = "auto"
    if args.frame_drop or args.scale is not None or args.colors is not None:
        mode = "manual"
        manual = {
            "frame_drop": args.frame_drop or "keep_all",
            "scale": args.scale if args.scale is not None else 1.0,
            "colors": args.colors if args.colors is not None else 256,
            "dither": args.dither,
        }

    def progress(phase, pct, msg):
        print("\r  [%s %3d%%] %s" % (phase, pct, msg), end="", flush=True)

    print("处理: %s" % src)
    try:
        report = gif_engine.process_gif(
            src, dst, target_mb=args.target, max_frames=args.max_frames,
            max_width=args.max_width or None, preset=args.preset,
            dither=args.dither, mode=mode, manual=manual, progress=progress)
    except Exception as e:
        print("\n错误: %s" % e)
        return 1
    print()
    b, a = report["before"], report["after"]
    print("体积: %.2fMB -> %.2fMB (省 %.1f%%)" % (
        b["size_bytes"] / 1048576, a["size_bytes"] / 1048576, report["saved_pct"]))
    print("帧数: %d -> %d    尺寸: %dx%d -> %dx%d" % (
        b["frames"], a["frames"], b["width"], b["height"], a["width"], a["height"]))
    print("手段: %s" % " | ".join(report["techniques"]))
    for w in report["warnings"]:
        print("警告: %s" % w)
    print("输出: %s" % dst)
    print("状态: %s" % ("符合公众号要求" if report["ok"] else "未完全达标, 请检查警告"))
    return 0 if report["ok"] else 1


def _serve(port):
    for d in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
    # 启动时清理上一次的临时文件
    for d in (UPLOAD_DIR, OUTPUT_DIR):
        for name in os.listdir(d):
            try:
                os.unlink(os.path.join(d, name))
            except OSError:
                pass
    url = "http://127.0.0.1:%d" % port
    print("公众号 GIF 工具已启动: %s" % url)
    print("按 Ctrl+C 停止; 处理全程在本机完成, 文件不会上传到任何服务器")
    if not os.environ.get("GIF_NO_BROWSER"):
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    app.run(host="127.0.0.1", port=port, threaded=True)


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
