"""把玩家面板画成一张图（Pillow），给「属性」指令实时生成。"""

from __future__ import annotations

import os
from typing import Dict, Sequence, Tuple

try:  # 没装 Pillow 的环境要能降级成文字
    from PIL import Image, ImageDraw, ImageFont

    PIL_OK = True
except Exception:  # pragma: no cover
    PIL_OK = False

W = 760
PAD = 44
BG = (251, 243, 246)
CARD = (255, 255, 255)
ACCENT = (142, 36, 78)
ACCENT_SOFT = (232, 201, 213)
INK = (36, 34, 40)
GREY = (128, 122, 132)
LINE = (235, 224, 229)
WARM = (196, 106, 68)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
BOLD_CANDIDATES = [r"C:\Windows\Fonts\msyhbd.ttc"] + FONT_CANDIDATES


def _font(size: int, bold: bool = False):
    for p in BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                break
    return ImageFont.load_default()


def available() -> bool:
    return PIL_OK and any(os.path.exists(p) for p in FONT_CANDIDATES)


def plain(text: str) -> str:
    """雅黑没有 emoji 字形，画图前把 emoji / 装饰符号去掉，避免出现方块。"""
    out = []
    for ch in str(text or ""):
        c = ord(ch)
        if c < 0x2000:  # 拉丁、数字、常见标点
            out.append(ch)
        elif 0x3000 <= c <= 0x9FFF:  # CJK 标点、假名、汉字
            out.append(ch)
        elif 0xFF00 <= c <= 0xFFEF:  # 全角字符
            out.append(ch)
        elif ch in "—–·…“”‘’　":
            out.append(ch)
        elif ch in "●○":
            out.append(ch)
    return "".join(out).strip()


def _text_w(draw, text: str, font) -> int:
    try:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]
    except Exception:
        return int(len(text) * getattr(font, "size", 12) * 0.62)


def _bar(draw, x: int, y: int, w: int, h: int, ratio: float, fill=ACCENT):
    ratio = max(0.0, min(1.0, float(ratio)))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=ACCENT_SOFT)
    if ratio > 0:
        fw = max(h, int(w * ratio))
        draw.rounded_rectangle([x, y, x + fw, y + h], radius=h // 2, fill=fill)


def render(data: Dict, out_path: str) -> str:
    """data 的字段见 main._status_image；返回图片路径。"""
    attrs: Sequence[Tuple[str, int]] = data.get("attrs") or []
    acts: Sequence[Tuple[str, bool]] = data.get("acts") or []
    recent: Sequence[str] = data.get("recent") or []

    img = Image.new("RGB", (W, 1500), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=ACCENT)

    f_title = _font(22, True)
    f_name = _font(40, True)
    f_pill = _font(19, True)
    f_big = _font(34, True)
    f_mid = _font(21, True)
    f_body = _font(19)
    f_small = _font(17)
    f_tiny = _font(15)

    y = 34
    d.text((PAD, y), "娱乐圈星途 · 艺人面板", font=f_title, fill=ACCENT)
    upd = plain(data.get("updated", ""))
    d.text((W - PAD - _text_w(d, upd, f_tiny), y + 6), upd, font=f_tiny, fill=GREY)
    y += 46

    # 名字 + 段位
    name = plain(data.get("name", ""))
    d.text((PAD, y), name, font=f_name, fill=INK)
    nw = _text_w(d, name, f_name)
    pill = plain(data.get("tier", ""))
    pw = _text_w(d, pill, f_pill) + 30
    px = PAD + nw + 18
    if pill and px + pw < W - PAD:
        d.rounded_rectangle([px, y + 14, px + pw, y + 52], radius=19, fill=ACCENT)
        d.text((px + 15, y + 22), pill, font=f_pill, fill=(255, 255, 255))

    # 综合实力
    y += 74
    d.text((PAD, y + 8), "综合实力", font=f_small, fill=GREY)
    total_txt = str(data.get("total", 0))
    d.text((PAD + 84, y - 8), total_txt, font=f_big, fill=ACCENT)
    tw = _text_w(d, total_txt, f_big)
    nxt = plain(data.get("next_text", ""))
    if nxt:
        d.text((PAD + 96 + tw, y + 10), nxt, font=f_tiny, fill=GREY)

    y += 48
    _bar(d, PAD, y, W - PAD * 2, 12, data.get("pct", 0.0))
    y += 36

    # 四项
    for label, val in attrs:
        d.text((PAD, y), label, font=f_mid, fill=INK)
        bx = PAD + 92
        bw = W - PAD * 2 - 92 - 84
        _bar(d, bx, y + 9, bw, 12, val / max(1, data.get("attr_scale", 300)))
        vtxt = str(val)
        d.text((W - PAD - _text_w(d, vtxt, f_mid), y), vtxt, font=f_mid, fill=ACCENT)
        y += 54

    # 人气
    y += 10
    renqi = data.get("renqi", 0)
    d.text((PAD, y), "人气", font=f_mid, fill=INK)
    d.text((PAD + 92, y), str(renqi), font=f_mid, fill=WARM)
    rw = _text_w(d, str(renqi), f_mid)
    title = plain(data.get("pop_title", ""))
    if title:
        d.text((PAD + 92 + rw + 10, y + 3), f"（{title}）", font=f_small, fill=GREY)
    y += 36
    _bar(d, PAD, y, W - PAD * 2, 10, data.get("pop_pct", 0.0), fill=WARM)
    y += 42

    # 四个数字块
    stats = [
        ("星币", str(data.get("coins", 0))),
        ("背包", f"{data.get('bag', 0)} 件"),
        ("成就", f"{data.get('ach_got', 0)}/{data.get('ach_all', 0)}"),
        ("连签", f"{data.get('streak', 0)} 天" if data.get("streak") else "未开始"),
    ]
    d.rounded_rectangle([PAD, y, W - PAD, y + 84], radius=18, fill=CARD, outline=LINE)
    cw = (W - PAD * 2) / 4
    for i, (k, v) in enumerate(stats):
        cx = PAD + cw * i + 22
        d.text((cx, y + 16), k, font=f_tiny, fill=GREY)
        d.text((cx, y + 40), v, font=f_mid, fill=INK)
    y += 108

    # 今日
    d.text((PAD, y), "今日", font=f_small, fill=GREY)
    d.text((PAD + 62, y - 3), plain(data.get("todo", "")), font=f_body, fill=INK)
    y += 42
    if acts:
        x = PAD
        for label, ok in acts:
            label = plain(label)
            d.ellipse([x, y + 7, x + 11, y + 18], fill=ACCENT if ok else (222, 214, 220))
            d.text((x + 18, y), label, font=f_small, fill=INK if ok else GREY)
            x += 18 + _text_w(d, label, f_small) + 22
        y += 40

    # 最近动态
    if recent:
        y += 6
        d.text((PAD, y), "最近动态", font=f_small, fill=GREY)
        y += 30
        for line in recent:
            d.ellipse([PAD + 2, y + 8, PAD + 9, y + 15], fill=ACCENT_SOFT)
            d.text((PAD + 20, y), plain(line), font=f_tiny, fill=(74, 68, 78))
            y += 38

    # 伴侣 / 待回复
    box = data.get("partner") or data.get("pending")
    if box:
        y += 8
        d.rounded_rectangle([PAD, y, W - PAD, y + 46], radius=14, fill=(252, 238, 242))
        d.text((PAD + 16, y + 11), plain(box), font=f_body, fill=ACCENT)
        y += 46

    # 裁到内容高度，再把页脚贴到底部
    end = min(1500, y + 74)
    img = img.crop((0, 0, W, end))
    d = ImageDraw.Draw(img)
    d.line([PAD, end - 44, W - PAD, end - 44], fill=LINE, width=2)
    d.text((PAD, end - 32), "发「帮助」看全部玩法　·　发「属性 文字」看文字版",
           font=f_tiny, fill=GREY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
