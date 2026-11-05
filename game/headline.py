# -*- coding: utf-8 -*-
"""今日娱乐头条：从最近的事件流水里挑几条 NPC 动态，做成一条播报。

只在「值得播」的事件类型里挑（代言、影视、争议、翻车…），
搭话/发博这类流水账不进头条。
"""

from __future__ import annotations

import random
import re
from typing import List, Optional

from .const import EVENT_POLARITY

# 值得上头条的规定
HYPE_KINDS = {
    "代言", "影视", "音乐", "时尚", "应援", "综艺", "奖项", "商务",
    "路透", "票房", "版权", "打歌", "杀青", "巡演", "剧组", "跨界",
    "热搜", "翻红", "翻车", "爆红", "塌房", "争议", "私生", "黑料",
    "解约", "破音", "恋爱", "官宣", "合约", "生病", "对家", "剪辑",
    "直播", "商务翻车", "绯闻", "结婚", "分手",
}

EMOJI = {1: "🎉", -1: "💥", 0: "📌"}


def _emoji(kind: str) -> str:
    pol = int(EVENT_POLARITY.get(str(kind or ""), 0))
    if pol > 0:
        return EMOJI[1]
    if pol < 0:
        return EMOJI[-1]
    return EMOJI[0]


def _strip_effects(text: str) -> str:
    """去掉事件尾巴上的「（实力 +5｜星币 +24｜粉丝 +1,344）」。"""
    t = (text or "").strip()
    idx = t.find("（实力")
    if idx > 0:
        t = t[:idx]
    return t.strip()


def build(store, gid: str, count: int = 3, days: int = 2) -> Optional[str]:
    """返回一条头条文本；没有可播的就返回 None。"""
    rows = store.recent_events(gid, limit=80)
    if not rows:
        return None
    # 只留最近 days 天、且属于「值得播」的类型
    from datetime import date, timedelta

    floor = (date.today() - timedelta(days=days - 1)).isoformat()
    cands = [
        r
        for r in rows
        if str(r.get("day", "")) >= floor and str(r.get("kind", "")) in HYPE_KINDS
    ]
    if not cands:
        return None

    # 同一个人最多出现一次，避免头条全是某个 NPC
    picked: List[dict] = []
    seen_names = set()
    seen_tmpl = set()
    for r in cands:
        text = _strip_effects(str(r.get("text", "")))
        if len(text) < 8:
            continue
        head = text.split(" ")[0]
        if head in seen_names:
            continue
        # 同一套模板只留一条（换个名字也是一样的话）
        tmpl = re.sub(r"^[^ ]+ ", "", text)[:12]
        if tmpl in seen_tmpl:
            continue
        seen_names.add(head)
        seen_tmpl.add(tmpl)
        picked.append({"kind": r["kind"], "text": text})
        if len(picked) >= max(1, count):
            break

    if not picked:
        return None
    # 保留最近的那条在第一位，其余随机，看起来更像编辑部挑的
    rest = picked[1:]
    random.shuffle(rest)
    picked = picked[:1] + rest

    lines = [f"📰 今日娱乐头条 · {date.today().strftime('%m-%d')}"]
    for it in picked:
        lines.append(f"{_emoji(it['kind'])} {it['kind']}｜{it['text']}")
    lines.append("—— 发「明星 名字」看他的完整档案")
    return "\n".join(lines)
