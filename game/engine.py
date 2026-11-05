"""星途核心逻辑（纯函数，不依赖 AstrBot，方便单测）。"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .const import (
    ACTIVITIES,
    ATTRS,
    ATTR_KEYS,
    DRAW_TYPES,
    POP_PK_CAP,
    POP_PK_DIVISOR,
    POP_TITLES,
    SIGN_BASE,
    SIGN_BIG,
    STREAK_REWARDS,
    TIERS,
)


# ---------------- 人气 ----------------
def pop_of(s: dict) -> int:
    return max(0, int(s.get("renqi", 0) or 0))


def pop_title(pop: int) -> str:
    name = POP_TITLES[0][1]
    for th, nm in POP_TITLES:
        if pop >= th:
            name = nm
    return name


def pop_bonus(pop: int) -> float:
    """人气给比拼带来的加成，0 ~ POP_PK_CAP。"""
    if pop <= 0:
        return 0.0
    return min(POP_PK_CAP, pop / (POP_PK_DIVISOR * 1.0))


def pop_bonus_text(pop: int) -> str:
    pct = int(round(pop_bonus(pop) * 100))
    return f"+{pct}%" if pct > 0 else ""


# ---------------- 基础 ----------------
def total_power(s: dict) -> int:
    """综合实力 = 四项之和。"""
    return sum(int(s[k]) for k in ATTR_KEYS)


def get_tier(total: int) -> Tuple[Tuple[int, str], Optional[Tuple[int, str]]]:
    """返回 (当前段位, 下一段位或 None)。"""
    cur = TIERS[0]
    nxt: Optional[Tuple[int, str]] = TIERS[1] if len(TIERS) > 1 else None
    for i, (th, name) in enumerate(TIERS):
        if total >= th:
            cur = (th, name)
            nxt = TIERS[i + 1] if i + 1 < len(TIERS) else None
    return cur, nxt


def tier_change_msg(before: int, after: int) -> str:
    cur_after, _ = get_tier(after)
    cur_before, _ = get_tier(before)
    if cur_after[1] != cur_before[1]:
        return f"\n🎉 段位晋升！你现在是「{cur_after[1]}」！"
    return ""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().date().isoformat()


def seconds_since(ts: Optional[str]) -> float:
    if not ts:
        return 1e9
    try:
        dt = datetime.fromisoformat(ts)
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return 1e9


def fmt_gain(v: int) -> str:
    return f"+{v}" if v >= 0 else str(v)


# ---------------- 抽签 ----------------
def do_draw(s: dict, draw_key: str = "全能") -> Tuple[Dict[str, int], int, int, str]:
    """返回 (各项增减, 抽前总分, 抽后总分, 实际触发的签型名)。"""
    spec = DRAW_TYPES.get(draw_key, DRAW_TYPES["全能"])
    mode = spec["mode"]
    lo, hi = spec["range"]

    if draw_key == "欧皇" and random.random() > spec.get("chance", 0.15):
        k = random.choice(ATTR_KEYS)
        results = {k: random.randint(0, 100)}
        rolled = "单项（未触发欧皇）"
    elif mode == "all":
        results = {k: random.randint(lo, hi) for k in ATTR_KEYS}
        rolled = "全能"
    elif mode == "single":
        k = random.choice(ATTR_KEYS)
        results = {k: random.randint(lo, hi)}
        rolled = "单项"
    elif mode == "penalty":
        k = random.choice(ATTR_KEYS)
        results = {k: -random.randint(lo, hi)}
        rolled = "反向（霉运）"
    else:
        results = {k: random.randint(lo, hi) for k in ATTR_KEYS}
        rolled = "全能"

    before = total_power(s)
    for k, v in results.items():
        s[k] = max(0, int(s[k]) + v)
    after = total_power(s)
    return results, before, after, rolled


# ---------------- 签到 ----------------
def do_sign(s: dict) -> Dict[str, object]:
    """四项各 +1~3，再随机一项额外 +3~10。"""
    gains: Dict[str, object] = {}
    for k in ATTR_KEYS:
        g = random.randint(*SIGN_BASE)
        s[k] = int(s[k]) + g
        gains[k] = g
    big = random.choice(ATTR_KEYS)
    extra = random.randint(*SIGN_BIG)
    s[big] = int(s[big]) + extra
    gains["big"] = (big, extra)
    return gains


# ---------------- 活动 ----------------
def do_activity(s: dict, act_key: str) -> Tuple[Dict[str, int], str]:
    attr_key, desc = ACTIVITIES[act_key]
    if attr_key == "total":
        gains: Dict[str, int] = {}
        for k in ATTR_KEYS:
            g = random.randint(15, 35)
            s[k] = int(s[k]) + g
            gains[k] = g
        return gains, desc
    stat = int(s[attr_key])
    g = random.randint(10, 30) + stat // 8
    s[attr_key] = stat + g
    return {attr_key: g}, desc


# ---------------- 比拼 ----------------
def _add(s: dict, cmp_key: Optional[str], amount: int) -> str:
    k = cmp_key if cmp_key else random.choice(ATTR_KEYS)
    s[k] = int(s[k]) + amount
    return k


def do_pk(s_a: dict, s_b: dict, attr_key: Optional[str] = None) -> dict:
    """比拼：双方各乘 0.9~1.1 运气系数。"""
    if attr_key in ATTRS:
        va, vb, label = int(s_a[attr_key]), int(s_b[attr_key]), ATTRS[attr_key]
        cmp_key: Optional[str] = attr_key
    else:
        va, vb, label = total_power(s_a), total_power(s_b), "综合实力"
        cmp_key = None

    la, lb = random.uniform(0.9, 1.1), random.uniform(0.9, 1.1)
    pa, pb = pop_bonus(pop_of(s_a)), pop_bonus(pop_of(s_b))
    sa, sb = va * la * (1 + pa), vb * lb * (1 + pb)

    if abs(sa - sb) < 1e-9:
        ka = _add(s_a, cmp_key, random.randint(2, 6))
        kb = _add(s_b, cmp_key, random.randint(2, 6))
        return {
            "winner": None,
            "label": label,
            "va": va,
            "vb": vb,
            "pa": pa,
            "pb": pb,
            "wattr": ka,
            "lattr": kb,
            "wgain": random.randint(2, 6),
            "lgain": random.randint(2, 6),
        }

    a_wins = sa > sb
    winner, loser = (s_a, s_b) if a_wins else (s_b, s_a)
    wgain = random.randint(8, 18)
    lgain = random.randint(1, 6)
    wattr = _add(winner, cmp_key, wgain)
    lattr = _add(loser, cmp_key, lgain)
    return {
        "winner": "a" if a_wins else "b",
        "label": label,
        "va": va,
        "vb": vb,
        "pa": pa,
        "pb": pb,
        "wattr": wattr,
        "lattr": lattr,
        "wgain": wgain,
        "lgain": lgain,
    }


# ---------------- 面板 ----------------
def fans_text(n) -> str:
    """粉丝数：一万以上按「万」，一亿以上按「亿」。"""
    try:
        n = int(n or 0)
    except Exception:
        n = 0
    if n >= 100000000:
        return f"{n / 100000000:.1f}亿"
    if n >= 10000:
        w = n / 10000
        return f"{w:.1f}万" if w < 100 else f"{int(round(w))}万"
    return str(n)


def star_card(s: dict) -> str:
    total = total_power(s)
    cur, nxt = get_tier(total)
    pop = pop_of(s)
    rows = [f"🎬 {s['name']}（{cur[1]}）"]
    rows.append("  " + " ｜ ".join(f"{ATTRS[k]} {int(s[k])}" for k in ATTR_KEYS))
    rows.append(f"  综合实力：{total}")
    who = str(s.get("gender") or "").strip()
    sty = str(s.get("style") or "").strip()
    fans = int(s.get("fans") or 0)
    if who or sty or fans:
        bits = []
        if who:
            bits.append(f"性别 {who}")
        if sty:
            bits.append(f"风格 {sty}")
        if fans:
            bits.append(f"粉丝 {fans_text(fans)}")
        rows.append("  " + " ｜ ".join(bits))
    if nxt:
        rows.append(f"  ➡️ 距「{nxt[1]}」还需 {nxt[0] - total} 点")
    else:
        rows.append("  ✨ 已登顶最高段位！")
    rows.append(f"  💰 星币：{int(s.get('coins') or 0)}")
    bonus = pop_bonus_text(pop)
    rows.append(
        f"  🔥 人气：{pop}（{pop_title(pop)}）" + (f"｜比拼加成 {bonus}" if bonus else "")
    )
    rows.append(
        f"  📊 战绩：{s.get('wins', 0)}胜 {s.get('losses', 0)}负 {s.get('draws', 0)}平"
    )
    streak = int(s.get("sign_streak") or 0)
    if streak > 1:
        rows.append(f"  📅 连续签到：{streak} 天")
    return "\n".join(rows)


# ---------------- 连签 ----------------
def next_streak_day(streak: int) -> int:
    """下一个还没拿到的连签档位（3/7/14/30），没有就返回 0。"""
    for d in sorted(STREAK_REWARDS):
        if streak < d:
            return d
    return 0
