"""系统驱动的 NPC 明星：自动成长、今日热搜、约战、台词。"""

from __future__ import annotations

import random
from typing import List, Optional

from .const import ATTR_KEYS, NPC_ROSTER
from .engine import now_iso, today, total_power

NEWS_TEMPLATES = [
    "疑似 {npc} 深夜与神秘人共进晚餐，全程低头快走。",
    "{npc} 新专辑预告只有 8 秒，评论区已经在拆摩斯密码。",
    "有站姐拍到 {npc} 在练习室留到凌晨三点，灯一直没关。",
    "{npc} 被问『最近在谈恋爱吗』，只笑不答，热搜挂了三小时。",
    "{npc} 的旧照被翻出来，粉丝：这也可以出道？",
    "{npc} 在机场给的签名写错自己名字，本人连夜发博道歉。",
    "{npc} 与导演吃饭被拍，新片传闻满天飞。",
    "{npc} 直播时手机弹出一条消息，镜头被他手速盖住了。",
]


def ensure_npcs(store, gid: str) -> List[dict]:
    """把 NPC 名册同步进当前群（幂等）。"""
    exist = {s["npc_key"] for s in store.npcs(gid)}
    for npc in NPC_ROSTER:
        if npc["key"] in exist:
            continue
        store.create_star(
            gid,
            f"npc:{npc['key']}",
            npc["name"],
            is_npc=True,
            npc_key=npc["key"],
            attrs=npc["attrs"],
            persona=f"{npc['tag']}。{npc['persona']}",
            renqi=min(400, sum(npc["attrs"].values()) // 10 + 20),
        )
    return store.npcs(gid)


async def daily_tick(store, ai, gid: str, news_enabled: bool = True) -> Optional[str]:
    """给 NPC 涨一波属性，并生成今日热搜。返回要播报的文本。

    跨天判定由调用方（main._daily）负责，这里只做事，避免两次判断打架。
    """
    players = store.players(gid)
    leader = max((total_power(p) for p in players), default=300)
    target = max(300, int(leader * 0.9))

    for npc in store.npcs(gid):
        persona = next(
            (n for n in NPC_ROSTER if n["key"] == npc["npc_key"]),
            {"growth": 1.0},
        )
        cur = total_power(npc)
        gap = target - cur
        if gap > 0:
            gain = max(20, int(gap * 0.25)) * float(persona.get("growth", 1.0))
        else:
            gain = random.randint(5, 20) * float(persona.get("growth", 1.0))
        gain = int(gain * random.uniform(0.7, 1.3))

        # 加在专长上更多
        weights = {k: 1.0 for k in ATTR_KEYS}
        top = max(ATTR_KEYS, key=lambda k: int(npc[k]))
        weights[top] = 2.5
        wsum = sum(weights.values())
        for k in ATTR_KEYS:
            npc[k] = int(npc[k]) + int(gain * weights[k] / wsum)
        # 实力涨了，热度也跟着涨一点（顶流不会掉队）
        npc["renqi"] = min(500, int(npc.get("renqi", 10) or 0) + max(1, gain // 6))
        store.save_star(npc)

    if not news_enabled:
        return None

    npcs = store.npcs(gid)
    names = [n["name"] for n in npcs]
    lines = await ai.generate_news(names, [p["name"] for p in players])
    if not lines:
        picked = random.sample(names, k=min(4, len(names)))
        lines = [tpl.format(npc=name) for tpl, name in zip(random.sample(NEWS_TEMPLATES, 4), picked)]
    body = "\n".join(f"  · {ln}" for ln in lines)
    return f"📰 今日娱乐圈热搜\n{body}"


def random_npc(
    store, gid: str, exclude: Optional[str] = None, near: Optional[int] = None
) -> Optional[dict]:
    """挑一个 NPC 对手：给了 near（自己的综合实力）就优先挑实力接近的。"""
    npcs = [n for n in store.npcs(gid) if n["qq_id"] != exclude]
    if not npcs:
        return None
    if near is None:
        return random.choice(npcs)
    ranked = sorted(npcs, key=lambda n: abs(total_power(n) - near))
    pool = ranked[:2] if len(ranked) >= 2 else ranked
    return random.choice(pool)


def npc_fallback_line(npc_key: str) -> str:
    roster = next((n for n in NPC_ROSTER if n["key"] == npc_key), None)
    if roster:
        return random.choice(roster["lines"])
    return "……"


async def npc_line(ai, npc: dict, scene: str) -> str:
    return await ai.generate_line(
        npc.get("persona") or npc["name"], scene, npc_fallback_line(npc.get("npc_key") or "")
    )


def maybe_challenge(store, gid: str, player: dict, probability: int = 12) -> Optional[dict]:
    """NPC 主动约战的判定。返回挑中的 NPC 档案或 None。"""
    if random.randint(1, 100) > probability:
        return None
    npc = random_npc(store, gid, near=total_power(player))
    if not npc:
        return None
    return npc
