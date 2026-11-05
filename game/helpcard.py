# -*- coding: utf-8 -*-
"""玩法手册图（帮助）。卡片网格布局：两列，接近方形，不拉长条。"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from . import card as C
from .card import (
    ACCENT,
    BG,
    GOLD,
    INK,
    LINE,
    SUB,
    _card,
    _font,
    _tw,
    plain,
)

W = 1080
PAD = 34
GAP = 18
COLS = 2
COL_W = (W - PAD * 2 - GAP * (COLS - 1)) // COLS
INNER = COL_W - 40


def available() -> bool:
    return C.available()


def _wrap(d, text: str, font, maxw: int, max_lines: int = 2) -> List[str]:
    rows: List[str] = []
    buf = ""
    no_start = "，。、；：！？」）)」』~～"
    for ch in text:
        if _tw(d, buf + ch, font) > maxw and buf:
            if ch in no_start:          # 标点不留行首
                buf += ch
                rows.append(buf)
                buf = ""
                if len(rows) >= max_lines:
                    return rows
                continue
            rows.append(buf)
            buf = ch
            if len(rows) >= max_lines:
                return rows
        else:
            buf += ch
    if buf:
        if len(rows) < max_lines:
            rows.append(buf)
        else:
            rows[-1] = rows[-1][:-1] + "…"
    return rows


def _measure(d, sec: Dict) -> int:
    kind = sec.get("kind", "cmds")
    f_desc = _font(15)
    h = 14 + 30 + 12          # 上内边距 + 标题 + 间距
    if kind == "tiers":
        n = len(sec.get("rows") or [])
        return h + ((n + 3) // 4) * 58 + 8
    for cmd, desc in sec.get("rows") or []:
        if kind == "kv":
            h += 32
            continue
        if str(cmd).strip():
            h += 27
        h += len(_wrap(d, plain(str(desc)), f_desc, INNER, 2)) * 21 + 8
    return h + 8


def _draw_card(d, x: int, y: int, sec: Dict, h: int) -> None:
    kind = sec.get("kind", "cmds")
    _card(d, [x, y, x + COL_W, y + h])
    f_title = _font(20, True)
    f_cmd = _font(17, True)
    f_desc = _font(15)

    tx = x + 20
    d.rounded_rectangle([tx, y + 18, tx + 5, y + 40], radius=3, fill=ACCENT)
    d.text((tx + 14, y + 16), plain(sec.get("label", "")), font=f_title, fill=INK)
    yy = y + 58

    if kind == "tiers":
        for i, (th, name) in enumerate(sec.get("rows") or []):
            r, c = divmod(i, 4)
            cx = tx + c * (INNER // 4)
            cy = yy + r * 58
            d.text((cx, cy), plain(str(name)), font=_font(15, True), fill=ACCENT)
            d.text((cx, cy + 23), str(th), font=_font(13), fill=SUB)
        return

    for cmd, desc in sec.get("rows") or []:
        cmd = plain(str(cmd)).strip()
        desc = plain(str(desc))
        if kind == "kv":
            d.text((tx, yy), cmd, font=_font(15, True), fill=INK)
            vw = _tw(d, desc, f_desc)
            d.text((x + COL_W - 20 - vw, yy), desc, font=f_desc, fill=SUB)
            yy += 32
            continue
        if cmd:
            d.text((tx, yy), cmd, font=f_cmd, fill=ACCENT)
            yy += 27
        for ln in _wrap(d, desc, f_desc, INNER, 2):
            d.text((tx, yy), ln, font=f_desc, fill=(70, 64, 72))
            yy += 21
        yy += 8


def render_help(data: Dict, out_path: str) -> str:
    """data: sections=[{label, rows, kind?}] / tiers=[(阈值, 名称)] / footer"""
    secs = list(data.get("sections") or [])
    if data.get("tiers"):
        secs.append({"label": "段位（只看综合实力）", "kind": "tiers", "rows": data["tiers"]})

    probe = Image.new("RGB", (W, 200), BG)
    dp = ImageDraw.Draw(probe)
    heights = [_measure(dp, s) for s in secs]

    cols: List[List[Tuple[Dict, int]]] = [[] for _ in range(COLS)]
    col_h = [0] * COLS
    for sec, h in zip(secs, heights):
        i = col_h.index(min(col_h))
        cols[i].append((sec, h))
        col_h[i] += h + GAP

    head_h = 116
    foot_h = 52
    total_h = head_h + max(col_h) + foot_h

    img = Image.new("RGB", (W, total_h), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 8], fill=ACCENT)
    d.text((PAD, 32), "娱乐圈星途 · 玩法手册", font=_font(24, True), fill=ACCENT)
    ver = "v3.3.1"
    d.text((W - PAD - _tw(d, ver, _font(15)), 40), ver, font=_font(15), fill=SUB)
    d.text((PAD, 70), "QQ 群 · 明星养成文字游戏　·　所有指令先 @机器人，或者用 / 开头",
           font=_font(17), fill=SUB)

    top = head_h - 14
    for ci in range(COLS):
        x = PAD + ci * (COL_W + GAP)
        y = top
        for sec, h in cols[ci]:
            _draw_card(d, x, y, sec, h)
            y += h + GAP

    fy = total_h - foot_h + 12
    d.line([PAD, fy - 12, W - PAD, fy - 12], fill=LINE, width=1)
    d.text((PAD, fy), plain(data.get("footer", "第一件事：@机器人 出道")), font=_font(15), fill=SUB)

    img.save(out_path, "PNG")
    return out_path
