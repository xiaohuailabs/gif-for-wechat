/* ============================================================
   FRAME LAB · GIF 工坊 前端逻辑
   ============================================================ */
(function () {
  "use strict";

  /* ---------------- 工具 ---------------- */
  function $(id) { return document.getElementById(id); }

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function fmtBytes(b) {
    if (b == null) return "-";
    if (b >= 1024 * 1024) return (b / 1048576).toFixed(2) + " MB";
    if (b >= 1024) return (b / 1024).toFixed(1) + " KB";
    return b + " B";
  }

  function fmtFps(f) {
    if (f == null) return "-";
    return (Math.round(f * 100) / 100) + " fps";
  }

  function fmtDur(ms) {
    if (ms == null) return "-";
    var s = ms / 1000;
    if (s < 60) return (Math.round(s * 10) / 10) + "s";
    return Math.floor(s / 60) + "m" + Math.round(s % 60) + "s";
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---------------- 图标 ---------------- */
  var ICONS = {
    "i-copy": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2.5"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    "i-check": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    "i-download": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/></svg>',
    "i-retry": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>',
    "i-warn": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    "i-film": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="18" rx="2"/><path d="M7 3v18M17 3v18M2 8h5M2 16h5M17 8h5M17 16h5"/></svg>',
    "i-lock": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
    "i-spark": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v5M12 17v5M4.9 4.9l3.5 3.5M15.6 15.6l3.5 3.5M2 12h5M17 12h5M4.9 19.1l3.5-3.5M15.6 8.4l3.5-3.5"/></svg>',
    "i-sliders": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 12h6"/></svg>',
    "i-err": '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    "i-play": '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4.5v15l12-7.5-12-7.5z"/></svg>'
  };

  function icon(name) { return ICONS[name] || ""; }

  /* ---------------- Toast ---------------- */
  var toastTimer = null;
  function toast(msg, isErr) {
    var el = $("toast");
    el.innerHTML = (isErr ? icon("i-err") : icon("i-check")) + "<span>" + esc(msg) + "</span>";
    el.className = "toast show " + (isErr ? "err" : "ok");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = "toast"; }, 2600);
  }

  /* ---------------- 数字滚动 ---------------- */
  function animateNumber(el, target, opts) {
    opts = opts || {};
    var decimals = opts.decimals || 0;
    var prefix = opts.prefix || "";
    if (reduceMotion) {
      el.textContent = prefix + target.toFixed(decimals) + "%";
      return;
    }
    var start = 0, dur = 900, t0 = null;
    function step(ts) {
      if (t0 == null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 4);
      var v = start + (target - start) * eased;
      el.textContent = prefix + v.toFixed(decimals) + "%";
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = prefix + target.toFixed(decimals) + "%";
    }
    requestAnimationFrame(step);
  }

  /* ---------------- 全局状态 ---------------- */
  var state = {
    meta: null,
    mode: "auto",
    manual: { frame_drop: "keep_all", scale: "1.0", colors: "256", dither: "none" },
    targetMB: 9.5,
    jobs: {} // jobId -> card 对象
  };

  /* ---------------- 控制台: 选项渲染 ---------------- */
  function renderConsole(meta) {
    state.meta = meta;

    // 引擎铭牌
    var eng = meta.engines || {};
    $("engineName").textContent = eng.ffmpeg ? "FFMPEG READY" : (eng.pillow ? "PILLOW READY" : "NO ENGINE");
    $("engineChip").title = eng.ffmpeg || (eng.pillow ? "Pillow 内置引擎" : "无可用编码引擎");

    // 组合预设
    var comboRow = $("comboRow");
    comboRow.innerHTML = "";
    (meta.combos || []).forEach(function (c) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "combo-btn";
      b.innerHTML = icon("i-spark") + "<span>" + esc(c.name) + "</span>";
      b.title = c.desc || "";
      b.addEventListener("click", function () {
        applyManual(c.params);
        toast("已应用组合: " + c.name + (c.desc ? " · " + c.desc : ""));
      });
      comboRow.appendChild(b);
    });

    // 选项组
    var groups = [
      { key: "frame_drop", order: meta.frame_drop_order, group: "帧" },
      { key: "scale", order: meta.scale_order, group: "形" },
      { key: "colors", order: meta.colors_order, group: "色" },
      { key: "dither", order: meta.dither_order, group: "抖动" }
    ];
    var wrap = $("optGroups");
    wrap.innerHTML = "";
    groups.forEach(function (g) {
      var m = meta.options_meta[g.key];
      if (!m) return;
      var box = document.createElement("div");
      box.className = "opt-group";
      box.innerHTML =
        '<div class="opt-head">' +
        '<span class="opt-num">' + ("0" + (groups.indexOf(g) + 1)) + "</span>" +
        '<span class="name">' + esc(m.label) + "</span>" +
        '<span class="desc">' + esc(m.desc) + "</span>" +
        "</div>";
      var list = document.createElement("div");
      list.className = "opt-list";
      (g.order || Object.keys(m.options)).forEach(function (oid) {
        var o = m.options[oid];
        if (!o) return;
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "opt-btn" + (state.manual[g.key] === oid ? " selected" : "");
        btn.dataset.group = g.key;
        btn.dataset.opt = oid;
        var meta2 = (o.impact ? o.impact : "") + (o.meta ? " · " + o.meta : "");
        var pros = "";
        if (o.pros) pros += '<span class="ob-pro"><em>✓</em>' + esc(o.pros) + "</span>";
        if (o.cons) pros += '<span class="ob-con"><em>✗</em>' + esc(o.cons) + "</span>";
        btn.innerHTML =
          '<span class="ob-label">' + esc(o.label) + "</span>" +
          (meta2 ? '<span class="ob-meta">' + esc(meta2) + "</span>" : "") +
          '<span class="ob-lines">' + pros + "</span>";
        btn.addEventListener("click", function () {
          state.manual[g.key] = oid;
          list.querySelectorAll(".opt-btn").forEach(function (x) { x.classList.remove("selected"); });
          btn.classList.add("selected");
          refreshModeHints();
        });
        list.appendChild(btn);
      });
      box.appendChild(list);
      wrap.appendChild(box);
    });
  }

  function applyManual(params) {
    ["frame_drop", "scale", "colors", "dither"].forEach(function (k) {
      if (params && params[k] != null) state.manual[k] = params[k];
    });
    document.querySelectorAll("#optGroups .opt-btn").forEach(function (btn) {
      var g = btn.dataset.group, o = btn.dataset.opt;
      btn.classList.toggle("selected", state.manual[g] === o);
    });
    refreshModeHints();
  }

  /* ---------------- 模式切换 ---------------- */
  function initModeSwitch() {
    var seg = $("modeSeg");
    var btns = seg.querySelectorAll(".segment");
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener("click", function () {
        var mode = b.dataset.mode;
        if (mode === state.mode) return;
        state.mode = mode;
        seg.dataset.active = mode === "manual" ? "1" : "0";
        Array.prototype.forEach.call(btns, function (x) {
          x.classList.toggle("active", x === b);
        });
        $("panel-auto").classList.toggle("active", mode === "auto");
        $("panel-manual").classList.toggle("active", mode === "manual");
        refreshModeHints();
      });
    });
  }

  /* ---------------- 卡片 ---------------- */
  var FRAME_CELLS = 24;

  function makeCard(name) {
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-head">' +
      '  <div class="card-fileicon">' + icon("i-film") + "</div>" +
      '  <div class="card-name">' + esc(name) + "</div>" +
      '  <span class="card-status">排队中</span>' +
      '  <button class="card-close" title="移除任务" type="button">' +
      '    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>' +
      "  </button>" +
      "</div>" +
      '<div class="card-body"></div>';

    var card = {
      el: el,
      jobId: null,
      poller: null,
      statusEl: el.querySelector(".card-status"),
      bodyEl: el.querySelector(".card-body")
    };

    el.querySelector(".card-close").addEventListener("click", function () {
      if (card.poller) clearInterval(card.poller);
      if (card.jobId) delete state.jobs[card.jobId];
      el.style.transition = "opacity .25s, transform .25s";
      el.style.opacity = "0";
      el.style.transform = "translateY(-8px) scale(.98)";
      setTimeout(function () {
        el.remove();
        syncEmpty();
        updateStartAll();
      }, 250);
    });

    $("queue").appendChild(el);
    syncEmpty();
    return card;
  }

  function syncEmpty() {
    $("emptyHint").style.display = $("queue").children.length ? "none" : "block";
  }

  function setStatus(card, cls, text) {
    card.statusEl.className = "card-status " + cls;
    card.statusEl.textContent = text;
  }

  function renderProgress(card, pct, msg) {
    var lit = Math.round((pct / 100) * FRAME_CELLS);
    var html =
      '<div class="progress-block">' +
      '  <div class="filmstrip">';
    for (var i = 0; i < FRAME_CELLS; i++) {
      html += '<span class="frame-cell' + (i < lit ? " lit" : "") + '"></span>';
    }
    html +=
      "  </div>" +
      '  <div class="progress-msg">' + esc(msg || "处理中") + "</div>" +
      '  <div class="bar"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
      "</div>";
    card.bodyEl.innerHTML = html;
  }

  /* ---------------- 结果渲染 ---------------- */
  function statRow(label, before, after, unit, deltaText, deltaCls) {
    return (
      '<div class="stat-row">' +
      '  <span class="stat-label">' + esc(label) + "</span>" +
      '  <span class="stat-val dim">' + esc(before) + "</span>" +
      '  <span class="stat-delta ' + deltaCls + '">' + esc(deltaText) + "</span>" +
      '  <span class="stat-val ' + (deltaCls === "good" ? "good" : deltaCls === "warn" ? "warn" : "") + '" style="text-align:right">' + esc(after) + "</span>" +
      "</div>"
    );
  }

  function renderResult(card, job) {
    var r = job.result || {};
    var before = r.before || job.original || {};
    var after = r.after || {};
    var pass = !!r.ok;

    setStatus(card, pass ? "ok" : "bad", pass ? "已完成" : "未达标");

    // 英雄区数字: 体积变化百分比
    var pct = 0, up = false;
    if (before.size_bytes && after.size_bytes != null) {
      pct = (after.size_bytes - before.size_bytes) / before.size_bytes * 100;
      up = pct > 0;
    }
    var heroNum = (pass && Math.abs(pct) < 0.05) ? "0.0" : Math.abs(pct).toFixed(1);
    var sign = pct > 0 ? "+" : "−";

    var html =
      '<div class="hero">' +
      '  <div class="hero-cap">体积变化</div>' +
      '  <div class="hero-num ' + (up ? "up" : "down") + '">' +
      '    <span class="num-sign">' + sign + '</span><span class="num-val">' + heroNum + "</span>" +
      "  </div>";

    if (pass) {
      html +=
        '  <div class="hero-badge">' + icon("i-check") +
        (r.passthrough ? "原文件已合规 · 原样输出" : "已达标 · 可直接粘贴公众号") + "</div>";
    } else {
      html +=
        '  <div class="hero-badge warn">' + icon("i-warn") + "极限压缩后仍未达标</div>";
    }
    html +=
      '  <div class="hero-sub">' + fmtBytes(before.size_bytes) +
      '    <span class="arr">→</span> ' + fmtBytes(after.size_bytes) + "</div>" +
      "</div>";

    // 前后对比
    html +=
      '<div class="compare">' +
      '  <div class="compare-item orig">' +
      '    <div class="ci-tag"><span>原文件</span><span class="size">' + fmtBytes(before.size_bytes) + " · " + (before.frames || "?") + "帧</span></div>" +
      '    <div class="ci-stage"><img src="' + (r.original_url || "") + '" alt="原文件预览"><div class="ci-fallback">原图加载失败</div></div>' +
      "  </div>" +
      '  <div class="compare-item after">' +
      '    <div class="ci-tag"><span>处理后</span><span class="size">' + fmtBytes(after.size_bytes) + " · " + (after.frames || "?") + "帧</span></div>" +
      '    <div class="ci-stage"><img src="' + (r.result_url || "") + "?t=" + Date.now() + '" alt="处理后预览"><div class="ci-fallback">结果加载失败</div></div>' +
      "  </div>" +
      "</div>";

    // 统计行
    var sizeDelta = before.size_bytes && after.size_bytes
      ? (after.size_bytes - before.size_bytes) / before.size_bytes * 100 : null;
    var frameDelta = before.frames != null && after.frames != null ? after.frames - before.frames : null;
    var sizeOk = after.size_bytes != null && after.size_bytes < 10 * 1024 * 1024;
    var frameOk = after.frames != null && after.frames <= (r.settings && r.settings.max_frames || 300);
    var dimDelta = before.width && after.width ? after.width - before.width : null;

    html += '<div class="stats">';
    html += statRow("文件体积", fmtBytes(before.size_bytes), fmtBytes(after.size_bytes), "MB",
      sizeDelta == null ? "-" : (sizeDelta <= 0 ? "−" + Math.abs(sizeDelta).toFixed(0) + "%" : "+" + sizeDelta.toFixed(0) + "%"),
      sizeDelta != null && sizeDelta < 0 ? "good" : sizeDelta != null && sizeDelta > 0 ? "warn" : "neutral");
    html += statRow("帧数", (before.frames || "?") + " 帧", (after.frames || "?") + " 帧", "",
      frameDelta == null ? "-" : (frameDelta === 0 ? "不变" : (frameDelta < 0 ? "−" + Math.abs(frameDelta) : "+" + frameDelta) + " 帧"),
      frameDelta == null ? "neutral" : frameDelta < 0 ? "good" : frameDelta > 0 ? "warn" : "neutral");
    html += statRow("分辨率", (before.width || "?") + "×" + (before.height || "?"), (after.width || "?") + "×" + (after.height || "?"), "",
      dimDelta == null ? "-" : (dimDelta === 0 ? "不变" : (dimDelta < 0 ? "−" + Math.abs(dimDelta) : "+" + dimDelta) + " px"),
      dimDelta == null ? "neutral" : dimDelta < 0 ? "good" : dimDelta > 0 ? "warn" : "neutral");
    html += statRow("帧率", fmtFps(before.fps), fmtFps(after.fps), "",
      before.fps && after.fps ? (after.fps < before.fps - 0.01 ? "−" + (before.fps - after.fps).toFixed(1) : after.fps > before.fps + 0.01 ? "+" + (after.fps - before.fps).toFixed(1) : "不变") : "-",
      before.fps && after.fps && after.fps < before.fps - 0.01 ? "good" : "neutral");
    html += "</div>";

    // 合规性小结
    html += '<div class="tag-list">';
    html += '<span class="tech-tag">' + icon(sizeOk ? "i-check" : "i-warn") + (sizeOk ? "体积 < 10MB" : "体积仍 ≥ 10MB") + "</span>";
    html += '<span class="tech-tag">' + icon(frameOk ? "i-check" : "i-warn") + (frameOk ? "帧数 ≤ " + (r.settings && r.settings.max_frames || 300) : "帧数仍超限") + "</span>";
    (r.techniques || []).forEach(function (t) {
      html += '<span class="tech-tag">' + esc(t) + "</span>";
    });
    html += "</div>";

    // 警告
    (r.warnings || []).forEach(function (w) {
      html +=
        '<div class="callout">' +
        '  <span class="icon">' + icon("i-warn") + "</span>" +
        "  <p>" + esc(w) + "</p>" +
        "</div>";
    });

    // 操作
    html +=
      '<div class="actions">' +
      '  <button class="btn btn-primary copy-btn" type="button">' + icon("i-copy") + "复制到剪贴板</button>" +
      '  <a class="btn btn-secondary" href="' + (r.download_url || "") + '" download>' + icon("i-download") + "下载文件</a>" +
      '  <button class="btn btn-secondary reprocess-btn" type="button">' + icon("i-retry") + "重新处理</button>" +
      "</div>";

    card.bodyEl.innerHTML = html;

    // 数字滚动(保留正负号)
    var numEl = card.bodyEl.querySelector(".num-val");
    var target = parseFloat(heroNum);
    if (!isNaN(target) && !(pass && Math.abs(pct) < 0.05)) {
      animateNumber(numEl, target, { decimals: Math.abs(target) < 10 ? 1 : 0, prefix: "" });
    }

    // 图片淡入 + 失败兜底
    card.bodyEl.querySelectorAll(".ci-stage img").forEach(function (img) {
      var stage = img.closest(".ci-stage");
      function done() { img.classList.add("loaded"); }
      function fail() {
        img.style.display = "none";
        var fb = stage.querySelector(".ci-fallback");
        if (fb) fb.style.display = "grid";
      }
      if (img.complete && img.naturalWidth > 0) done();
      else {
        img.addEventListener("load", done);
        img.addEventListener("error", fail);
      }
    });

    // 复制
    var copyBtn = card.bodyEl.querySelector(".copy-btn");
    copyBtn.addEventListener("click", function () { copyGif((r.result_url || "") + "?t=" + Date.now(), copyBtn); });

    // 重新处理: 用当前控制台设置再跑一遍
    card.bodyEl.querySelector(".reprocess-btn").addEventListener("click", function () {
      reprocess(card, job);
    });
  }

  /* ---------------- 上传 / 开始 / 重新处理 ---------------- */
  function currentParams() {
    var p = {
      mode: state.mode,
      target_mb: parseFloat($("targetMB").value) || 9.5,
      max_frames: 300
    };
    if (state.mode === "manual") p.manual = state.manual;
    return p;
  }

  /* 上传只负责入队与分析, 不开工; 用户选好模式后点「开始处理」才执行 */
  function uploadFile(file) {
    if (!/\.gif$/i.test(file.name)) {
      toast("只支持 GIF 文件: " + file.name, true);
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      toast("文件超过 100MB, 请先分段录制", true);
      return;
    }

    var card = makeCard(file.name);
    setStatus(card, "working", "上传中");
    renderProgress(card, 2, "正在读取 " + fmtBytes(file.size) + " 文件…");
    updateStartAll();

    var fd = new FormData();
    fd.append("file", file);

    fetch("/api/upload", { method: "POST", body: fd })
      .then(function (res) {
        return res.json().then(function (body) {
          if (!res.ok) throw new Error(body.error || "上传失败");
          return body;
        });
      })
      .then(function (body) {
        card.jobId = body.job_id;
        card.original = body.original;
        card.state = "ready";
        state.jobs[body.job_id] = card;
        renderReady(card);
        updateStartAll();
      })
      .catch(function (err) {
        card.state = "error";
        setStatus(card, "err", "失败");
        card.bodyEl.innerHTML =
          '<div class="err-block"><span class="icon">' + icon("i-err") + "</span>" +
          '<div class="txt"><b>装片失败</b><br>' + esc(err.message || String(err)) + "</div></div>";
        updateStartAll();
      });
  }

  /* 待开始态: 原图预览 + 原始规格 + 开始按钮 */
  function renderReady(card) {
    var o = card.original || {};
    setStatus(card, "", "待开始");
    var warnSize = o.size_bytes > 10 * 1024 * 1024;
    var warnFrames = o.frames > 300;
    var html =
      '<div class="ready-block">' +
      '  <div class="ready-thumb"><img src="/api/original/' + card.jobId + '" alt="原文件预览"></div>' +
      '  <div class="ready-info">' +
      '    <div class="ready-specs">' +
      '      <div class="spec"><span class="k">体积</span><span class="v' + (warnSize ? " over" : "") + '">' + fmtBytes(o.size_bytes) + "</span></div>" +
      '      <div class="spec"><span class="k">帧数</span><span class="v' + (warnFrames ? " over" : "") + '">' + (o.frames || "?") + "</span></div>" +
      '      <div class="spec"><span class="k">尺寸</span><span class="v">' + (o.width || "?") + "×" + (o.height || "?") + "</span></div>" +
      '      <div class="spec"><span class="k">帧率</span><span class="v">' + fmtFps(o.fps) + "</span></div>" +
      "    </div>" +
      '    <div class="ready-verdict">' + readyVerdict(o, warnSize, warnFrames) + "</div>" +
      '    <div class="ready-mode" data-role="mode-hint"></div>' +
      '    <div class="actions">' +
      '      <button class="btn btn-primary start-btn" type="button">' + icon("i-play") + "开始处理</button>" +
      "    </div>" +
      "  </div>" +
      "</div>";
    card.bodyEl.innerHTML = html;

    var img = card.bodyEl.querySelector(".ready-thumb img");
    img.addEventListener("load", function () { img.classList.add("loaded"); });
    img.addEventListener("error", function () { img.style.display = "none"; });
    if (img.complete && img.naturalWidth > 0) img.classList.add("loaded");

    card.bodyEl.querySelector(".start-btn").addEventListener("click", function () {
      startCard(card);
    });
    refreshModeHints();
  }

  function readyVerdict(o, warnSize, warnFrames) {
    if (!warnSize && !warnFrames) {
      return "已满足公众号限制 · 仍可处理以进一步减小体积";
    }
    var parts = [];
    if (warnSize) parts.push("体积超过 10MB");
    if (warnFrames) parts.push("帧数超过 300 帧");
    return "需要处理 · " + parts.join("、");
  }

  /* 待开始卡片上展示「点击后将按什么模式执行」, 随控制台实时刷新 */
  function refreshModeHints() {
    var text;
    if (state.mode === "auto") {
      text = "将使用 智能模式 · 目标 " + (parseFloat($("targetMB").value) || 9.5) + " MB";
    } else {
      var m = state.manual, md = state.meta && state.meta.options_meta;
      function lab(k) {
        var o = md && md[k] && md[k].options[m[k]];
        return o ? o.label : m[k];
      }
      text = "将使用 手动模式 · 抽帧「" + lab("frame_drop") + "」· 缩放 " + lab("scale") +
        " · " + lab("colors") + " · " + lab("dither");
    }
    document.querySelectorAll('[data-role="mode-hint"]').forEach(function (el) {
      el.textContent = text;
    });
  }

  /* 开工: 读取点击瞬间的控制台设置 */
  function startCard(card) {
    if (!card.jobId || card.state === "running") return;
    var p = currentParams();
    card.state = "running";
    setStatus(card, "working", "处理中");
    renderProgress(card, 3, p.mode === "auto" ? "智能分析中…" : "按你的设置编码中…");
    updateStartAll();
    fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: card.jobId,
        mode: p.mode,
        target_mb: p.target_mb,
        max_frames: p.max_frames,
        manual: p.manual || null
      })
    })
      .then(function (res) {
        return res.json().then(function (body) {
          if (!res.ok) throw new Error(body.error || "请求失败");
          return body;
        });
      })
      .then(function () { startPolling(card); })
      .catch(function (err) {
        card.state = "error";
        setStatus(card, "err", "失败");
        card.bodyEl.innerHTML =
          '<div class="err-block"><span class="icon">' + icon("i-err") + "</span>" +
          '<div class="txt"><b>启动失败</b><br>' + esc(err.message || String(err)) + "</div></div>";
        updateStartAll();
      });
  }

  /* 「全部开始」: 出片区里所有待开始卡片, 用当前控制台设置一起开工 */
  function updateStartAll() {
    var btn = $("startAllBtn");
    var readyCount = 0;
    Object.keys(state.jobs).forEach(function (id) {
      if (state.jobs[id].state === "ready") readyCount++;
    });
    btn.style.display = readyCount >= 2 ? "" : "none";
    btn.lastChild.textContent = "全部开始 (" + readyCount + ")";
  }

  function startAll() {
    Object.keys(state.jobs).forEach(function (id) {
      var c = state.jobs[id];
      if (c.state === "ready") startCard(c);
    });
  }

  function reprocess(card, job) {
    if (!card.jobId) return;
    card.poller && clearInterval(card.poller);
    startCard(Object.assign(card, { state: "ready" }));
  }

  function startPolling(card) {
    if (!card.jobId) return;
    if (card.poller) clearInterval(card.poller);
    var lastMsg = "";
    card.poller = setInterval(function () {
      fetch("/api/job/" + card.jobId)
        .then(function (res) { return res.json(); })
        .then(function (job) {
          if (job.error && job.status === "error") {
            clearInterval(card.poller);
            card.state = "error";
            setStatus(card, "err", "失败");
            card.bodyEl.innerHTML =
              '<div class="err-block"><span class="icon">' + icon("i-err") + "</span>" +
              '<div class="txt"><b>处理失败</b><br>' + esc(job.error) + "</div></div>";
            updateStartAll();
            return;
          }
          if (job.status === "running" || job.status === "queued") {
            var pct = Math.max(2, Math.min(98, job.progress || 0));
            if (job.message !== lastMsg || pct < 5) {
              lastMsg = job.message;
              renderProgress(card, pct, job.message);
            } else {
              var strip = card.bodyEl.querySelector(".filmstrip");
              if (strip) {
                var lit = Math.round((pct / 100) * FRAME_CELLS);
                var cells = strip.children;
                for (var i = 0; i < cells.length; i++) {
                  cells[i].classList.toggle("lit", i < lit);
                }
                var fill = card.bodyEl.querySelector(".bar-fill");
                if (fill) fill.style.width = pct + "%";
              }
            }
            return;
          }
          // 完成
          clearInterval(card.poller);
          card.poller = null;
          if (job.status === "done" && job.result) {
            card.state = "done";
            renderResult(card, job);
          } else {
            card.state = "error";
            setStatus(card, "err", "失败");
            card.bodyEl.innerHTML =
              '<div class="err-block"><span class="icon">' + icon("i-err") + "</span>" +
              '<div class="txt"><b>处理失败</b><br>' + esc(job.error || "未知错误") + "</div></div>";
          }
          updateStartAll();
        })
        .catch(function () { /* 网络抖动, 下轮再试 */ });
    }, 600);
  }

  /* ---------------- 复制到剪贴板 ---------------- */
  function copyGif(url, btn) {
    fetch(url)
      .then(function (res) { return res.blob(); })
      .then(function (blob) {
        if (blob.type !== "image/gif" && !/GIF8/.test(String.fromCharCode.apply(null, [blob[0], blob[1], blob[2]]))) {
          throw new Error("not-a-gif");
        }
        if (!navigator.clipboard || typeof window.ClipboardItem === "undefined") {
          var e = new Error("clipboard-unsupported");
          e.name = "NotSupportedError";
          throw e;
        }
        return navigator.clipboard.write([new window.ClipboardItem({ "image/gif": blob })]);
      })
      .then(function () {
        btn.classList.add("done");
        btn.innerHTML = icon("i-check") + "已复制";
        toast("已复制, 去公众号编辑器 Ctrl+V 粘贴吧");
        setTimeout(function () {
          btn.classList.remove("done");
          btn.innerHTML = icon("i-copy") + "复制到剪贴板";
        }, 2600);
      })
      .catch(function (err) {
        if (err && (err.name === "NotSupportedError" || err.message === "clipboard-unsupported")) {
          toast("当前浏览器不支持直接复制图片, 已打开图片, 请右键复制或拖进编辑器", true);
          window.open(url, "_blank");
        } else {
          toast("复制失败: " + (err && err.message ? err.message : "未知错误"), true);
        }
      });
  }

  /* ---------------- 拖拽 & 选择 ---------------- */
  function initDropzone() {
    var dz = $("dropzone");
    var input = $("fileInput");

    dz.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      Array.prototype.forEach.call(input.files, uploadFile);
      input.value = "";
    });

    ["dragenter", "dragover"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        dz.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (ev === "dragleave" && dz.contains(e.relatedTarget)) return;
        dz.classList.remove("dragover");
      });
    });
    dz.addEventListener("drop", function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files) Array.prototype.forEach.call(files, uploadFile);
    });

    // 全局拖拽防打开
    window.addEventListener("dragover", function (e) { e.preventDefault(); });
    window.addEventListener("drop", function (e) { e.preventDefault(); });
  }

  /* ---------------- 启动 ---------------- */
  function init() {
    initModeSwitch();
    initDropzone();
    $("startAllBtn").addEventListener("click", startAll);
    $("targetMB").addEventListener("input", refreshModeHints);
    $("emptyHint").style.display = "block";
    fetch("/api/meta")
      .then(function (res) { return res.json(); })
      .then(function (meta) {
        renderConsole(meta);
        if (meta.defaults && meta.defaults.target_mb) {
          $("targetMB").value = meta.defaults.target_mb;
        }
      })
      .catch(function () {
        $("engineName").textContent = "META OFFLINE";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
