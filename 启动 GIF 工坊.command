#!/bin/bash
# FRAME LAB · GIF 工坊 —— 双击启动
# 首次运行会自动创建独立虚拟环境并安装依赖(需联网, 约 1 分钟), 之后秒开。

cd "$(dirname "$0")" || exit 1
PORT="${GIF_PORT:-8600}"
VENV=".venv"

say() { printf "\n\033[1m%s\033[0m\n" "$1"; }
warn() { printf "\033[33m%s\033[0m\n" "$1"; }
die() { printf "\n\033[31m%s\033[0m\n" "$1"; echo "按回车键关闭窗口..."; read -r; exit 1; }

# 1) 找 Python 3.9+
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
[ -z "$PY" ] && die "没有找到 Python 3.9 或更高版本。请先安装: https://www.python.org/downloads/ (或 brew install python)"

# 2) 虚拟环境 + 依赖(首次才装; 依赖文件变化时重装)
if [ ! -x "$VENV/bin/python" ]; then
  say "首次运行: 正在创建运行环境..."
  "$PY" -m venv "$VENV" || die "创建虚拟环境失败。"
fi
STAMP="$VENV/.deps-installed"
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
  say "正在安装依赖(flask, pillow)..."
  "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  "$VENV/bin/python" -m pip install --quiet -r requirements.txt \
    || die "依赖安装失败, 请检查网络后重试。"
  touch "$STAMP"
fi

# 3) ffmpeg 检查(没有也能跑, 但画质/体积会差一些)
if ! command -v ffmpeg >/dev/null 2>&1; then
  for p in /opt/homebrew/bin /usr/local/bin; do
    [ -x "$p/ffmpeg" ] && export PATH="$p:$PATH"
  done
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "未检测到 ffmpeg: 将使用内置 Pillow 兜底引擎(透明背景会变白底, 压缩率更低)。"
  warn "建议安装: brew install ffmpeg"
fi

# 4) 端口被占用 -> 说明已经开着了, 直接打开浏览器
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  say "GIF 工坊已经在运行, 正在打开浏览器..."
  open "http://127.0.0.1:$PORT"
  exit 0
fi

say "GIF 工坊启动中 —— 关闭此窗口即可退出"
exec "$VENV/bin/python" app.py --port "$PORT"
