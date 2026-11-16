#!/usr/bin/env bash
set -e
echo "== CoverGrab 依赖安装 =="

if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python python-pillow tk
    pip install --user --break-system-packages mutagen tkinterdnd2 2>/dev/null || \
        pip install --user mutagen tkinterdnd2
elif command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo apt install -y python3 python3-pil python3-tk python3-pip
    pip3 install --user mutagen tkinterdnd2
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pillow python3-tkinter
    pip install --user mutagen tkinterdnd2
else
    echo "未识别的发行版，请手动安装： python3、Pillow、mutagen、tkinter"
    exit 1
fi

echo
echo "完成。运行： ./run.sh"