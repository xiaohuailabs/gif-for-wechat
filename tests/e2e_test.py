#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_test.py — Web 服务全链路测试"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8600"
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS  %s %s" % (name, detail))
    else:
        failed += 1
        print("  FAIL  %s %s" % (name, detail))


def upload(path, **fields):
    boundary = "----e2e%s" % time.time()
    with open(path, "rb") as f:
        data = f.read()
    body = b""
    for k, v in fields.items():
        if v is None:
            continue
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
             "Content-Type: image/gif\r\n\r\n" % (boundary, os.path.basename(path))).encode()
    body += data + ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(BASE + "/api/upload", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.status, json.loads(r.read())


def get_raw(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.status, r.read()


def post_json(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_done(job_id, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, job = get("/api/job/%s" % job_id)
        if st == 200 and job["status"] in ("done", "error"):
            return job
        time.sleep(0.5)
    return None


def start(job_id, **kw):
    """模拟前端点「开始处理」: 带当前控制台设置调用 /api/process"""
    body = {"job_id": job_id, "mode": "auto", "target_mb": 9.5, "max_frames": 300}
    body.update(kw)
    return post_json("/api/process", body)


print("== 0. 上传不自动执行(用户选好模式后点开始才执行) ==")
st, res = upload(os.path.join(FIX, "04_big_and_many.gif"))
check("上传成功", st == 200 and res.get("job_id"), str(res)[:100])
idle_id = res["job_id"]
time.sleep(2.5)
st, job = get("/api/job/%s" % idle_id)
check("上传后保持待开始(ready)", job["status"] == "ready", "status=%s" % job["status"])
check("上传后未产生结果", job["result"] is None and job["progress"] == 0)
check("原文件分析信息已返回", job["original"].get("frames", 0) > 300,
      "%s 帧" % job["original"].get("frames"))
st, _ = start(idle_id)
check("点击开始后才执行", st == 200)
job = wait_done(idle_id)
check("开始后任务完成", job and job["status"] == "done", job and job.get("error") or "")

print("== 1. 智能模式: 双重超限文件 ==")
st, res = upload(os.path.join(FIX, "04_big_and_many.gif"))
check("上传成功", st == 200 and res.get("job_id"), str(res)[:120])
start(res["job_id"], mode="auto")
job = wait_done(res["job_id"])
check("任务完成", job and job["status"] == "done", job and job.get("error") or "")
if job and job["result"]:
    r = job["result"]
    check("体积 < 10MB", r["after"]["size_bytes"] < 10 * 1024 * 1024,
          "%.2fMB (原 %.2fMB)" % (r["after"]["size_bytes"] / 1048576, r["before"]["size_bytes"] / 1048576))
    check("帧数 <= 300", r["after"]["frames"] <= 300, "%d 帧" % r["after"]["frames"])
    check("报告 ok 标记", r["ok"] is True)
    check("压缩手段非空", len(r["techniques"]) > 0, " | ".join(r["techniques"])[:100])

print("== 2. 手动模式: 只抽帧(参数形式与前端完全一致: 选项 ID 字符串) ==")
manual = {"frame_drop": "1in2", "scale": "1.0", "colors": "256", "dither": "none"}
st, res = upload(os.path.join(FIX, "02_too_many_frames.gif"))
check("手动模式上传", st == 200 and res.get("job_id"))
start(res["job_id"], mode="manual", manual=manual)
job = wait_done(res["job_id"])
check("手动任务完成", job and job["status"] == "done", job and job.get("error") or "")
if job and job["result"]:
    r = job["result"]
    check("帧数约减半", r["after"]["frames"] <= r["before"]["frames"] * 0.55,
          "%d -> %d" % (r["before"]["frames"], r["after"]["frames"]))
    check("帧数 <= 300", r["after"]["frames"] <= 300)

print("== 3. 已合规文件直通 ==")
st, res = upload(os.path.join(FIX, "01_small_ok.gif"))
check("直通上传", st == 200)
start(res["job_id"], mode="auto")
job = wait_done(res["job_id"])
check("直通完成", job and job["status"] == "done")
if job and job["result"]:
    check("标记 passthrough", job["result"]["passthrough"] is True)

print("== 4. 重新处理(换参数, 选项 ID 形式) ==")
st, res = post_json("/api/process", {
    "job_id": res["job_id"], "mode": "manual",
    "manual": {"frame_drop": "4in5", "scale": "0.9", "colors": "192", "dither": "slight"},
    "target_mb": 9.5, "max_frames": 300})
check("重新处理启动", st == 200, str(res)[:100])
job = wait_done(res["job_id"])
check("重新处理完成", job and job["status"] == "done", job and job.get("error") or "")
if job and job["result"]:
    r = job["result"]
    check("设置生效(色彩128/缩放0.9描述)", any("192" in t or "缩放" in t for t in r["techniques"]),
          " | ".join(r["techniques"])[:120])

print("== 5. 结果文件可读 ==")
st, blob = get_raw("/api/result/%s" % res["job_id"])
check("result 接口", st == 200 and blob[:6] in (b"GIF87a", b"GIF89a"), "%dB" % len(blob))
st, blob = get_raw("/api/download/%s" % res["job_id"])
check("download 接口", st == 200 and len(blob) > 0)

print("== 6. 异常路径 ==")
st, res = upload(os.path.join(FIX, "10_not_gif.png"))
check("拒绝非 GIF", st == 400 and "GIF" in res.get("error", ""), res.get("error", "")[:60])
st, res = upload(os.path.join(FIX, "09_broken.gif"))
if st == 200:
    start(res["job_id"], mode="auto")
    st2 = wait_done(res["job_id"])["status"]
check("损坏文件被拒或报错", st == 400 or (st == 200 and st2 == "error"), "st=%s" % st)
st, res = post_json("/api/process", {"job_id": "nonexistent", "mode": "manual"})
check("不存在的任务 404", st == 404)

print("== 7. 畸形元数据 GIF(元组 transparency, 曾导致 Pillow 位与崩溃) ==")
bad_path = os.path.join(FIX, "11_tuple_transparency.gif")
if os.path.exists(bad_path):
    for mode, kw in (("auto", {}),
                     ("manual", {"manual": {"frame_drop": "2in3", "scale": "0.8",
                                            "colors": "128", "dither": "none"}}),
                     ("manual(数字参数)", {"mode": "manual",
                                       "manual": {"frame_drop": "2in3", "scale": 0.8,
                                                  "colors": 128, "dither": 0}})):
        st, res = upload(bad_path)
        check("畸形 GIF 上传(%s)" % mode, st == 200, str(res)[:80])
        if st == 200:
            kw = dict(kw)
            kw.setdefault("mode", mode if mode in ("auto", "manual") else "manual")
            start(res["job_id"], **kw)
            job = wait_done(res["job_id"])
            check("畸形 GIF 处理成功(%s)" % mode, job and job["status"] == "done",
                  (job and job.get("error")) or "")
else:
    print("  (跳过: 缺少 11_tuple_transparency.gif, 先运行 make_test_gifs.py)")

print("\n总计: %d 通过, %d 失败" % (passed, failed))
sys.exit(1 if failed else 0)
