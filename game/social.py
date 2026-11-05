"""恋爱系统：好感度、送礼、表白、交往、结婚、离婚。"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from .const import GIFT_SHOP, MARRY_DIVORCE_PENALTY, NPC_BY_KEY
from .engine import now_iso, today

GIFTS = {k: (v["lo"], v["hi"], v["cap"]) for k, v in GIFT_SHOP.items()}


def resolve_target(store, gid: str, arg: str, self_uid: str) -> Optional[dict]:
    """按艺名找目标（真人优先，其次 NPC）。"""
    arg = (arg or "").strip()
    if not arg:
        return None
    hits = store.find_by_name(gid, arg)
    hits = [h for h in hits if h["qq_id"] != self_uid]
    return hits[0] if hits else None


def affection_bar(v: int) -> str:
    v = max(0, min(100, int(v)))
    filled = v // 10
    return "█" * filled + "░" * (10 - filled) + f" {v}/100"


def affection_word(v: int) -> str:
    if v >= 85:
        return "眼里只有你"
    if v >= 70:
        return "暧昧得藏不住"
    if v >= 50:
        return "有点在意你"
    if v >= 30:
        return "算熟人"
    if v >= 10:
        return "点头之交"
    return "还不熟"


def gift_menu() -> str:
    rows = []
    for name, g in GIFT_SHOP.items():
        if name == "求婚戒指":
            rows.append(f"  · {name}：{g['price']} 星币 — {g['desc']}")
            continue
        rows.append(
            f"  · {name}：{g['price']} 星币，好感 +{g['lo']}~{g['hi']}"
            f"（每天最多送 {g['cap']} 次）— {g['desc']}"
        )
    return "\n".join(rows)


def _gift_key(gift: str) -> str:
    return f"{today()}:{gift}"


def gift_allowed(rel: dict, gift: str) -> Tuple[bool, int]:
    cap = GIFT_SHOP[gift]["cap"]
    used = int((rel.get("gifts") or {}).get(_gift_key(gift), 0))
    return used < cap, used


def apply_gift(store, gid: str, x: str, y: str, gift: str) -> Tuple[int, dict]:
    """送礼：返回 (本次好感增量, 关系)。"""
    g = GIFT_SHOP[gift]
    lo, hi = int(g["lo"]), int(g["hi"])
    rel = store.get_relation(gid, x, y)
    used = rel.get("gifts") or {}
    key = _gift_key(gift)
    used[key] = int(used.get(key, 0)) + 1
    rel["gifts"] = used
    delta = random.randint(lo, hi) if hi else 0
    rel["affection"] = max(0, min(100, int(rel["affection"]) + delta))
    store.save_relation(rel)
    return delta, rel


def confess_threshold(target: dict, affection: int) -> int:
    """NPC 有固定门槛；真人玩家则看对方答不答应（门槛只是提示）。"""
    if target.get("is_npc"):
        roster = NPC_BY_KEY.get(target.get("npc_key") or "")
        base = int(roster["love"]) if roster else 60
        return base
    return 50


def make_couple(store, gid: str, x: str, y: str) -> dict:
    rel = store.get_relation(gid, x, y)
    rel["couple"] = 1
    rel["since"] = now_iso()
    rel["affection"] = max(int(rel["affection"]), 60)
    store.save_relation(rel)
    return rel


def marry(store, gid: str, x: str, y: str) -> dict:
    """结婚：比情侣更进一步，签到加成更高。"""
    rel = store.get_relation(gid, x, y)
    rel["couple"] = 1
    rel["married"] = 1
    rel["married_at"] = now_iso()
    if not rel.get("since"):
        rel["since"] = now_iso()
    rel["affection"] = max(int(rel["affection"]), 80)
    store.save_relation(rel)
    return rel


def divorce(store, gid: str, x: str, y: str) -> dict:
    rel = store.get_relation(gid, x, y)
    rel["couple"] = 0
    rel["married"] = 0
    rel["married_at"] = None
    rel["affection"] = max(0, int(rel["affection"]) - MARRY_DIVORCE_PENALTY)
    store.save_relation(rel)
    return rel


def breakup(store, gid: str, x: str, y: str) -> dict:
    rel = store.get_relation(gid, x, y)
    rel["couple"] = 0
    rel["married"] = 0
    rel["married_at"] = None
    rel["affection"] = max(0, int(rel["affection"]) - 30)
    store.save_relation(rel)
    return rel


def lover_line(name: str, affection: int) -> str:
    pool = [
        f"{name} 侧过头看了你一眼，没说话。",
        f"{name} 把耳机分了一半给你。",
        f"{name} 小声说：『今天也加油。』",
        f"{name} 假装不在意，但一直待在你旁边。",
    ]
    return random.choice(pool)


def couple_names(store, gid: str, uid: str) -> Optional[str]:
    pid = store.partner_of(gid, uid)
    if not pid:
        return None
    p = store.get_star(gid, pid)
    return p["name"] if p else None
