"""把游戏数据画成卡片（Pillow）：艺人面板 / 排行榜 / 艺人档案。

对外只暴露四个函数：available() / render() / render_rank() / render_npc()。
画不出字体或没装 Pillow 时 available() 返回 False，调用方回退文字。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

try:  # 没装 Pillow 的环境要能降级成文字
    from PIL import Image, ImageDraw, ImageFont

    PIL_OK = True
except Exception:  # pragma: no cover
    PIL_OK = False

# ---------------- 设计变量 ----------------
W = 760
PAD = 40

BG = (247, 244, 246)
CARD = (255, 255, 255)
INK = (28, 24, 30)
SUB = (126, 118, 126)
LINE = (236, 229, 233)
ACCENT = (150, 40, 78)
ACCENT_DARK = (112, 26, 56)
ACCENT_SOFT = (233, 205, 216)
ACCENT_TINT = (250, 240, 244)
GOLD = (176, 122, 56)
GOLD_SOFT = (243, 232, 214)
BAD = (172, 62, 62)

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


def _tw(d, text: str, font) -> int:
    try:
        box = d.textbbox((0, 0), text, font=font)
        return box[2] - box[0]
    except Exception:
        return int(len(text) * getattr(font, "size", 12) * 0.62)


def _card(d, box, r: int = 18, fill=CARD, outline=LINE) -> None:
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=1)


def _bar(d, x: int, y: int, w: int, h: int, ratio: float, fill=ACCENT) -> None:
    ratio = max(0.0, min(1.0, float(ratio)))
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(238, 230, 234))
    if ratio > 0:
        fw = max(h, int(w * ratio))
        d.rounded_rectangle([x, y, x + fw, y + h], radius=h // 2, fill=fill)


def _pill(d, x: int, y: int, text: str, font, fg, bg, padx: int = 14, h: int = 34) -> int:
    tw = _tw(d, text, font)
    box = [x, y, x + tw + padx * 2, y + h]
    d.rounded_rectangle(box, radius=h // 2, fill=bg)
    th = getattr(font, "size", 16)
    d.text((x + padx, y + (h - th) / 2 - 2), text, font=font, fill=fg)
    return box[2] - x


def _header(d, left: str, right: str = "", y: int = 30) -> None:
    f = _font(20, True)
    fs = _font(15)
    d.text((PAD, y), left, font=f, fill=ACCENT)
    if right:
        d.text((W - PAD - _tw(d, right, fs), y + 3), right, font=fs, fill=SUB)


def _section(d, y: int, label: str, right: str = "") -> int:
    f = _font(16, True)
    fs = _font(15)
    d.rounded_rectangle([PAD, y + 6, PAD + 5, y + 26], radius=3, fill=ACCENT)
    d.text((PAD + 16, y + 4), label, font=f, fill=SUB)
    if right:
        d.text((W - PAD - _tw(d, right, fs), y + 6), right, font=fs, fill=SUB)
    return y + 40


def _attr_rows(d, y: int, attrs: Sequence[Tuple[str, int]], scale: int, height_hint: int = 0) -> int:
    f = _font(19, True)
    fv = _font(20, True)
    for label, val in attrs:
        d.text((PAD + 22, y), label, font=f, fill=INK)
        bx = PAD + 108
        bw = W - PAD * 2 - 108 - 92
        _bar(d, bx, y + 8, bw, 12, val / max(1, scale))
        vtxt = str(val)
        d.text((W - PAD - 22 - _tw(d, vtxt, fv), y - 1), vtxt, font=fv, fill=ACCENT)
        y += 52
    return y


def _affection_rows(d, y: int, items: Sequence[dict], x: int = PAD + 22, width: int = 0) -> int:
    f = _font(17)
    fv = _font(17, True)
    for it in items[:6]:
        nm = plain(it.get("name", ""))
        val = int(it.get("affection", 0) or 0)
        d.text((x, y), nm, font=f, fill=INK)
        vtxt = f"{val:+d}"
        col = ACCENT if val > 0 else BAD
        d.text((x + (width or (W - PAD * 2 - 44)) - _tw(d, vtxt, fv), y), vtxt, font=fv, fill=col)
        y += 32
    return y


def _wrap_text(d, text: str, font, maxw: int, max_lines: int = 2) -> List[str]:
    """按像素宽度折行，超出 max_lines 的部分用省略号收掉。"""
    text = plain(text)
    rows: List[str] = []
    buf = ""
    for ch in text:
        if _tw(d, buf + ch, font) > maxw:
            cut = buf
            if len(buf) > 6:
                for i in range(len(buf) - 1, max(2, len(buf) - 14), -1):
                    if buf[i] in " ｜，。、；·）)":
                        cut = buf[: i + 1]
                        break
            rows.append(cut)
            buf = buf[len(cut):] + ch
            if len(rows) == max_lines:
                break
        else:
            buf += ch
    if len(rows) < max_lines and buf:
        rows.append(buf)
    if len(rows) == max_lines:
        rest = text[sum(len(r) for r in rows):]
        if rest:
            last = rows[-1]
            while last and _tw(d, last + "…", font) > maxw:
                last = last[:-1]
            rows[-1] = last + "…"
    return rows


def _timeline_rows(d, y: int, items: Sequence[str], x: int = PAD + 44) -> int:
    f = _font(16)
    maxw = W - PAD - x
    for line in items[:4]:
        d.ellipse([x - 18, y + 7, x - 10, y + 15], fill=ACCENT_SOFT)
        for i, ln in enumerate(_wrap_text(d, line, f, maxw, 2)):
            d.text((x, y), ln, font=f, fill=(64, 58, 66))
            y += 26
        y += 6
    return y


def _save(img, y_end: int, out_path: str) -> str:
    end = max(240, min(img.height, y_end))
    img = img.crop((0, 0, W, end))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _footer(d, y: int, text: str) -> int:
    f = _font(15)
    d.line([PAD, y, W - PAD, y], fill=LINE, width=1)
    d.text((PAD, y + 14), text, font=f, fill=SUB)
    return y + 46


# ---------------- 个人面板 ----------------
def render(data: Dict, out_path: str) -> str:
    """data 的字段见 main._status_image；返回图片路径。"""
    attrs: Sequence[Tuple[str, int]] = data.get("attrs") or []
    acts: Sequence[Tuple[str, bool]] = data.get("acts") or []
    recent: Sequence[str] = data.get("recent") or []
    affs: Sequence[dict] = data.get("affections") or []

    img = Image.new("RGB", (W, 1700), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)

    f_name = _font(42, True)
    f_tier = _font(18, True)
    f_big = _font(40, True)
    f_mid = _font(20, True)
    f_body = _font(18)
    f_small = _font(16)
    f_tiny = _font(14)

    _header(d, "娱乐圈星途 · 艺人面板", plain(data.get("updated", "")))
    y = 84

    # --- 姓名 + 段位 + 综合实力 ---
    name = plain(data.get("name", ""))
    d.text((PAD, y), name, font=f_name, fill=INK)
    nw = _tw(d, name, f_name)
    tier = plain(data.get("tier", ""))
    if tier:
        _pill(d, PAD + nw + 16, y + 12, tier, f_tier, (255, 255, 255), ACCENT, padx=16, h=36)

    total_txt = str(data.get("total", 0))
    tw = _tw(d, total_txt, f_big)
    d.text((W - PAD - tw, y - 4), total_txt, font=f_big, fill=ACCENT)
    lab = "综合实力"
    d.text((W - PAD - _tw(d, lab, f_tiny), y + 46), lab, font=f_tiny, fill=SUB)
    y += 92

    nxt = plain(data.get("next_text", ""))
    if nxt:
        d.text((PAD, y), nxt, font=f_small, fill=SUB)
    y += 28
    _bar(d, PAD, y, W - PAD * 2, 12, float(data.get("pct", 0.0)))
    y += 36

    # --- 资料胶囊：性别 / 风格 / 粉丝 / 战绩 ---
    g_txt = plain(data.get("gender")) or "未填"
    s_txt = plain(data.get("style")) or "未定"
    prof_bits = [
        (f"性别 {g_txt}", False),
        (f"风格 {s_txt}", False),
        (f"星币 {int(data.get('coins') or 0)}", True),
        (f"粉丝 {plain(data.get('fans_text')) or 0}", False),
        (f"战绩 {plain(data.get('record'))}", False),
    ]
    cx = PAD
    for text, gold in prof_bits:
        txt = text.strip()
        if not txt:
            continue
        w_pill = _tw(d, txt, f_tiny) + 26
        if cx + w_pill > W - PAD:
            break
        _pill(d, cx, y, txt, f_tiny,
              GOLD if gold else SUB,
              GOLD_SOFT if gold else (243, 240, 242))
        cx += w_pill + 8
    y += 52

    # --- 四格数字 ---
    stats = [
        (str(data.get("coins", 0)), "星币"),
        (f"{data.get('bag', 0)} 件", "背包"),
        (f"{data.get('ach_got', 0)}/{data.get('ach_all', 0)}", "成就"),
        (f"{data.get('streak', 0)} 天", "连签"),
    ]
    box_h = 92
    _card(d, [PAD, y, W - PAD, y + box_h])
    cw = (W - PAD * 2) / 4
    for i, (val, lab) in enumerate(stats):
        cx = PAD + cw * i + cw / 2
        d.text((cx - _tw(d, val, f_mid) / 2, y + 20), val, font=f_mid, fill=INK)
        d.text((cx - _tw(d, lab, f_tiny) / 2, y + 54), lab, font=f_tiny, fill=SUB)
        if i:
            d.line([PAD + cw * i, y + 22, PAD + cw * i, y + box_h - 22], fill=LINE, width=1)
    y += box_h + 26

    # --- 四项属性 ---
    y = _section(d, y, "四项属性")
    card_h = 52 * len(attrs) + 16
    _card(d, [PAD, y - 6, W - PAD, y - 6 + card_h])
    _attr_rows(d, y + 12, attrs, int(data.get("attr_scale", 300)))
    y += card_h + 20

    # --- 人气 ---
    y = _section(d, y, "人气")
    renqi = data.get("renqi", 0)
    d.text((PAD + 2, y - 14), str(renqi), font=f_mid, fill=GOLD)
    pop = plain(data.get("pop_title", ""))
    if pop:
        _pill(d, PAD + 90, y - 16, pop, f_tiny, GOLD, GOLD_SOFT, padx=12, h=28)
    _bar(d, PAD, y + 22, W - PAD * 2, 10, float(data.get("pop_pct", 0.0)), fill=GOLD)
    y += 46

    # --- 今日 ---
    todo = plain(data.get("todo", ""))
    if todo or acts:
        y = _section(d, y, "今日")
        if todo:
            d.text((PAD + 2, y - 8), todo, font=f_small, fill=(64, 58, 66))
            y += 32
        cx = PAD + 2
        for label, done in acts:
            label = plain(label)
            wdt = _tw(d, label, f_tiny) + 26
            if cx + wdt > W - PAD:
                cx = PAD + 2
                y += 38
            if done:
                d.rounded_rectangle([cx, y - 6, cx + wdt, y + 24], radius=15, fill=ACCENT_TINT,
                                    outline=ACCENT_SOFT)
                d.text((cx + 13, y - 2), label, font=f_tiny, fill=ACCENT)
            else:
                d.rounded_rectangle([cx, y - 6, cx + wdt, y + 24], radius=15, fill=(243, 240, 242))
                d.text((cx + 13, y - 2), label, font=f_tiny, fill=SUB)
            cx += wdt + 10
        y += 44

    # --- 好感 ---
    if affs:
        y = _section(d, y, "好感", "负数为不待见")
        card_h = 32 * len(affs[:6]) + 18
        _card(d, [PAD, y - 8, W - PAD, y - 8 + card_h])
        _affection_rows(d, y + 5, affs)
        y += card_h + 18

    # --- 最近动态 ---
    if recent:
        y = _section(d, y, "最近动态")
        y = _timeline_rows(d, y - 6, recent)
        y += 6

    # --- 伴侣 / 待回复 ---
    partner = data.get("partner")
    pending = data.get("pending")
    if partner or pending:
        box = [PAD, y, W - PAD, y + 62]
        _card(d, box, fill=ACCENT_TINT, outline=ACCENT_SOFT)
        if partner:
            d.text((PAD + 18, y + 12), "伴侣", font=f_tiny, fill=SUB)
            d.text((PAD + 18, y + 32), plain(partner), font=f_small, fill=ACCENT)
        if pending:
            d.text((W - PAD - 18 - _tw(d, plain(pending), f_tiny), y + 20), plain(pending),
                   font=f_tiny, fill=SUB)
        y += 76

    y = _footer(d, y, "发「帮助」看全部玩法 · 发「属性 文字」看文字版")
    return _save(img, y, out_path)


# ---------------- 排行榜 ----------------
def render_rank(data: Dict, out_path: str) -> str:
    """排行榜图片。data: {label, rows:[{name,value,sub}], updated}"""
    rows: List[dict] = list(data.get("rows") or [])
    img = Image.new("RGB", (W, 220 + 66 * max(1, len(rows))), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)

    f_big = _font(34, True)
    f_head = _font(15, True)
    f_name = _font(21, True)
    f_sub = _font(15)
    f_val = _font(24, True)
    f_num = _font(17, True)

    _header(d, "娱乐圈星途 · 排行榜", plain(data.get("updated", "")))
    y = 86
    d.text((PAD, y), plain(data.get("label", "")), font=f_big, fill=INK)
    y += 62

    # 列头
    d.text((PAD + 14, y), "名次", font=f_head, fill=SUB)
    d.text((W - PAD - _tw(d, "数值", f_head), y), "数值", font=f_head, fill=SUB)
    d.line([PAD, y + 26, W - PAD, y + 26], fill=LINE, width=1)
    y += 40

    for i, it in enumerate(rows, 1):
        row_h = 62
        top3 = i <= 3
        if top3:
            _card(d, [PAD, y - 4, W - PAD, y + row_h - 8], fill=ACCENT_TINT, outline=ACCENT_SOFT)
        elif i % 2 == 0:
            d.rounded_rectangle([PAD, y - 4, W - PAD, y + row_h - 8], radius=14, fill=(252, 250, 251))

        # 名次徽章
        bx = PAD + 14
        by = y + 8
        if top3:
            d.ellipse([bx, by, bx + 30, by + 30], fill=ACCENT if i == 1 else ACCENT_SOFT)
            num_col = (255, 255, 255) if i == 1 else ACCENT_DARK
        else:
            d.ellipse([bx, by, bx + 30, by + 30], outline=LINE, width=1)
            num_col = SUB
        num = str(i)
        d.text((bx + 15 - _tw(d, num, f_num) / 2, by + 3), num, font=f_num, fill=num_col)

        # 名字 / 副标题
        nm = plain(it.get("name", ""))
        d.text((PAD + 58, y + 4), nm, font=f_name, fill=INK)
        sub = plain(it.get("sub", ""))
        if sub:
            d.text((PAD + 58, y + 30), sub, font=f_sub, fill=SUB)

        vtxt = str(it.get("value", ""))
        d.text((W - PAD - 18 - _tw(d, vtxt, f_val), y + 8), vtxt, font=f_val,
               fill=ACCENT if top3 else INK)
        y += row_h

    y = _footer(d, y + 6, "默认只排玩家 · 发「排行 全」连 NPC 一起排 · 「排行 文字」看文字版")
    return _save(img, y, out_path)


# ---------------- 艺人档案（NPC / 其他玩家） ----------------
def render_npc(data: Dict, out_path: str) -> str:
    """NPC / 其他艺人的资料卡。"""
    attrs: Sequence[Tuple[str, int]] = data.get("attrs") or []
    affs: Sequence[dict] = data.get("affections") or []

    img = Image.new("RGB", (W, 1500), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)

    f_name = _font(42, True)
    f_tier = _font(18, True)
    f_big = _font(38, True)
    f_mid = _font(20, True)
    f_body = _font(18)
    f_small = _font(16)
    f_tiny = _font(14)

    tag = plain(data.get("tag", ""))
    _header(d, "娱乐圈星途 · 艺人档案", tag)
    y = 84

    name = plain(data.get("name", ""))
    d.text((PAD, y), name, font=f_name, fill=INK)
    nw = _tw(d, name, f_name)
    tier = plain(data.get("tier", ""))
    if tier:
        _pill(d, PAD + nw + 16, y + 12, tier, f_tier, (255, 255, 255), ACCENT, padx=16, h=36)
    y += 74

    # 资料胶囊
    chips = []
    if data.get("gender"):
        chips.append(("性别 " + plain(data["gender"]), SUB, (243, 240, 242)))
    if data.get("style"):
        chips.append(("风格 " + plain(data["style"]), INK, (243, 240, 242)))
    if data.get("fans_text"):
        chips.append(("粉丝 " + plain(data["fans_text"]), GOLD, GOLD_SOFT))
    if data.get("coins") is not None:
        chips.append((f"星币 {data.get('coins')}", ACCENT, ACCENT_TINT))
    cx = PAD
    for text, fg, bg in chips:
        wdt = _tw(d, text, f_tiny) + 24
        if cx + wdt > W - PAD:
            cx = PAD
            y += 38
        _pill(d, cx, y, text, f_tiny, fg, bg, padx=12, h=30)
        cx += wdt + 10
    y += 52

    # 综合实力
    total = str(data.get("total", 0))
    d.text((PAD, y), "综合实力", font=f_small, fill=SUB)
    d.text((PAD + 92, y - 10), total, font=f_big, fill=ACCENT)
    y += 56
    _bar(d, PAD, y, W - PAD * 2, 12, float(data.get("pct", 0.0)))
    y += 36

    # 四项
    y = _section(d, y, "四项属性")
    card_h = 52 * len(attrs) + 16
    _card(d, [PAD, y - 6, W - PAD, y - 6 + card_h])
    _attr_rows(d, y + 12, attrs, int(data.get("attr_scale", 300)))
    y += card_h + 20

    # 人气
    y = _section(d, y, "人气")
    d.text((PAD + 2, y - 14), str(data.get("renqi", 0)), font=f_mid, fill=GOLD)
    y += 26

    # 人设
    persona = plain(data.get("persona", ""))
    if persona:
        y = _section(d, y, "人设")
        line, lines = "", []
        for ch in persona:
            if _tw(d, line + ch, f_body) > W - PAD * 2 - 56:
                lines.append(line)
                line = ch
            else:
                line += ch
        if line:
            lines.append(line)
        lines = lines[:5]
        card_h = 32 * len(lines) + 26
        _card(d, [PAD, y - 6, W - PAD, y - 6 + card_h], fill=(252, 250, 251))
        d.rounded_rectangle([PAD + 18, y + 8, PAD + 22, y + 8 + card_h - 28], radius=2, fill=ACCENT_SOFT)
        ty = y + 8
        for ln in lines:
            d.text((PAD + 38, ty), ln, font=f_body, fill=(62, 56, 64))
            ty += 32
        y += card_h + 18

    # 好感
    if affs:
        y = _section(d, y, "好感", "负数为不待见")
        card_h = 32 * len(affs[:6]) + 18
        _card(d, [PAD, y - 8, W - PAD, y - 8 + card_h])
        _affection_rows(d, y + 5, affs)
        y += card_h + 16

    # 最近动态
    recent = list(data.get("recent") or [])[:3]
    if recent:
        y = _section(d, y, "最近动态")
        y = _timeline_rows(d, y - 6, recent)
        y += 6

    y = _footer(d, y, "发「明星 名字」看任意艺人 · 发「属性 文字」看文字版")
    return _save(img, y, out_path)
