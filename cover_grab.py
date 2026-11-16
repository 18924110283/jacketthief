"""封皮贼 JacketThief — 从音乐文件里扒内嵌封面，导出成封面图 / 视频封面。

支持 MP3(APIC) / FLAC(picture) / M4A(covr) / OGG / WAV 等
"""

import io
import os
import re
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageFilter, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False

try:
    import windnd
    HAS_WINDND = True
except Exception:
    HAS_WINDND = False

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from ui_widgets import RoundedButton
import platform_utils as PU

UI_FONT = PU.ui_font()          # 界面字体族（win 微软雅黑 / linux Noto）

AUDIO_EXT = {".mp3", ".flac", ".m4a", ".mp4", ".m4b", ".ogg", ".opus", ".wma",
             ".aiff", ".ape", ".wav", ".aac", ".wv", ".tta", ".dff", ".dsf"}

BG = "#1b1a20"
CARD = "#26242c"
CARD2 = "#2f2c36"
FG = "#e9e6ef"
DIM = "#8d8799"
ACCENT = "#b98cf0"
ACCENT2 = "#7d5bb8"
OK = "#7ee0a8"

MODE_LABEL = {
    "方形（原比例）": "square",
    "16:9 模糊填充": "blur16x9",
    "16:9 裁切铺满": "crop16x9",
}


# ---------------- 提取 ----------------
def extract_cover(path: Path):
    """返回 (PIL.Image, 尺寸说明) 或 (None, 原因)。"""
    try:
        suf = path.suffix.lower()
        if suf == ".flac":
            f = FLAC(str(path))
            if f.pictures:
                p = f.pictures[0]
                im = Image.open(io.BytesIO(p.data)).convert("RGB")
                return im, f"{im.width}x{im.height}"
            return None, "无封面"
        if suf in (".m4a", ".mp4", ".m4b", ".m4v"):
            f = MP4(str(path))
            covr = f.tags.get("covr") if f.tags else None
            if covr:
                im = Image.open(io.BytesIO(bytes(covr[0]))).convert("RGB")
                return im, f"{im.width}x{im.height}"
            return None, "无封面"
        if suf == ".mp3":
            try:
                tags = ID3(str(path))
            except Exception:
                return None, "读不到标签"
            for k in tags.keys():
                if k.startswith("APIC"):
                    im = Image.open(io.BytesIO(tags[k].data)).convert("RGB")
                    return im, f"{im.width}x{im.height}"
            return None, "无封面"
        f = MutagenFile(str(path))
        if f and getattr(f, "tags", None):
            for k in f.tags.keys():
                if str(k).startswith("APIC"):
                    im = Image.open(io.BytesIO(f.tags[k].data)).convert("RGB")
                    return im, f"{im.width}x{im.height}"
            pics = getattr(f, "pictures", None)
            if pics:
                im = Image.open(io.BytesIO(pics[0].data)).convert("RGB")
                return im, f"{im.width}x{im.height}"
        return None, "无封面"
    except Exception as e:  # noqa: BLE001
        return None, f"读取失败：{type(e).__name__}"


def read_title(path: Path):
    try:
        f = MutagenFile(str(path), easy=True)
        if not f:
            return ""
        t = (f.get("title") or [""])[0]
        a = (f.get("artist") or [""])[0]
        return f"{t}" + (f" · {a}" if a else "")
    except Exception:
        return ""


# ---------------- 渲染 ----------------
def render(img: Image.Image, mode: str, size: int) -> Image.Image:
    if mode == "square":
        out = img.resize((size, size), Image.LANCZOS)
    elif mode == "crop16x9":
        w, h = img.size
        ratio = 16 / 9
        if w / h > ratio:
            nw = int(h * ratio)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / ratio)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        out = img.resize((size, int(size * 9 / 16)), Image.LANCZOS)
    else:
        W, H = size, int(size * 9 / 16)
        bg = img.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(48))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (18, 16, 20)), 0.18)
        side = int(H * 0.86)
        fg = img.resize((side, side), Image.LANCZOS)
        # 封面投影
        sh = Image.new("RGBA", (side + 40, side + 40), (0, 0, 0, 0))
        bg.paste(fg, ((W - side) // 2, (H - side) // 2))
        out = bg
    return out.filter(ImageFilter.UnsharpMask(radius=1.4, percent=80, threshold=2))


def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s).strip()
    return s[:80] or "cover"


# ---------------- 界面 ----------------
class DarkSelect(tk.Menubutton):
    """深色下拉框（ttk.Combobox 在这套配色下会发白）"""

    def __init__(self, parent, var, values, width=12, font=(UI_FONT, 9)):
        super().__init__(parent, textvariable=var, bg=CARD2, fg=FG,
                         activebackground=ACCENT2, activeforeground="#ffffff",
                         relief="flat", bd=0, anchor="w", padx=10, pady=4,
                         width=width, font=font, highlightthickness=0, cursor="hand2")
        m = tk.Menu(self, tearoff=0, bg=CARD2, fg=FG, activebackground=ACCENT2,
                    activeforeground="#ffffff", bd=0, font=font)
        for v in values:
            m.add_command(label=v, command=lambda v=v: var.set(v))
        self.configure(menu=m)

        # 显示"值 ▾"，让人一眼看出能点
        self._var = var
        self.configure(textvariable="")

        def refresh(*_):
            self.configure(text=f"{var.get()}  ▾")
        var.trace_add("write", refresh)
        refresh()


class ThinScroll(tk.Canvas):
    """自绘细滚动条：8px 宽，跟随 Treeview。"""

    def __init__(self, parent, target, **kw):
        super().__init__(parent, width=8, bg=CARD, highlightthickness=0, bd=0, **kw)
        self.target = target
        self.first, self.last = 0.0, 1.0
        self._drag = None
        target.configure(yscrollcommand=self._on_scroll)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw(hover=False))

    def _on_scroll(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        h = self.winfo_height()
        if h <= 4 or self.last - self.first >= 0.999:
            return
        y0 = int(self.first * h)
        y1 = max(y0 + 24, int(self.last * h))
        col = ACCENT2 if hover else CARD2
        self.create_rectangle(2, y0, 7, y1, fill=col, outline="")

    def _press(self, e):
        h = self.winfo_height()
        y0, y1 = int(self.first * h), int(self.last * h)
        if y0 <= e.y <= y1:
            self._drag = e.y - y0
        else:
            self.target.yview_moveto(max(0.0, e.y / h))

    def _motion(self, e):
        if self._drag is None:
            return
        h = self.winfo_height()
        self.target.yview_moveto(max(0.0, (e.y - self._drag) / h))


class App:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.covers = {}
        self._tkimg = None
        self._pct = 0

        root.title("封皮贼 · JacketThief")
        root.configure(bg=BG)
        root.geometry("1120x760")
        root.minsize(980, 660)

        self.size_var = tk.StringVar(value="1920")
        self.mode_var = tk.StringVar(value="16:9 模糊填充")
        self.out_var = tk.StringVar(value=str(Path.home() / "Desktop" / "封面导出"))
        self.step = tk.StringVar(value="拖入音乐文件开始")

        self._build()
        self._bind_dnd()

    # ---------- 布局 ----------
    def _build(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=16, pady=14)

        left = tk.Frame(wrap, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        right = tk.Frame(wrap, bg=CARD, width=330)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        tk.Label(left, text="封皮贼", bg=BG, fg=FG,
                 font=(UI_FONT, 16, "bold")).pack(anchor="w")
        tk.Label(left, text="拖入音乐文件 · 自动扒出内嵌封面 · 一键导出封面图",
                 bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(anchor="w", pady=(0, 8))

        self.drop = tk.Canvas(left, bg=CARD, height=92, highlightthickness=0)
        self.drop.pack(fill="x")
        self.drop.bind("<Configure>", lambda e: self._draw_drop())
        self.drop.bind("<Button-1>", lambda e: self.pick_files())

        # 底部按钮区（先 pack，保证不被挤掉）
        bottom = tk.Frame(left, bg=BG)
        bottom.pack(side="bottom", fill="x")

        btns = tk.Frame(bottom, bg=BG)
        btns.pack(fill="x", pady=(10, 0))
        for text, cb, w in (("添加文件", self.pick_files, 98),
                            ("添加文件夹", self.pick_dir, 118),
                            ("清空", self.clear, 74)):
            btn = RoundedButton(btns, text=text, command=cb, width=w, height=34,
                                bg=BG, fg=FG, fill=CARD2, hover=ACCENT2,
                                font=(UI_FONT, 10), radius=10)
            btn.pack(side="left", padx=(0, 12))
        self.go = RoundedButton(btns, text="导出全部", command=self.export_all, width=124, height=34,
                                bg=BG, fg="#1b1a20", fill=ACCENT, hover="#cba8ff",
                                font=(UI_FONT, 10), radius=10)
        self.go.pack(side="right", padx=(12, 0))
        tk.Label(btns, textvariable=self.step, bg=BG, fg=DIM, anchor="w",
                 font=(UI_FONT, 9)).pack(side="left", padx=12, fill="x", expand=True)

        self.bar = tk.Canvas(bottom, bg=BG, height=4, highlightthickness=0)
        self.bar.pack(fill="x", pady=(6, 0))
        self.bar.bind("<Configure>", lambda e: self._draw_bar(self._pct))

        # 列表
        mid = tk.Frame(left, bg=CARD)
        mid.pack(fill="both", expand=True, pady=(8, 8))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("CG.Treeview", background=CARD, fieldbackground=CARD,
                        foreground=FG, rowheight=26, borderwidth=0, relief="flat",
                        bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
        style.layout("CG.Treeview", [("CG.Treeview.treearea", {"sticky": "nswe"})])
        style.configure("CG.Treeview.Heading", background=CARD2, foreground="#b9b3c4",
                        relief="flat", borderwidth=0, bordercolor=CARD2,
                        lightcolor=CARD2, darkcolor=CARD2)
        style.configure("CG.Vertical.TScrollbar", background=CARD2, troughcolor=CARD,
                        bordercolor=CARD, arrowcolor=DIM, relief="flat", borderwidth=0)
        style.map("CG.Vertical.TScrollbar", background=[("active", ACCENT2)])
        style.map("CG.Treeview", background=[("selected", ACCENT2)],
                  foreground=[("selected", "#ffffff")])

        cols = ("name", "cover", "size", "title")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=7,
                                 style="CG.Treeview")
        for c, t, w in (("name", "文件", 300), ("cover", "封面", 56),
                        ("size", "原图尺寸", 90), ("title", "标题", 300)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ThinScroll(mid, self.tree)
        sb.pack(side="right", fill="y", padx=(4, 0))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # 预览
        self.preview = tk.Canvas(left, bg=CARD, height=210, highlightthickness=0)
        self.preview.pack(fill="x")
        self.preview.bind("<Configure>", lambda e: self.on_select())
        self._draw_preview_empty()

        self._build_panel(right)

    def _build_panel(self, p):
        tk.Label(p, text="导出设置", bg=CARD, fg=FG,
                 font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=14, pady=(14, 8))

        def row(label, widget):
            f = tk.Frame(p, bg=CARD)
            f.pack(fill="x", padx=14, pady=3)
            tk.Label(f, text=label, bg=CARD, fg=DIM, width=5, anchor="w",
                     font=(UI_FONT, 9)).pack(side="left")
            widget(f)
            return f

        def size_widget(f):
            DarkSelect(f, self.size_var, ["1000", "1200", "1600", "1920", "2560", "3840"],
                       width=8).pack(side="left")

        def mode_widget(f):
            DarkSelect(f, self.mode_var, list(MODE_LABEL), width=15).pack(side="left")

        row("尺寸", size_widget)
        row("比例", mode_widget)

        f = tk.Frame(p, bg=CARD)
        f.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(f, text="输出目录", bg=CARD, fg=DIM, width=5, anchor="w",
                 font=(UI_FONT, 9)).pack(side="left")
        RoundedButton(f, text="选", command=self.pick_out, width=38, height=26,
                      bg=CARD, fg=FG, fill=CARD2, font=(UI_FONT, 9)).pack(
            side="right", padx=(6, 0))
        tk.Entry(f, textvariable=self.out_var, bg=CARD2, fg=FG, insertbackground=FG,
                 relief="flat", bd=0, font=(UI_FONT, 9)).pack(
            side="left", fill="x", expand=True, ipady=5)

        tk.Frame(p, bg=CARD2, height=1).pack(fill="x", padx=14, pady=14)

        tk.Label(p, text="比例说明", bg=CARD, fg=ACCENT,
                 font=(UI_FONT, 10, "bold")).pack(anchor="w", padx=14)
        for t in ("方形（原比例）  直接放大，适合专辑图",
                  "16:9 模糊填充  两侧用封面模糊铺满，适合视频封面",
                  "16:9 裁切铺满  裁掉上下留白，画面更满"):
            tk.Label(p, text=t, bg=CARD, fg=DIM, wraplength=290, justify="left",
                     anchor="w", font=(UI_FONT, 9)).pack(anchor="w", padx=14, pady=2)

        tk.Frame(p, bg=CARD2, height=1).pack(fill="x", padx=14, pady=14)
        tk.Label(p, text="没有封面怎么办", bg=CARD, fg=ACCENT,
                 font=(UI_FONT, 10, "bold")).pack(anchor="w", padx=14)
        tk.Label(p, text="列表里显示「—」表示这个文件没有内嵌封面。\n"
                         "可以另外找原图，本站不联网搜索。",
                 bg=CARD, fg=DIM, wraplength=290, justify="left", anchor="w",
                 font=(UI_FONT, 9)).pack(anchor="w", padx=14, pady=2)

    # ---------- 拖放 ----------
    def _bind_dnd(self):
        if HAS_WINDND:
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                windnd.hook_dropfiles(hwnd, self._on_windnd)
            except Exception:
                pass
        if HAS_DND:
            for w in (self.root, self.drop, self.tree, self.preview):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass

    def _on_windnd(self, files):
        paths = []
        for f in files:
            try:
                paths.append(f.decode("gbk"))
            except Exception:
                paths.append(f.decode("utf-8", "ignore"))
        self.add(paths)

    def _on_drop(self, e):
        self.add(list(self.root.tk.splitlist(e.data)))

    # ---------- 绘制 ----------
    def _draw_drop(self):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 4:
            return
        c.create_rectangle(2, 2, w - 2, h - 2, outline=CARD2, width=2, dash=(6, 4))
        c.create_text(w / 2, h / 2 - 10, text="把音乐文件或文件夹拖进来",
                      fill=FG, font=(UI_FONT, 11, "bold"))
        c.create_text(w / 2, h / 2 + 14, text="也可以点这里选择文件",
                      fill=DIM, font=(UI_FONT, 9))

    def _draw_preview_empty(self):
        c = self.preview
        c.delete("all")
        w, h = c.winfo_width() or 600, c.winfo_height() or 210
        c.create_text(w / 2, h / 2, text="选中上方的文件，这里预览封面",
                      fill=DIM, font=(UI_FONT, 10))

    def _draw_bar(self, pct):
        c = self.bar
        c.delete("all")
        w = c.winfo_width()
        if w <= 4:
            return
        c.create_rectangle(0, 0, w, 4, fill=CARD2, width=0)
        if pct > 0:
            c.create_rectangle(0, 0, int(w * pct), 4, fill=ACCENT, width=0)

    def _set_pct(self, p):
        self._pct = max(0.0, min(1.0, p))
        self.root.after(0, lambda: self._draw_bar(self._pct))

    # ---------- 数据 ----------
    def pick_files(self):
        fs = filedialog.askopenfilenames(
            filetypes=[("音频", "*.mp3 *.flac *.m4a *.ogg *.wav *.opus *.wma *.aac"),
                       ("全部", "*.*")])
        if fs:
            self.add(list(fs))

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.add([d])

    def pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def clear(self):
        self.files.clear()
        self.covers.clear()
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._draw_preview_empty()
        self.step.set("拖入音乐文件开始")
        self._set_pct(0)

    def add(self, paths):
        found = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                found += [f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT]
            elif p.suffix.lower() in AUDIO_EXT:
                found.append(p)
        new = 0
        for f in found:
            if f in self.files:
                continue
            self.files.append(f)
            img, info = extract_cover(f)
            self.covers[f] = img
            self.tree.insert("", "end", iid=str(f), values=(
                f.name, "✓" if img else "—", info, read_title(f)))
            new += 1
        if new:
            # 自动选中第一条，省得再点一下
            kids = self.tree.get_children()
            if kids and not self.tree.selection():
                self.tree.selection_set(kids[0])
                self.tree.focus(kids[0])
            nocover = sum(1 for f in found if self.covers.get(f) is None)
            msg = f"已添加 {new} 个文件"
            if nocover:
                msg += f"，其中 {nocover} 个没有内嵌封面"
            self.step.set(msg)
        else:
            self.step.set("没有可识别的音频文件")

    def on_select(self, _e=None):
        sel = self.tree.selection()
        c = self.preview
        c.delete("all")
        if not sel:
            self._draw_preview_empty()
            return
        p = Path(sel[0])
        img = self.covers.get(p)
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 4:
            return
        if img is None:
            c.create_text(w / 2, h / 2, text="这个文件没有内嵌封面", fill=DIM,
                          font=(UI_FONT, 11))
            return
        s = min(h - 20, 320)
        thumb = img.copy()
        thumb.thumbnail((s, s), Image.LANCZOS)
        self._tkimg = ImageTk.PhotoImage(thumb)
        c.create_image(14, h / 2, image=self._tkimg, anchor="w")
        tx = 14 + thumb.width + 18
        c.create_text(tx, h / 2 - 26, text=p.stem, fill=FG, anchor="w",
                      font=(UI_FONT, 11, "bold"))
        c.create_text(tx, h / 2, text=read_title(p) or "（无标题标签）", fill=DIM,
                      anchor="w", font=(UI_FONT, 9))
        c.create_text(tx, h / 2 + 24, text=f"原图 {img.width}×{img.height}", fill=DIM,
                      anchor="w", font=(UI_FONT, 9))

    def export_all(self):
        targets = [f for f in self.files if self.covers.get(f)]
        if not targets:
            messagebox.showinfo("提示", "没有可导出的封面\n（列表里全是「—」就说明这些文件没有内嵌封面）")
            return
        outdir = Path(self.out_var.get())
        outdir.mkdir(parents=True, exist_ok=True)
        size = int(self.size_var.get())
        mode = MODE_LABEL.get(self.mode_var.get(), "blur16x9")
        suffix = {"square": "", "blur16x9": "_16x9", "crop16x9": "_16x9裁切"}[mode]

        def run():
            self.go.set_state("disabled")
            self.go.set_text("导出中…")
            ok = 0
            for i, f in enumerate(targets, 1):
                try:
                    out = render(self.covers[f], mode, size)
                    dst = outdir / f"{safe_name(f.stem)}{suffix}.jpg"
                    n = 1
                    while dst.exists():
                        dst = outdir / f"{safe_name(f.stem)}{suffix}_{n}.jpg"
                        n += 1
                    out.save(dst, quality=95)
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    print("导出失败", f, e)
                self.step.set(f"导出 {i}/{len(targets)}")
                self._set_pct(i / len(targets))
            self.go.set_state("normal")
            self.go.set_text("导出全部")
            self.step.set(f"完成 {ok} 张 → {outdir}")
            self.root.after(300, lambda: self._set_pct(0))
            PU.open_path(outdir)

        threading.Thread(target=run, daemon=True).start()


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = App(root)
    # 支持把文件拖到快捷方式/命令行传参
    import sys
    args = [a for a in sys.argv[1:] if Path(a).exists()]
    if args:
        root.after(200, lambda: app.add(args))
    root.mainloop()


if __name__ == "__main__":
    main()
