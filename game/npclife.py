"""NPC 的日常：他们也有自己的小日子，会涨会跌。

玩家看到的是结果：某个 NPC 今天接了代言、明天被扒了黑料，
实力、星币、粉丝、人气都跟着动。
"""

from __future__ import annotations

import random
from typing import List, Optional

from .const import ATTR_KEYS, NPC_ROSTER
from .engine import total_power

# 每类事件：文案里 {npc} 会被替换成艺名；power/coins/fans 是效果区间（可负）
LIFE_EVENTS = [
    {
        "kind": "代言",
        "text": "{npc} 接了个饮料代言，片场一条过，品牌方当场追加预算。",
        "power": (8, 26),
        "coins": (60, 180),
        "fans": (800, 4200),
    },
    {
        "kind": "影视",
        "text": "{npc} 新剧路透被夸『把男主按在地上摩擦』，路人纷纷补剧。",
        "power": (6, 20),
        "coins": (40, 120),
        "fans": (1500, 6000),
    },
    {
        "kind": "音乐",
        "text": "{npc} 新歌上线，评论区第一条是『这歌能单曲循环到明年』。",
        "power": (6, 18),
        "coins": (30, 90),
        "fans": (1200, 5000),
    },
    {
        "kind": "时尚",
        "text": "{npc} 出席活动那套造型被三个时尚号同时评为本周最佳。",
        "power": (3, 12),
        "coins": (20, 60),
        "fans": (300, 1800),
    },
    {
        "kind": "应援",
        "text": "{npc} 生日应援大屏刷了三条街，路人问这是谁。",
        "power": (2, 8),
        "coins": (10, 40),
        "fans": (600, 3000),
    },
    {
        "kind": "综艺",
        "text": "{npc} 在综艺里社死了一次，那段播放量破千万。",
        "power": (4, 14),
        "coins": (20, 70),
        "fans": (900, 4000),
    },
    {
        "kind": "练习",
        "text": "{npc} 被拍到凌晨还在练习室，灯一直没关，路人缘涨了。",
        "power": (5, 15),
        "coins": (0, 10),
        "fans": (200, 1200),
    },
    {
        "kind": "翻红",
        "text": "{npc} 一个旧舞台被剪成短视频，突然翻红。",
        "power": (10, 28),
        "coins": (40, 150),
        "fans": (3000, 12000),
    },
    {
        "kind": "合作",
        "text": "{npc} 和顶流合唱了一首，被夸『压得住场』。",
        "power": (8, 22),
        "coins": (50, 160),
        "fans": (2000, 8000),
    },
    {
        "kind": "副业",
        "text": "{npc} 开了家小店，开业当天队伍排到街角。",
        "power": (2, 8),
        "coins": (100, 300),
        "fans": (200, 1500),
    },
    {
        "kind": "争议",
        "text": "{npc} 一句话被解读成内涵同行，词条挂了两小时。",
        "power": (-14, -3),
        "coins": (-60, -10),
        "fans": (-3000, -600),
    },
    {
        "kind": "私生",
        "text": "{npc} 被私生跟到楼下，工作室连夜发声明。",
        "power": (-8, -2),
        "coins": (-20, 0),
        "fans": (-800, 300),
    },
    {
        "kind": "黑料",
        "text": "{npc} 早年采访被翻出来，被说『人设崩了』。",
        "power": (-18, -5),
        "coins": (-120, -20),
        "fans": (-6000, -1200),
    },
    {
        "kind": "解约",
        "text": "{npc} 和公司谈续约没谈拢，工作停了两周。",
        "power": (-10, -2),
        "coins": (-80, -10),
        "fans": (-1500, -200),
    },
    {
        "kind": "破音",
        "text": "{npc} 音乐节破音切片流出，本人发博『我认』。",
        "power": (-6, -1),
        "coins": (-10, 10),
        "fans": (-1200, 400),
    },
    {
        "kind": "休息",
        "text": "{npc} 给自己放了一个月假，只在深夜点赞粉丝。",
        "power": (-3, 0),
        "coins": (-10, 10),
        "fans": (-200, 200),
    },
    {
        "kind": "恋爱",
        "text": "狗仔拍到 {npc} 和圈外人吃饭，粉丝分成两派。",
        "power": (-4, 6),
        "coins": (0, 40),
        "fans": (-2000, 3000),
    },
    {
        "kind": "翻车",
        "text": "{npc} 直播时说错话，被截图挂了一整天。",
        "power": (-12, -2),
        "coins": (-50, -5),
        "fans": (-4000, -800),
    },
]


def _delta(rng) -> int:
    lo, hi = rng
    return random.randint(int(lo), int(hi))


def _shift_attrs(npc: dict, delta: int) -> None:
    """把实力变化分摊到属性上：专长吃大头，另一项吃点边角。"""
    if not delta:
        return
    keys = [k for k in ATTR_KEYS if k in npc]
    if not keys:
        return
    top = max(keys, key=lambda k: int(npc.get(k) or 0))
    others = [k for k in keys if k != top] or [top]
    main = int(round(delta * 0.6))
    rest = delta - main
    plan = {top: main}
    if rest:
        side = random.choice(others)
        plan[side] = plan.get(side, 0) + rest
    for k, d in plan.items():
        npc[k] = max(0, int(npc.get(k) or 0) + int(d))


def _fmt_signed(n: int) -> str:
    return f"+{n:,}" if n >= 0 else f"-{abs(n):,}"


def run_daily_life(store, gid: str, chance: float = 0.55) -> List[dict]:
    """给 NPC 们过一天：部分人会摊上事，属性/星币/粉丝跟着变。

    返回本次产生的事件列表（dict: kind/text/npc/delta...）。
    """
    out: List[dict] = []
    npcs = store.npcs(gid)
    if not npcs:
        return out
    roster = {n["key"]: n for n in NPC_ROSTER}
    pool = list(LIFE_EVENTS)

    for npc in npcs:
        if random.random() > chance:
            continue
        picks = random.sample(pool, 1 if random.random() < 0.82 else 2)
        name = str(npc.get("name") or "某人")
        persona = roster.get(npc.get("npc_key"), {})
        cap = int(persona.get("cap") or 0)

        for ev in picks:
            delta = _delta(ev["power"])
            cur = total_power(npc)
            if cap and delta > 0 and cur + delta > cap:
                delta = max(0, cap - cur)

            coins = _delta(ev["coins"])
            fans = _delta(ev["fans"])

            _shift_attrs(npc, delta)
            npc["coins"] = max(0, int(npc.get("coins") or 0) + coins)
            npc["fans"] = max(0, int(npc.get("fans") or 0) + fans)
            # 人气跟着粉丝走：1000 粉 ≈ 1 点人气
            pop_shift = int(round(fans / 1000))
            if pop_shift:
                npc["renqi"] = max(0, min(500, int(npc.get("renqi") or 0) + pop_shift))
            store.save_star(npc)

            text = str(ev["text"]).format(npc=name)
            tail = f"（实力 {_fmt_signed(delta)}｜星币 {_fmt_signed(coins)}｜粉丝 {_fmt_signed(fans)}）"
            store.log_event(gid, str(ev["kind"]), text + tail)
            out.append(
                {
                    "kind": ev["kind"],
                    "npc": name,
                    "text": text,
                    "power": delta,
                    "coins": coins,
                    "fans": fans,
                }
            )
    return out


def recent_of(store, gid: str, name: str, limit: int = 3) -> List[str]:
    """某个艺人最近摊上的事，给艺人卡用。"""
    try:
        rows = store.recent_for(gid, name, limit)
    except Exception:
        return []
    return [f"{r.get('kind', '')}：{r.get('text', '')}" for r in rows]
