"""星途 2.0 · 娱乐圈明星养成（AstrBot 版）

由 NoneBot2 版移植：命令层换成 AstrBot 的 filter，游戏逻辑原样保留在 game/ 里。
新增：AI 事件库、系统驱动 NPC、恋爱系统、4 人小群数值档。

群里用法（需要 @机器人 或者用 / 开头）：
    出道 / 属性 / 签到 / 抽签 / 活动 选秀 / 比拼 @某人 / 排行
    表白 名字 / 送礼 名字 礼物 / 答应 / 拒绝 / 分手 / 情侣 / 明星 / 事件
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

try:  # 组件导出位置在不同版本里略有差异
    from astrbot.api.message_components import At, Plain
except Exception:  # pragma: no cover
    from astrbot.core.message.components import At, Plain  # type: ignore

try:  # 框架自带的「会话级 AI 开关」，能直接停掉这个群的大模型回复
    from astrbot.core.star.session_llm_manager import SessionServiceManager
except Exception:  # pragma: no cover
    SessionServiceManager = None  # type: ignore

try:
    from astrbot.core.message.message_event_result import MessageEventResult
except Exception:  # pragma: no cover
    MessageEventResult = None  # type: ignore

from .game import card as gcard
from .game import npc as gnpc
from .game import social as gsocial
from .game.ai import AI, FALLBACK_QUESTIONS, fallback_events
from .game.const import (
    ACHIEVEMENTS,
    ACTIVITIES,
    ACTIVITY_COST,
    ASSISTANT_LEVELS,
    ASSISTANT_MAX,
    ATTRS,
    ATTR_KEYS,
    COIN_ACTIVITY,
    COIN_PK_WIN,
    COIN_POST,
    COIN_SIGN,
    COIN_START,
    DRAW_TYPES,
    DRAMA_BASE_FEE,
    DRAMA_SCORE_FEE,
    DRAMA_SETUPS,
    EVENT_KINDS,
    EVENT_POLARITY,
    FALLBACK_CHAT_REPLY,
    FALLBACK_ENDING,
    FALLBACK_POST_COMMENTS,
    FLAVOR_BAD,
    FLAVOR_FLAT,
    FLAVOR_GOOD,
    FOLLOWUP_BAD,
    FOLLOWUP_GOOD,
    FORTUNES,
    FAN_CHEER_COST,
    FAN_CHEER_POP,
    FAN_PER_POP,
    GIFT_SHOP,
    HOT_REWARD,
    HOT_TOP_N,
    INTERVIEW_FEE,
    INVITE_FALLBACK,
    INVITE_TTL_MIN,
    MARRY_AFFECTION,
    MARRY_DIVORCE_PENALTY,
    MONTHLY_ACT,
    MONTHLY_BASE,
    MONTHLY_SIGN,
    MONTHLY_WIN,
    NPC_ROSTER,
    POP_DECAY_KEEP,
    POP_DECAY_PERCENT,
    STREAK_REWARDS,
    TIERS,
)
from .game.engine import (
    do_activity,
    do_draw,
    do_pk,
    do_sign,
    fmt_gain,
    get_tier,
    next_streak_day,
    now_iso,
    pop_bonus,
    pop_bonus_text,
    pop_of,
    pop_title,
    seconds_since,
    star_card,
    tier_change_msg,
    today,
    total_power,
)
from .game.guard import SendGuard, norm_text
from .game.store import Store

PLUGIN_NAME = "astrbot_plugin_star_game"
HELP_IMG = Path(__file__).parent / "resources" / "help.png"


class DrawFilter(filter.CustomFilter):
    """『抽签』允许写成 「抽签」「欧皇 抽签」，所以不能用普通指令过滤器。"""

    def filter(self, event: AstrMessageEvent, cfg) -> bool:  # noqa: ARG002
        if not getattr(event, "is_at_or_wake_command", False):
            return False
        text = re.sub(r"\s+", "", event.message_str or "")
        return "抽签" in text


# ---------------- 「关掉 AI 回应」自然语言开关 ----------------
# 群友不会记固定指令，这里按词匹配，@机器人 或 / 开头即可
_AI_OFF_WORDS = (
    "关闭ai",
    "关掉ai",
    "关ai",
    "停止ai",
    "停ai",
    "ai关闭",
    "ai关掉",
    "ai闭嘴",
    "不需要ai",
    "关掉ai回应",
    "关闭ai回应",
    "停止回应",
    "关闭回应",
    "别说话",
    "闭嘴",
    "安静点",
)
_AI_ON_WORDS = (
    "开启ai",
    "打开ai",
    "开ai",
    "恢复ai",
    "ai开启",
    "ai打开",
    "ai说话",
    "恢复回应",
    "开启回应",
    "开始回应",
    "可以说话了",
)


class AIOffFilter(filter.CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg) -> bool:  # noqa: ARG002
        if not getattr(event, "is_at_or_wake_command", False):
            return False
        text = norm_text(event.message_str)
        return any(w in text for w in _AI_OFF_WORDS)


class AIOnFilter(filter.CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg) -> bool:  # noqa: ARG002
        if not getattr(event, "is_at_or_wake_command", False):
            return False
        text = norm_text(event.message_str)
        # 「开ai」是「打开ai」的子串，只需要判断正向词
        return any(w in text for w in _AI_ON_WORDS)


class StarGame(Star):
    def __init__(self, context: Context, config: Optional[dict] = None) -> None:
        super().__init__(context, config)
        self.cfg = config or {}
        self.store: Optional[Store] = None
        self.ai: Optional[AI] = None
        self.guard: Optional[SendGuard] = None
        self._tasks: set[asyncio.Task] = set()

    # ---------------- 生命周期 ----------------
    async def initialize(self) -> None:
        try:
            data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        except Exception:
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(data_dir / "star_game.db")
        self.store.init()
        self.data_dir = Path(data_dir)
        self.ai = AI(
            self.context,
            timeout=float(self._i("ai_timeout", 15)),
            enabled=self._b("event_ai_enabled", True),
            daily_budget=self._i("ai_daily_cap", 150),
        )
        self.guard = SendGuard(
            per_min=self._i("guard_per_min", 12),
            min_interval=self._i("guard_min_interval_ms", 1200) / 1000.0,
            max_len=self._i("guard_max_len", 1200),
            dedupe_sec=float(self._i("guard_dedupe_sec", 3)),
            words=tuple(
                w.strip()
                for w in self._s("guard_sensitive_words", "").split(",")
                if w.strip()
            ),
        )
        logger.info(f"[star_game] 就绪，数据库：{self.store.db_path}")

    async def terminate(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        self._tasks.clear()

    # ---------------- 配置读取 ----------------
    def _raw(self, key: str, default):
        try:
            val = self.cfg.get(key, default)  # type: ignore[union-attr]
        except Exception:
            return default
        return default if val is None else val

    def _b(self, key: str, default: bool) -> bool:
        v = self._raw(key, default)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on", "是")
        return bool(v)

    def _i(self, key: str, default: int) -> int:
        try:
            return int(self._raw(key, default))
        except (TypeError, ValueError):
            return default

    def _s(self, key: str, default: str) -> str:
        v = self._raw(key, default)
        return str(v)

    # ---------------- 通用 ----------------
    def _spawn(self, coro) -> None:
        try:
            task = asyncio.create_task(coro)
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _gate(self, event: AstrMessageEvent) -> bool:
        gid = event.get_group_id()
        if not gid:
            return False
        wl = self._s("group_whitelist", "").strip()
        if wl:
            ids = {x for x in re.split(r"[,，\s]+", wl) if x}
            if str(gid) not in ids:
                return False
        # 标记一下，发送守卫只处理本插件自己的消息
        event.set_extra("star_game", True)
        return True

    # ---------------- 群级 AI 回应开关 ----------------
    def _ai_off(self, gid: str) -> bool:
        store = self.store
        if store is None:
            return False
        return store.meta_get(gid, "ai_off") == "1"

    def _ai_set(self, gid: str, off: bool) -> None:
        if self.store is not None:
            self.store.meta_set(gid, "ai_off", "1" if off else "0")

    async def _ai_mirror(self, event: AstrMessageEvent, enabled: bool) -> bool:
        """把状态同步给框架的会话级开关，这样整条大模型链路都停。"""
        if SessionServiceManager is None:
            return False
        try:
            await SessionServiceManager.set_llm_status_for_session(
                event.unified_msg_origin, enabled
            )
            return True
        except Exception as e:
            logger.warning(f"[star_game] 同步会话 AI 状态失败：{e}")
            return False

    async def _ai_framework_state(self, event: AstrMessageEvent) -> Optional[bool]:
        if SessionServiceManager is None:
            return None
        try:
            return await SessionServiceManager.is_llm_enabled_for_session(
                event.unified_msg_origin
            )
        except Exception:
            return None

    def _can_switch(self, event: AstrMessageEvent) -> bool:
        if not self._b("ai_switch_admin_only", False):
            return True
        try:
            if event.is_admin():
                return True
        except Exception:
            pass
        return getattr(event, "role", "") == "admin"

    # ================= 群级 AI 开关 =================
    @filter.custom_filter(AIOffFilter, False)
    async def cmd_ai_off(self, event: AstrMessageEvent):
        """关掉本群的 AI 回应，只留游戏"""
        if not self._gate(event):
            return
        if not self._can_switch(event):
            yield event.plain_result("只有群管理能开关 AI 回应～")
            event.stop_event()
            return
        gid = str(event.get_group_id())
        self._ai_set(gid, True)
        mirrored = await self._ai_mirror(event, False)
        body = (
            "🔇 已关掉本群的 AI 回应\n"
            "大模型不再接话，这个群现在只能玩明星游戏\n"
            "（签到 / 抽签 / 接戏 / 采访 / 发博 / 比拼 / 排行 …都正常）\n"
            "要恢复聊天就发「开AI」"
        )
        if not mirrored:
            body += "\n（框架接口没接上，只在本插件内生效）"
        yield event.plain_result(body)
        event.stop_event()

    @filter.custom_filter(AIOnFilter, False)
    async def cmd_ai_on(self, event: AstrMessageEvent):
        """恢复本群的 AI 回应"""
        if not self._gate(event):
            return
        if not self._can_switch(event):
            yield event.plain_result("只有群管理能开关 AI 回应～")
            event.stop_event()
            return
        gid = str(event.get_group_id())
        self._ai_set(gid, False)
        mirrored = await self._ai_mirror(event, True)
        body = "🔊 已恢复本群的 AI 回应，聊天和游戏都能用。"
        if not mirrored:
            body += "\n（框架接口没接上，只在本插件内生效）"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("AI状态", alias={"ai状态", "AI开关", "ai开关"})
    async def cmd_ai_status(self, event: AstrMessageEvent):
        """看本群 AI 回应是开还是关"""
        if not self._gate(event):
            return
        gid = str(event.get_group_id())
        off = self._ai_off(gid)
        fw = await self._ai_framework_state(event)
        rows = [
            f"🎚 本群 AI 回应：{'🔇 关闭（只玩游戏）' if off else '🔊 开启（聊天+游戏）'}"
        ]
        if fw is not None:
            rows.append(f"   框架会话开关：{'开启' if fw else '已停用'}")
        rows.append("   发「关AI」或「开AI」切换")
        yield event.plain_result("\n".join(rows))
        event.stop_event()

    # ================= 发送守卫（防风控） =================
    @filter.on_decorating_result()
    async def guard_outgoing(self, event: AstrMessageEvent):
        """消息发出去之前最后过一遍：去链接、截断、去重、控频。"""
        if not event.get_extra("star_game"):
            return
        if event.get_extra("star_game_guard"):
            return
        event.set_extra("star_game_guard", True)
        if not self._b("guard_enabled", True) or self.guard is None:
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        raw = result.get_plain_text()
        if not raw or not raw.strip():
            return

        gid = str(event.get_group_id() or event.unified_msg_origin)
        text = self.guard.prepare(raw)
        if self.guard.is_duplicate(gid, text):
            event.clear_result()
            logger.info("[star_game] 同群重复内容，已拦下一次发送")
            return
        if text != raw and all(isinstance(c, Plain) for c in result.chain):
            result.chain = [Plain(text=text)]
        waited = await self.guard.pace(gid)
        if waited > 1.5:
            logger.info(f"[star_game] 控频排队 {waited:.1f}s（{gid}）")

    def _at_target(self, event: AstrMessageEvent) -> Optional[str]:
        self_id = str(event.get_self_id())
        try:
            comps = event.get_messages()
        except Exception:
            return None
        for comp in comps:
            if isinstance(comp, At):
                q = str(comp.qq)
                if q not in ("all", self_id):
                    return q
        return None

    def _arg(self, event: AstrMessageEvent, *names: str) -> str:
        text = re.sub(r"\s+", " ", (event.message_str or "").strip())
        for name in names:
            if text == name:
                return ""
            if text.startswith(name):
                return text[len(name) :].strip()
        return text

    def _pick_person(self, arg: str) -> str:
        """从参数里抠出人名：兼容「@昵称(12345)」「@昵称」「林晚星」。

        AstrBot 会把 @某人 渲染成 " @昵称(12345) " 塞进 message_str；
        用户手打的 @小红 则只有文本，两种都要能认。
        """
        s = re.sub(r"@[^\s(]+\(\d+\)", " ", arg or "")
        m = re.search(r"@([^\s()]+)", s)
        if m:
            return m.group(1).strip()
        words = [w for w in s.split() if w and w not in ATTRS.values()]
        return words[0].strip() if words else ""

    # ---------------- 每日维护 ----------------
    def _daily(self, gid: str) -> str:
        """同步部分：补 NPC、跨天成长；AI 热搜放后台。返回待播报的昨日/今日热搜。"""
        store = self.store
        assert store is not None
        if self._b("npc_enabled", True):
            gnpc.ensure_npcs(store, gid)

        pending = store.meta_get(gid, "news_text")
        if (
            pending
            and store.meta_get(gid, "news_day") == today()
            and store.meta_get(gid, "news_shown") != today()
        ):
            store.meta_set(gid, "news_shown", today())
            return pending

        if store.meta_get(gid, "npc_tick_day") != today():
            store.meta_set(gid, "npc_tick_day", today())
            self._spawn(self._daily_bg(gid))
        return ""

    def _decay_pop(self, gid: str) -> None:
        """跨天掉人气：不营业就会被忘掉。"""
        store = self.store
        if store is None:
            return
        for s in store.players(gid):
            pop = pop_of(s)
            if pop <= POP_DECAY_KEEP:
                continue
            drop = max(1, pop * POP_DECAY_PERCENT // 100)
            s["renqi"] = max(0, pop - drop)
            store.save_star(s)

    async def _daily_bg(self, gid: str) -> None:
        store, ai = self.store, self.ai
        if store is None or ai is None:
            return
        try:
            self._decay_pop(gid)
            news = await gnpc.daily_tick(
                store, ai, gid, news_enabled=self._b("npc_news_enabled", True)
            )
            if news:
                store.meta_set(gid, "news_text", news)
                store.meta_set(gid, "news_day", today())
                store.meta_set(gid, "news_shown", "")
        except Exception as e:  # 后台任务绝不冒泡
            logger.warning(f"[star_game] 每日 NPC 维护失败：{e}")

    def _player(self, event: AstrMessageEvent) -> Optional[tuple]:
        """取（必要时自动创建）当前玩家的档案。"""
        store = self.store
        if store is None:
            return None
        gid, uid = str(event.get_group_id()), str(event.get_sender_id())
        name = ""
        try:
            name = event.get_sender_name() or ""
        except Exception:
            name = ""
        star, created = store.ensure_star(gid, uid, name)
        return gid, uid, star, created

    # ---------------- 事件库 ----------------
    async def _fill_pool(self, gid: str) -> None:
        store, ai = self.store, self.ai
        if store is None or ai is None:
            return
        try:
            if not self._b("event_ai_enabled", True):
                store.add_events(gid, fallback_events(4))
                return
            used = [e["text"][:14] for e in store.events_today(gid, 8)]
            events = await ai.generate_events(self._i("event_pool_target", 4), used)
            if not events:
                events = fallback_events(4)
            store.add_events(gid, events)
            logger.info(f"[star_game] 事件池补充 {len(events)} 条（{gid}）")
        except Exception as e:
            logger.warning(f"[star_game] 补充事件池失败：{e}")

    # ---------------- AI 点评（对当事人说一句） ----------------
    async def _bot_persona(self, umo: str = "") -> str:
        """取这只机器人平时的人格卡文本（带 5 分钟缓存），拿不到就空串。"""
        if not self._b("flavor_use_persona", True):
            return ""
        now = time.time()
        cached = getattr(self, "_persona_cache", None)
        if cached and now - cached[0] < 300:
            return cached[1]
        txt = ""
        pm = getattr(self.context, "persona_manager", None) if self.context is not None else None
        if pm is not None:
            try:
                p = await pm.get_default_persona_v3(umo or None)
                if isinstance(p, dict):
                    txt = str(p.get("prompt") or "")
            except Exception as e:
                logger.debug(f"[star_game] 读取人格失败：{e}")
                txt = ""
        self._persona_cache = (now, txt)
        return txt

    async def _flavor(
        self,
        star: dict,
        action: str,
        outcome: str,
        delta: int = 0,
        umo: str = "",
    ) -> str:
        """按这次结果，有概率让 AI 对当事人说一句；返回 '\\n💬 xxx' 或空串。"""
        if not self._b("flavor_enabled", True):
            return ""
        prob = max(0, min(100, self._i("flavor_probability", 45)))
        if prob <= 0 or random.randint(1, 100) > prob:
            return ""
        if delta >= 6:
            pool = FLAVOR_GOOD
        elif delta <= -3:
            pool = FLAVOR_BAD
        else:
            pool = FLAVOR_FLAT
        fallback = random.choice(pool)
        line = fallback
        if self.ai is not None:
            try:
                line = await self.ai.flavor_line(
                    str(star.get("name") or "这位"),
                    action,
                    outcome,
                    fallback,
                    self._s("flavor_persona", ""),
                    await self._bot_persona(umo),
                )
            except Exception as e:
                logger.warning(f"[star_game] 点评生成失败：{e}")
                line = fallback
        return f"\n💬 {line}" if line else ""

    # ---------------- 成就 ----------------
    def _ach_hits(self, gid: str, star: dict) -> List[str]:
        """按当前状态算出「现在应该拥有」的成就，全量判定，不记中间状态。"""
        store = self.store
        hits = ["debut"]
        streak = int(star.get("sign_streak") or 0)
        if streak >= 1 or star.get("last_sign"):
            hits.append("first_sign")
        if streak >= 7:
            hits.append("streak7")
        pop = pop_of(star)
        if pop >= 100:
            hits.append("pop100")
        if pop >= 500:
            hits.append("pop500")
        total = total_power(star)
        if total >= 1800:
            hits.append("diamond")
        if total >= 3200:
            hits.append("king")
        if int(star.get("wins") or 0) >= 1:
            hits.append("first_win")
        if all(int(star[k]) >= 300 for k in ATTR_KEYS):
            hits.append("allround")
        if store is not None and store.partner_of(gid, star["qq_id"]):
            hits.append("couple")
        if store is not None and store.married_of(gid, star["qq_id"]):
            hits.append("married")
        if self._coins(star) >= 1000:
            hits.append("rich")
        return hits

    def _check_ach(self, gid: str, star: dict) -> List[str]:
        """解锁新达成的成就，返回要播报的行。"""
        store = self.store
        if store is None or star.get("is_npc"):
            return []
        out: List[str] = []
        for key in self._ach_hits(gid, star):
            if not store.unlock(gid, star["qq_id"], key):
                continue
            icon, name, desc = ACHIEVEMENTS.get(key, ("🏅", key, ""))
            out.append(f"🏅 成就解锁 {icon}「{name}」— {desc}")
        return out

    @staticmethod
    def _event_effects(kind: str, effects: dict) -> dict:
        """把一条事件的数值统一成同一方向：好事只加，坏事只减。"""
        pol = int(EVENT_POLARITY.get(str(kind or ""), 0))
        out = {}
        for k, v in (effects or {}).items():
            try:
                n = int(v)
            except (TypeError, ValueError):
                continue
            if pol > 0:
                n = abs(n)
            elif pol < 0:
                n = -abs(n)
            if n:
                out[str(k)] = n
        return out

    async def _maybe_event(self, gid: str, actor: dict, targets: List[dict]) -> str:
        """按概率触发一条事件，返回要追加的文本（可能为空）。"""
        store = self.store
        if store is None:
            return ""
        prob = self._i("event_probability", 35)
        cap = self._i("event_daily_cap", 8)
        # 人气越高越容易被盯上：最多再加 20 个百分点
        prob += min(20, pop_of(actor) // 25)
        if prob <= 0 or random.randint(1, 100) > prob:
            return ""
        if store.events_today_count(gid) >= cap:
            return ""

        ev = store.pop_event(gid)
        if not ev:
            ev = random.choice(fallback_events(1))

        # 有些事件发生在系统 NPC 身上：加减只算那个 NPC，不碰玩家
        npcs = store.npcs(gid) if self._b("npc_enabled", True) else []
        npc_prob = max(0, min(100, self._i("npc_event_probability", 30)))
        npc_target = (
            random.choice(npcs)
            if npcs and npc_prob > 0 and random.randint(1, 100) <= npc_prob
            else None
        )
        applies_all = ev.get("target") == "all"
        if npc_target is not None:
            who_name = str(npc_target.get("name") or "某位艺人")
        else:
            who_name = "群里所有人" if applies_all else str(actor.get("name") or "你")
        ev_title = str(ev.get("title") or "").replace("{name}", who_name)
        ev_text = str(ev.get("text") or "").replace("{name}", who_name)
        store.log_event(gid, ev["kind"], f"《{ev_title}》{ev_text}")

        if npc_target is not None:
            applies = [npc_target]
        elif applies_all:
            applies = [t for t in targets if t]
        else:
            applies = [actor]
        who = []
        eff_rows = []
        effs = self._event_effects(ev.get("kind"), ev.get("effects"))
        for s in applies:
            is_npc = bool(s.get("is_npc"))
            for k, v in effs.items():
                if k == "renqi":
                    cur = pop_of(s)
                    if is_npc:
                        s["renqi"] = max(0, min(500, cur + int(v)))
                    else:
                        s["renqi"] = max(0, cur + int(v))
                    eff_rows.append(f"人气{fmt_gain(int(v))}")
                elif k in ATTR_KEYS:
                    s[k] = max(0, int(s[k]) + int(v))
                    eff_rows.append(f"{ATTRS[k]}{fmt_gain(int(v))}")
            store.save_star(s)
            who.append(s["name"] + ("·NPC" if is_npc else ""))

        eff = "、".join(dict.fromkeys(eff_rows)) or "人气波动（无属性变化）"
        head_line = "🎬 圈内动静" if npc_target is not None else "🎬 突发事件"
        lines = [
            f"{head_line}｜{ev['kind']}",
            f"《{ev_title}》",
            ev_text,
            f"  → {eff}（{'、'.join(who)}）",
        ]
        if store.pool_size(gid) < self._i("event_pool_target", 4):
            self._spawn(self._fill_pool(gid))
        return "\n".join(lines)

    # ================= NPC 主动搭话 =================
    async def _maybe_talk(self, gid: str, star: dict) -> Optional[dict]:
        """有概率让一个 NPC 突然找玩家说话（回复里带 @），15 分钟内可回。"""
        store, ai = self.store, self.ai
        if store is None or ai is None or not self._b("npc_talk_enabled", True):
            return None
        if star.get("is_npc"):
            return None
        uid = str(star["qq_id"])
        if store.get_story(gid, uid, "talk"):
            return None
        prob = self._i("npc_talk_probability", 18)
        if prob <= 0 or random.randint(1, 100) > prob:
            return None
        gap = max(1, self._i("npc_talk_cooldown_min", 30)) * 60
        if seconds_since(store.meta_get(gid, f"talk:{uid}")) < gap:
            return None

        npc = gnpc.random_npc(store, gid, exclude=uid, near=total_power(star))
        if not npc:
            return None
        tier = get_tier(total_power(star))[0][1]
        data = await ai.npc_talk_open(
            npc, star["name"], tier, total_power(star)
        )
        store.save_story(
            gid,
            uid,
            "talk",
            0,
            {
                "npc_uid": npc["qq_id"],
                "npc_name": npc["name"],
                "line": data["line"],
                "options": data["options"],
            },
        )
        store.meta_set(gid, f"talk:{uid}", now_iso())

        rows = [f"🎙 {npc['name']}：{data['line']}", ""]
        for i, opt in enumerate(data["options"][:3]):
            rows.append(f"  {chr(65 + i)}. {opt}")
        rows.append("")
        rows.append("（回「回应 A」，或者「回应 你想说的话」，15 分钟内有效）")
        return {
            "npc_uid": npc["qq_id"],
            "npc_name": npc["name"],
            "text": "\n".join(rows),
        }

    async def _finish(self, event: AstrMessageEvent, body: str, gid: str, star: dict):
        """统一出口：有概率让 NPC 突然搭话，用消息链 @ 一下当事人。"""
        talk = await self._maybe_talk(gid, star)
        if not talk:
            invite = await self._maybe_invite(gid, star)
            if invite:
                body = body + invite
            return event.plain_result(body)
        text = body + "\n\n" + talk["text"]
        try:
            mer = event.make_result()
            mer.message(body + "\n\n")
            mer.at(star["name"], star["qq_id"])
            mer.message(" " + talk["text"])
            return mer
        except Exception:
            return event.plain_result(text)

    @filter.command("回应", alias={"回复他", "接话"})
    async def cmd_reply(self, event: AstrMessageEvent):
        """回应 NPC 刚才的搭话：选 A/B/C，或者直接说你想说的话"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store, ai = self.store, self.ai
        assert store is not None
        st = self._load_story(gid, uid, "talk")
        if st and st.get("expired"):
            yield event.plain_result("那句搭话已经凉了，下次撞上了再聊。")
            event.stop_event()
            return
        if not st or ai is None:
            yield event.plain_result("现在没人跟你搭话。")
            event.stop_event()
            return

        data = st.get("data") or {}
        npc_name = str(data.get("npc_name") or "对方")
        npc_uid = str(data.get("npc_uid") or "")
        line = str(data.get("line") or "")
        options = [str(x) for x in (data.get("options") or [])]
        npc = store.get_star(gid, npc_uid) if npc_uid else None
        if not npc:
            store.del_story(gid, uid, "talk")
            yield event.plain_result("对方已经走了。")
            event.stop_event()
            return

        raw = self._arg(event, "回应", "回复他", "接话").strip()
        if not raw:
            rows = [f"🎙 {npc_name}：{line}", ""]
            for i, opt in enumerate(options[:3]):
                rows.append(f"  {chr(65 + i)}. {opt}")
            rows.append("")
            rows.append("（回「回应 A」，或者「回应 你想说的话」）")
            yield event.plain_result("\n".join(rows))
            event.stop_event()
            return

        choice, free_text = "", raw
        key = raw.upper()
        if key in ("A", "B", "C", "1", "2", "3"):
            idx = "ABC".index(key) if key in "ABC" else int(key) - 1
            if 0 <= idx < len(options):
                choice, free_text = options[idx], ""

        judged = await ai.npc_talk_judge(npc, me["name"], line, choice, free_text)
        favor = int(judged.get("favor") or 0)
        renqi = int(judged.get("renqi") or 0)
        rel = store.add_affection(gid, uid, npc_uid, favor)

        effs = {"renqi": renqi}
        for k, v in (judged.get("effects") or {}).items():
            effs[k] = int(v)
        eff_text = self._apply_effects(store, me, effs)
        store.save_star(me)

        said = f"「{choice}」" if choice else f"「{free_text[:40]}」"
        store.log_event(
            gid,
            "搭话",
            f"{npc_name} 找 {me['name']} 说话，回应{said}，好感{favor:+d}",
        )
        store.del_story(gid, uid, "talk")

        # 记下结果，第二天 _daily_extra 兑现「后续」
        store.save_story(
            gid,
            uid,
            "followup",
            0,
            {
                "npc_uid": npc_uid,
                "npc_name": npc_name,
                "good": favor >= 4,
                "day": date.today().isoformat(),
            },
        )

        rows = [
            f"💬 你（对{npc_name}）：{said}",
            "",
            f"🎙 {npc_name}：{judged.get('reply')}",
            "",
        ]
        tail = [f"氛围 {judged.get('mood') or '微妙'}"]
        tail.append(f"好感 {favor:+d} → {rel['affection']}")
        if eff_text:
            tail.append(eff_text)
        rows.append("（" + "｜".join(tail) + "）")
        head = self._daily(gid)
        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    # ================= 星币 / 事务所 / 粉丝团 =================
    def _coins(self, star: dict) -> int:
        return max(0, int(star.get("coins", 0) or 0))

    def _gain(self, star: dict, n: int) -> int:
        """加减星币并立刻落库；返回实际变化量。"""
        star["coins"] = max(0, self._coins(star) + int(n))
        if self.store is not None:
            self.store.save_star(star)
        return int(n)

    def _assistant_lv(self, gid: str, uid: str) -> int:
        store = self.store
        if store is None:
            return 0
        raw = store.meta_get(gid, f"assist:{uid}", "0") or "0"
        try:
            return max(0, min(ASSISTANT_MAX, int(raw)))
        except ValueError:
            return 0

    @staticmethod
    def _month_key(offset: int = 0) -> str:
        d = date.today()
        y, m = d.year, d.month + offset
        while m <= 0:
            y, m = y - 1, m + 12
        return f"{y}-{m:02d}"

    async def _daily_extra(self, gid: str, star: dict) -> str:
        """每日一进来就结算：搭话后续、助理通告、月初考勤结算。"""
        store = self.store
        if store is None:
            return ""
        uid = str(star["qq_id"])
        today_s = date.today().isoformat()
        rows: List[str] = []

        fu = store.get_story(gid, uid, "followup")
        if fu:
            data = fu.get("data") or {}
            if str(data.get("day") or "") < today_s:
                npc_name = str(data.get("npc_name") or "对方")
                if bool(data.get("good")):
                    line = random.choice(FOLLOWUP_GOOD).format(npc=npc_name)
                    bonus = random.randint(15, 30)
                    k = random.choice(ATTR_KEYS)
                    star[k] = int(star[k]) + 3
                    star["coins"] = self._coins(star) + bonus
                    store.save_star(star)
                    line += f"\n  → 星币+{bonus}、{ATTRS[k]}+3"
                else:
                    line = random.choice(FOLLOWUP_BAD).format(npc=npc_name)
                store.del_story(gid, uid, "followup")
                rows.append("📮 " + line)

        lv = self._assistant_lv(gid, uid)
        if lv:
            pay_key = f"assist_pay:{uid}:{today_s}"
            if not store.meta_get(gid, pay_key):
                store.meta_set(gid, pay_key, "1")
                pay = ASSISTANT_LEVELS[lv][1]
                k = random.choice(ATTR_KEYS)
                star[k] = int(star[k]) + lv
                star["renqi"] = int(star.get("renqi", 0)) + 1
                star["coins"] = self._coins(star) + pay
                store.save_star(star)
                rows.append(
                    f"🏢 助理替你接了个通告：星币+{pay}、{ATTRS[k]}+{lv}、人气+1"
                )

        if date.today().day == 1:
            mk = self._month_key(-1)
            settle_key = f"settle:{uid}:{mk}"
            if not store.meta_get(gid, settle_key):
                cs = store.counters_of(gid, uid, mk)
                n_sign = cs.get("sign", 0)
                n_act = sum(v for k, v in cs.items() if k.startswith("act:"))
                n_win = cs.get("win", 0)
                if n_sign or n_act or n_win:
                    store.meta_set(gid, settle_key, "1")
                    bonus = (
                        MONTHLY_BASE
                        + n_sign * MONTHLY_SIGN
                        + n_act * MONTHLY_ACT
                        + n_win * MONTHLY_WIN
                    )
                    pop = min(10, n_sign // 5)
                    star["coins"] = self._coins(star) + bonus
                    star["renqi"] = int(star.get("renqi", 0)) + pop
                    store.save_star(star)
                    rows.append(
                        f"🧾 上个月（{mk}）结算：签到 {n_sign} 天、活动 {n_act} 次、胜 {n_win} 场\n"
                        f"  → 年终奖 星币+{bonus}、人气+{pop}"
                    )
        return "\n".join(rows)

    @filter.command("事务所", alias={"经纪公司", "公司", "我的事务所"})
    async def cmd_agency(self, event: AstrMessageEvent):
        """看星币和助理，升级助理后每天自动接一个通告"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        lv = self._assistant_lv(gid, uid)
        rows = [f"🏢 {star['name']} 的事务所", f"  星币：{self._coins(star)}"]
        if lv:
            rows.append(f"  助理 Lv.{lv}：{ASSISTANT_LEVELS[lv][2]}")
            rows.append(f"  每天自动进账 {ASSISTANT_LEVELS[lv][1]} 星币（今天签到后到账）")
        else:
            rows.append("  还没请助理，一切自己跑")
        if lv < ASSISTANT_MAX:
            nxt = lv + 1
            cost = ASSISTANT_LEVELS[nxt][0]
            rows.append(f"  下一级 Lv.{nxt}：{cost} 星币 — {ASSISTANT_LEVELS[nxt][2]}")
            rows.append("  发「雇助理」就升级")
        else:
            rows.append("  助理已经满级了")
        rows.append("")
        rows.append("攒星币：签到 +8、活动 +12、发博 +6、比拼胜 +10")
        yield event.plain_result("\n".join(rows))
        event.stop_event()

    @filter.command("雇助理", alias={"请助理", "升级助理"})
    async def cmd_hire(self, event: AstrMessageEvent):
        """花星币升级助理"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        lv = self._assistant_lv(gid, uid)
        if lv >= ASSISTANT_MAX:
            yield event.plain_result("助理已经满级了，再多一个能干的也是抢你资源。")
            event.stop_event()
            return
        nxt = lv + 1
        cost, pay, desc = ASSISTANT_LEVELS[nxt]
        if self._coins(star) < cost:
            yield event.plain_result(
                f"请 Lv.{nxt} 要 {cost} 星币，你现在只有 {self._coins(star)}。\n"
                "多签到、参加活动、发博攒一攒。"
            )
            event.stop_event()
            return
        star["coins"] = self._coins(star) - cost
        self.store.meta_set(gid, f"assist:{uid}", str(nxt))  # type: ignore[union-attr]
        self.store.save_star(star)  # type: ignore[union-attr]
        yield event.plain_result(
            f"🤝 助理升到 Lv.{nxt}（花了 {cost} 星币）\n"
            f"  {desc}\n"
            f"  从明天起每天签到，她会自动帮你进账 {pay} 星币。"
        )
        event.stop_event()

    @filter.command("粉丝团", alias={"粉丝", "后援会"})
    async def cmd_fans(self, event: AstrMessageEvent):
        """看粉丝团规模，花星币应援冲人气"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        fans = pop_of(star) * FAN_PER_POP + int(star.get("sign_streak", 0)) * 20
        rows = [
            f"🧣 {star['name']} 的粉丝团",
            f"  粉丝：{fans:,} 人（人气 {pop_of(star)} × {FAN_PER_POP} ＋ 连签 {int(star.get('sign_streak', 0))} × 20）",
            f"  星币：{self._coins(star)}",
            "",
            f"发「应援」花 {FAN_CHEER_COST} 星币冲一次榜，每天一次，人气 +{FAN_CHEER_POP[0]}~{FAN_CHEER_POP[1]}。",
        ]
        yield event.plain_result("\n".join(rows))
        event.stop_event()

    @filter.command("应援", alias={"打投", "冲榜"})
    async def cmd_cheer(self, event: AstrMessageEvent):
        """花星币给粉丝团冲榜，涨人气"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        key = f"cheer:{uid}:{date.today().isoformat()}"
        if store.meta_get(gid, key):
            yield event.plain_result("今天已经应援过了，粉丝也要休息。")
            event.stop_event()
            return
        if self._coins(star) < FAN_CHEER_COST:
            yield event.plain_result(
                f"应援要 {FAN_CHEER_COST} 星币，你现在只有 {self._coins(star)}。"
            )
            event.stop_event()
            return
        gain = random.randint(*FAN_CHEER_POP)
        star["coins"] = self._coins(star) - FAN_CHEER_COST
        star["renqi"] = pop_of(star) + gain
        store.save_star(star)
        store.meta_set(gid, key, "1")
        yield event.plain_result(
            f"📣 粉丝团连夜打投，给你冲上了榜尾。\n"
            f"  → 人气+{gain}（现在 {pop_of(star)}）｜星币-{FAN_CHEER_COST}"
        )
        event.stop_event()

    @filter.command("热搜", alias={"热搜榜", "榜单"})
    async def cmd_hot(self, event: AstrMessageEvent):
        """看本群实时热搜 Top5，上榜前 3 每小时有额外人气"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        everyone = [s for s in store.all_stars(gid) if pop_of(s) > 0]
        everyone.sort(key=lambda s: pop_of(s), reverse=True)
        top = everyone[:HOT_TOP_N]
        rows = [f"🔥 本群热搜 Top{HOT_TOP_N}（按人气）"]
        rank_of_me = 0
        for i, s in enumerate(top, 1):
            tag = "·NPC" if s.get("is_npc") else ""
            mark = " ←你" if str(s["qq_id"]) == uid else ""
            if mark:
                rank_of_me = i
            rows.append(f"  {i}. {s['name']}{tag}　人气 {pop_of(s)}{mark}")
        if not rank_of_me:
            rows.append(f"  你没进前 {HOT_TOP_N}，现在人气 {pop_of(star)}。")
        reward = HOT_REWARD.get(rank_of_me, 0)
        if reward:
            hour_key = f"hot:{uid}:{date.today().isoformat()}:{time.strftime('%H')}"
            if not store.meta_get(gid, hour_key):
                store.meta_set(gid, hour_key, "1")
                star["renqi"] = pop_of(star) + reward
                store.save_star(star)
                rows.append(f"  → 上了榜，路人涌进来：人气+{reward}")
        yield event.plain_result("\n".join(rows))
        event.stop_event()

    @filter.command("考勤", alias={"月报数据", "本月考勤"})
    async def cmd_attendance(self, event: AstrMessageEvent):
        """看本月的签到/活动/胜场，月初会按这个发年终奖"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        mk = self._month_key(0)
        cs = store.counters_of(gid, uid, mk)
        n_sign = cs.get("sign", 0)
        n_act = sum(v for k, v in cs.items() if k.startswith("act:"))
        n_win = cs.get("win", 0)
        rows = [
            f"🗓 {star['name']} 的 {mk} 考勤",
            f"  签到 {n_sign} 天｜活动 {n_act} 次｜比拼胜 {n_win} 场",
            f"  现在结算大约能拿 {MONTHLY_BASE + n_sign * MONTHLY_SIGN + n_act * MONTHLY_ACT + n_win * MONTHLY_WIN} 星币",
            "  每月 1 号第一次进游戏自动发年终奖。",
        ]
        yield event.plain_result("\n".join(rows))
        event.stop_event()

    # ================= NPC 邀约 =================
    async def _maybe_invite(self, gid: str, star: dict) -> str:
        """有概率让一个 NPC 主动发邀约，带倒计时。"""
        store, ai = self.store, self.ai
        if store is None or ai is None or not self._b("invite_enabled", True):
            return ""
        uid = str(star["qq_id"])
        if star.get("is_npc"):
            return ""
        if store.get_story(gid, uid, "invite"):
            return ""
        prob = self._i("invite_probability", 14)
        if prob <= 0 or random.randint(1, 100) > prob:
            return ""
        npc = gnpc.random_npc(store, gid, exclude=uid, near=total_power(star))
        if not npc:
            return ""
        scene = "你主动给一个后辈/同行发一个通告或约戏的邀请，一句话，不超过 30 字，带点你自己的语气"
        text = await gnpc.npc_line(ai, npc, scene)
        if not text:
            text = random.choice(INVITE_FALLBACK).format(npc=npc["name"])
        store.save_story(
            gid, uid, "invite", 0, {"npc_uid": npc["qq_id"], "npc_name": npc["name"], "text": text}
        )
        return (
            f"\n\n📩 {npc['name']} 发来一条邀约：{text}\n"
            f"  （{INVITE_TTL_MIN} 分钟内回「接邀」或「推辞」）"
        )

    @filter.command("接邀", alias={"接受邀约", "接活"})
    async def cmd_take_invite(self, event: AstrMessageEvent):
        """接下 NPC 的邀约"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        st = self._load_story(gid, uid, "invite")
        if st and st.get("expired"):
            yield event.plain_result("这条邀约已经过期了，对方等不了你。")
            event.stop_event()
            return
        if not st:
            yield event.plain_result("现在没有待接的邀约。")
            event.stop_event()
            return
        data = st.get("data") or {}
        npc_name = str(data.get("npc_name") or "对方")
        npc_uid = str(data.get("npc_uid") or "")
        coins = random.randint(25, 45)
        k = random.choice(ATTR_KEYS)
        g = random.randint(4, 7)
        star[k] = int(star[k]) + g
        star["coins"] = self._coins(star) + coins
        star["renqi"] = pop_of(star) + 2
        store.save_star(star)
        rel = store.add_affection(gid, uid, npc_uid, 4) if npc_uid else {"affection": 0}
        store.del_story(gid, uid, "invite")
        store.log_event(gid, "邀约", f"{npc_name} 邀 {star['name']} 合作，接下后星币+{coins}")
        yield event.plain_result(
            f"✅ 你接下了 {npc_name} 的邀约。\n"
            f"  → 星币+{coins}（{self._coins(star)}）、{ATTRS[k]}+{g}、人气+2、好感+4（现在 {rel.get('affection', 0)}）"
        )
        event.stop_event()

    @filter.command("推辞", alias={"拒绝邀约", "不去"})
    async def cmd_decline_invite(self, event: AstrMessageEvent):
        """推掉 NPC 的邀约"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        st = self._load_story(gid, uid, "invite")
        if st and st.get("expired"):
            yield event.plain_result("这条邀约已经过期了。")
            event.stop_event()
            return
        if not st:
            yield event.plain_result("现在没有待接的邀约。")
            event.stop_event()
            return
        data = st.get("data") or {}
        npc_name = str(data.get("npc_name") or "对方")
        npc_uid = str(data.get("npc_uid") or "")
        if npc_uid:
            store.add_affection(gid, uid, npc_uid, -4)
        store.del_story(gid, uid, "invite")
        yield event.plain_result(f"🙅 你推掉了 {npc_name} 的邀约，好感-4。")
        event.stop_event()

    # ================= 指令 =================
    @filter.command("出道", alias={"注册", "入职", "加入星途"})
    async def cmd_debut(self, event: AstrMessageEvent):
        """出道：加入星途"""
        if not self._gate(event):
            return
        gid, uid, star, created = self._player(event)  # type: ignore[misc]
        head = self._daily(gid)
        if not created:
            msg = f"你已经在娱乐圈了，艺名「{star['name']}」～用「属性」看看自己。"
        else:
            msg = (
                f"🌟 欢迎出道！你的艺名是「{star['name']}」。\n"
                "初始四项各 10 点。每天「签到」、@我「抽签」、参加「活动」来提升实力，\n"
                "也可以「比拼」真人或「明星」里的 NPC，还能去「表白」某个人。\n"
                "发送「帮助」查看全部玩法。"
            )
        if created:
            msg += await self._flavor(
                star, "正式出道", "新人第一天进圈", 6, umo=event.unified_msg_origin
            )
        if head:
            msg = f"{head}\n\n{msg}"
        yield event.plain_result(msg)
        event.stop_event()

    def _status_image(
        self, gid: str, uid: str, star: dict, info: dict
    ) -> Optional[str]:
        """把面板画成图；环境不支持、或渲染出错就返回 None，让调用方回退成文字。"""
        if not self._b("status_image", True) or not gcard.available():
            return None
        try:
            total = total_power(star)
            cur, nxt = get_tier(total)
            cur_th = int(cur[0])
            if nxt:
                span = max(1, int(nxt[0]) - cur_th)
                pct = max(0.0, (total - cur_th) / span)
                next_text = f"距「{nxt[1]}」还差 {max(0, int(nxt[0]) - total)} 点"
            else:
                pct = 1.0
                next_text = "已在最高段位"
            attrs = [(ATTRS[k], int(star.get(k, 0) or 0)) for k in ATTR_KEYS]
            scale = max(300, int((max(v for _, v in attrs) + 99) // 100 * 100))
            renqi = pop_of(star)
            data = {
                "name": star["name"],
                "tier": cur[1],
                "total": total,
                "next_text": next_text,
                "pct": pct,
                "attrs": attrs,
                "attr_scale": scale,
                "renqi": renqi,
                "pop_title": pop_title(renqi),
                "pop_pct": min(1.0, renqi / 400),
                "coins": self._coins(star),
                "bag": info.get("bag_n", 0),
                "ach_got": info.get("ach_got", 0),
                "ach_all": len(ACHIEVEMENTS),
                "streak": int(star.get("sign_streak") or 0),
                "todo": info.get("todo", ""),
                "acts": info.get("acts", []),
                "recent": info.get("recent", []),
                "partner": info.get("partner"),
                "pending": info.get("pending"),
                "updated": time.strftime("更新于 %m-%d %H:%M"),
            }
            out = self.data_dir / "cards" / f"{gid}_{uid}.png"
            return gcard.render(data, str(out))
        except Exception as exc:
            logger.warning(f"[star_game] 面板图渲染失败，回退文字：{exc}")
            return None

    @filter.command("属性", alias={"我的", "我的属性", "资料", "面板", "档案"})
    async def cmd_status(self, event: AstrMessageEvent):
        """查看自己的艺人面板（发图；「属性 文字」看文字版）"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        lines = [f"@{star['name']}", star_card(star)]
        store = self.store
        assert store is not None

        # 今日待办：活动五项、签到、抽签冷却、发博额度，一眼看完
        acts = " ".join(
            (k + "✓") if store.activity_done(gid, uid, k) else (k + "✗")
            for k in ACTIVITIES
        )
        lines.append(f"  🗓 今日活动：{acts}")

        sign_txt = "已签" if star.get("last_sign") == today() else "未签"
        cd = max(1, self._i("draw_cooldown_min", 8)) * 60
        left = cd - seconds_since(star.get("last_draw"))
        draw_txt = "可抽" if left <= 0 else f"{int(left // 60) + 1} 分钟后"
        posts = store.count_activity(gid, uid, "发博")
        post_cap = self._i("post_daily_limit", 3)
        lines.append(
            f"  ✅ 签到 {sign_txt}｜🎲 抽签 {draw_txt}｜📱 发博 {posts}/{post_cap}"
        )

        got = store.achs_of(gid, uid)
        bag = store.inv_get(gid, uid)
        bag_n = sum(bag.values())
        lines.append(
            f"  💰 星币 {self._coins(star)}｜🎒 背包 {bag_n} 件"
            f"（「商店」「背包」）｜🏅 成就 {len(got)}/{len(ACHIEVEMENTS)}"
        )

        recent = store.recent_for(gid, star["name"], 3)
        recent_lines: List[str] = []
        if recent:
            lines.append("  📰 最近动态：")
            for r in recent:
                lines.append(f"    · {r['kind']}｜{str(r['text'])[:26]}")
                recent_lines.append(f"{r['kind']}｜{str(r['text'])[:18]}")

        pid = store.partner_of(gid, uid)
        partner_txt: Optional[str] = None
        pending_txt: Optional[str] = None
        if pid:
            p = store.get_star(gid, pid)
            rel = store.get_relation(gid, uid, pid)
            if p:
                tag = "💍 已婚" if rel.get("married") else "💞 恋人"
                lines.append(
                    f"  {tag}：{p['name']}｜好感 {gsocial.affection_bar(rel['affection'])}"
                )
                partner_txt = (
                    f"{'已婚' if rel.get('married') else '恋人'}：{p['name']}"
                    f"　好感 {int(rel['affection'])}/100"
                )
        else:
            pend = store.pendings_to(gid, uid)
            if pend:
                kinds = "、".join(
                    "求婚" if (x.get("kind") == "marry") else "表白" for x in pend
                )
                lines.append(
                    f"  💌 有 {len(pend)} 个人在等你回复（{kinds}），发「答应」或「拒绝」"
                )
                pending_txt = f"有 {len(pend)} 个人在等你回复（{kinds}）"

        want_text = "文字" in event.message_str or "text" in event.message_str.lower()
        if not want_text:
            img = self._status_image(
                gid,
                uid,
                star,
                {
                    "bag_n": bag_n,
                    "ach_got": len(got),
                    "todo": f"签到 {sign_txt}　抽签 {draw_txt}　发博 {posts}/{post_cap}",
                    "acts": [(k, store.activity_done(gid, uid, k)) for k in ACTIVITIES],
                    "recent": recent_lines,
                    "partner": partner_txt,
                    "pending": pending_txt,
                },
            )
            if img:
                yield event.image_result(img)
                event.stop_event()
                return

        yield event.plain_result("\n".join(lines))
        event.stop_event()

    @filter.command("成就", alias={"成就墙", "徽章"})
    async def cmd_ach(self, event: AstrMessageEvent):
        """看自己解锁了哪些成就"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        got = set(store.achs_of(gid, uid))
        lines = [f"🏅 {star['name']} 的成就墙（{len(got)}/{len(ACHIEVEMENTS)}）"]
        for key, (icon, name, desc) in ACHIEVEMENTS.items():
            if key in got:
                lines.append(f"  ✅ {icon} {name} — {desc}")
            else:
                lines.append(f"  🔒 {name}｜{desc}")
        lines.append("（达成新条件时会自动播报，不用手动领）")
        yield event.plain_result("\n".join(lines))
        event.stop_event()

    @filter.command("签到", alias={"每日签到", "打卡"})
    async def cmd_sign(self, event: AstrMessageEvent):
        """每日签到"""
        if not self._gate(event):
            return
        gid, uid, star, created = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)
        if created:
            head = (head + "\n" if head else "") + f"（顺手给你建了档案：{star['name']}，以后直接签到就行）"

        if star.get("last_sign") == today():
            yield event.plain_result(f"{head}\n今天已经签到过啦，明天再来领成长值～".strip())
            event.stop_event()
            return

        before = total_power(star)
        gains = do_sign(star)
        # 连签：昨天签过就接着数，断一天从 1 重新开始
        prev_sign = str(star.get("last_sign") or "")
        yday = (date.today() - timedelta(days=1)).isoformat()
        streak = int(star.get("sign_streak") or 0)
        streak = streak + 1 if prev_sign == yday else 1
        star["sign_streak"] = streak
        star["last_sign"] = today()
        store.save_star(star)
        big_attr, big_extra = gains["big"]  # type: ignore[misc]
        msg = [
            f"✅ {star['name']} 签到成功（连签第 {streak} 天）",
            f"  四项基础 +{gains['changtiao']}/+{gains['chuangzuo']}/+{gains['wudao']}/+{gains['shengyue']}",
            f"  今日高光：{ATTRS[big_attr]} 额外 +{big_extra}",
        ]

        # 连签里程碑（3/7/14/30 天各发一次）
        reward = STREAK_REWARDS.get(streak)
        if reward:
            r_pop, r_attr, r_desc = reward
            if r_attr:
                for k in ATTR_KEYS:
                    star[k] = int(star[k]) + r_attr
            star["renqi"] = pop_of(star) + r_pop
            store.save_star(star)
            msg.append(f"  🔥 连签 {streak} 天！{r_desc}")
            msg.append(
                f"     → 人气 +{r_pop}" + (f"、四项各 +{r_attr}" if r_attr else "")
            )
        elif streak > 1:
            nd = next_streak_day(streak)
            if nd:
                msg.append(f"  📅 再签 {nd - streak} 天有连签奖励")

        partner = store.partner_of(gid, uid)
        if partner:
            p = store.get_star(gid, partner)
            if p:
                for k in ATTR_KEYS:
                    star[k] = int(star[k]) + 2
                store.save_star(star)
                msg.append(f"  💞 情侣加成：{p['name']} 也在，四项各 +2")
            store.add_affection(gid, uid, partner, 2)

        after = total_power(star)
        msg.append(f"  综合实力 {before} → {after}（+{after - before}）{tier_change_msg(before, after)}")

        pop_delta = random.randint(1, 3)
        star["renqi"] = pop_of(star) + pop_delta
        star["coins"] = self._coins(star) + COIN_SIGN
        store.save_star(star)
        store.bump(gid, uid, self._month_key(), "sign")
        msg.append(f"  🔥 人气 +{pop_delta}（{pop_of(star)}｜{pop_title(pop_of(star))}）")
        msg.append(f"  💰 星币 +{COIN_SIGN}（{self._coins(star)}）")

        extra = await self._daily_extra(gid, star)
        if extra:
            msg.append("")
            msg.append(extra)

        fl = await self._flavor(
            star,
            "签到打卡",
            f"综合实力 {before} 涨到 {after}，人气 +{pop_delta}",
            after - before,
            umo=event.unified_msg_origin,
        )
        if fl:
            msg.append(fl)

        ev = await self._maybe_event(gid, star, [star])
        if ev:
            msg.append("")
            msg.append(ev)

        chal = (
            gnpc.maybe_challenge(
                store, gid, star, self._i("npc_challenge_probability", 12)
            )
            if self._b("npc_enabled", True)
            else None
        )
        if chal:
            prev_pk = star.get("last_pk")
            res = do_pk(star, chal, None)
            self._apply_pk(store, star, chal, res)
            star["last_pk"] = prev_pk  # 被约战不算自己发起，不吃掉比拼冷却
            store.save_star(star)
            msg.append(
                f"\n⚔️ {chal['name']} 主动找你约战了！\n"
                f"  {star['name']} {res['va']} VS {res['vb']} {chal['name']}\n"
                + self._pk_tail(star, chal, res)
            )

        for line in self._check_ach(gid, star):
            msg.append(line)

        body = "\n".join(msg)
        if head:
            body = f"{head}\n\n{body}"
        yield await self._finish(event, body, gid, star)
        event.stop_event()

    @filter.custom_filter(DrawFilter, False)
    async def cmd_draw(self, event: AstrMessageEvent):
        """抽签：随机 0-100 注入属性"""
        if not self._gate(event):
            return
        gid, uid, star, created = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)
        if created:
            head = (head + "\n" if head else "") + f"（已自动为你建立档案：{star['name']}）"

        cd = self._i("draw_cooldown_min", 8) * 60
        elapsed = seconds_since(star.get("last_draw"))
        if elapsed < cd:
            left = int(cd - elapsed)
            yield event.plain_result(
                f"{head}\n🎲 抽签太频繁啦，{left // 60}分{left % 60}秒后再来～".strip()
            )
            event.stop_event()
            return

        text = re.sub(r"\s+", "", event.message_str or "")
        key = "全能"
        if "欧皇" in text:
            key = "欧皇"
        elif "反向" in text or "霉运" in text:
            key = "反向"
        elif "单项" in text:
            key = "单项"

        results, before, after, rolled = do_draw(star, key)
        star["last_draw"] = now_iso()
        store.save_star(star)

        rows = [f"🎲 {star['name']} 抽签（{rolled}）"]
        for k in ATTR_KEYS:
            if k in results:
                rows.append(f"  {ATTRS[k]}：{fmt_gain(results[k])}")
        rows.append(f"  综合实力 {before} → {after}（{fmt_gain(after - before)}）{tier_change_msg(before, after)}")

        fl = await self._flavor(
            star,
            f"抽了个{key}签",
            f"综合实力 {before} 变成 {after}",
            after - before,
            umo=event.unified_msg_origin,
        )
        if fl:
            rows.append(fl)

        ev = await self._maybe_event(gid, star, [star])
        if ev:
            rows.append("")
            rows.append(ev)

        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield await self._finish(event, body, gid, star)
        event.stop_event()

    @filter.command("活动", alias={"参加", "参加活动", "act"})
    async def cmd_activity(self, event: AstrMessageEvent):
        """参加活动（选秀/写歌/斗舞/开嗓/盛典）"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        name = self._arg(event, "活动", "参加活动", "参加", "act")
        if not name:
            rows = ["🎪 可参加的活动（每天每项限一次）："]
            for k, (_, desc) in ACTIVITIES.items():
                rows.append(f"  · {k}：{desc}")
            rows.append("用法：参加 选秀 / 参加 写歌 / 参加 盛典")
            body = "\n".join(rows)
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        key = next((k for k in ACTIVITIES if k in name), None)
        if not key:
            yield event.plain_result("没有这个活动哦，发送「活动」查看列表。")
            event.stop_event()
            return
        if store.activity_done(gid, uid, key):
            yield event.plain_result(f"今天已经参加过「{key}」啦，明天再来～")
            event.stop_event()
            return
        if self._coins(star) < ACTIVITY_COST:
            yield event.plain_result(
                f"💰 场地费不够：练一次要 {ACTIVITY_COST} 星币，你只有 {self._coins(star)}。\n"
                "  签到、接戏、采访、接邀都能赚钱。"
            )
            event.stop_event()
            return

        self._gain(star, -ACTIVITY_COST)
        before = total_power(star)
        gains, desc = do_activity(star, key)
        store.mark_activity(gid, uid, key)
        store.save_star(star)
        after = total_power(star)

        rows = [
            f"🎪 {star['name']}｜{key}",
            f"  {desc}",
        ]
        rows += [f"  {ATTRS[k]} +{v}" for k, v in gains.items()]
        rows.append(f"  综合实力 {before} → {after}（+{after - before}）{tier_change_msg(before, after)}")
        star["coins"] = self._coins(star) + COIN_ACTIVITY
        store.save_star(star)
        store.bump(gid, uid, self._month_key(), f"act:{key}")
        rows.append(
            f"  💰 场地费 -{ACTIVITY_COST}、演出费 +{COIN_ACTIVITY}"
            f"（{self._coins(star)}）"
        )

        fl = await self._flavor(
            star,
            f"去参加了{key}",
            f"{desc}，综合实力 {before} 变成 {after}",
            after - before,
            umo=event.unified_msg_origin,
        )
        if fl:
            rows.append(fl)

        ev = await self._maybe_event(gid, star, store.players(gid))
        if ev:
            rows.append("")
            rows.append(ev)

        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield await self._finish(event, body, gid, star)
        event.stop_event()

    # ---- 比拼 ----
    def _apply_pk(self, store: Store, a: dict, b: dict, res: dict) -> None:
        if res["winner"] is None:
            a["draws"] = int(a["draws"]) + 1
            b["draws"] = int(b["draws"]) + 1
        elif res["winner"] == "a":
            a["wins"] = int(a["wins"]) + 1
            b["losses"] = int(b["losses"]) + 1
        else:
            b["wins"] = int(b["wins"]) + 1
            a["losses"] = int(a["losses"]) + 1
        a["last_pk"] = now_iso()
        b["last_pk"] = now_iso()
        store.save_star(a)
        store.save_star(b)

    def _pk_tail(self, a: dict, b: dict, res: dict) -> str:
        if res["winner"] is None:
            return (
                f"  🤝 平局！双方各得：{ATTRS[res['wattr']]} +{res['wgain']} / "
                f"{ATTRS[res['lattr']]} +{res['lgain']}"
            )
        return (
            f"  🏆 胜者：{(a if res['winner'] == 'a' else b)['name']}"
            f"（{ATTRS[res['wattr']]} +{res['wgain']}）\n"
            f"  💪 败者：{(b if res['winner'] == 'a' else a)['name']}"
            f"（{ATTRS[res['lattr']]} +{res['lgain']}，安慰奖）"
        )

    @filter.command("比拼", alias={"pk", "对决", "单挑", "battle", "挑战"})
    async def cmd_pk(self, event: AstrMessageEvent):
        """比拼：@某人 或 写 NPC 名字；不写对手＝随机挑战一位 NPC"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "比拼", "单挑", "对决", "battle", "挑战", "pk")
        at_qq = self._at_target(event)

        rival: Optional[dict] = None
        if at_qq:
            if at_qq == uid:
                yield event.plain_result("不能挑战自己啦～")
                event.stop_event()
                return
            rival = store.get_star(gid, at_qq)
            if not rival:
                yield event.plain_result("对方还没出道，先让他发个「出道」吧～")
                event.stop_event()
                return
        else:
            name = self._pick_person(arg)
            if name:
                rival = gsocial.resolve_target(store, gid, name, uid)
            if rival is None and self._b("npc_enabled", True):
                rival = gnpc.random_npc(store, gid, near=total_power(me))
            if rival is None:
                yield event.plain_result("场上没有对手，先让大家「出道」吧～")
                event.stop_event()
                return

        cd = self._i("pk_cooldown_min", 3) * 60
        elapsed = seconds_since(me.get("last_pk"))
        if elapsed < cd:
            left = int(cd - elapsed)
            yield event.plain_result(f"⏳ 比拼冷却中，{left // 60}分{left % 60}秒后再来。")
            event.stop_event()
            return

        attr_key = next((k for k, nm in ATTRS.items() if nm in arg), None)
        res = do_pk(me, rival, attr_key)
        self._apply_pk(store, me, rival, res)

        pop_line = ""
        if res["winner"] == "a":
            d = random.randint(2, 5)
            me["renqi"] = pop_of(me) + d
            store.save_star(me)
            pop_line = f"  🔥 赢了热度：人气 +{d}（{pop_of(me)}｜{pop_title(pop_of(me))}）"
        elif res["winner"] is None:
            me["renqi"] = pop_of(me) + 1
            store.save_star(me)

        if not rival.get("is_npc"):
            # 真人之间打一架也顺便涨点好感
            store.add_affection(gid, uid, rival["qq_id"], 2)

        npc_line = ""
        if rival.get("is_npc") and self.ai is not None:
            scene = (
                f"{me['name']}（{total_power(me)}）和你在「{res['label']}」上比拼，"
                + ("你赢了。" if res["winner"] == "b" else "你输了。" if res["winner"] == "a" else "打成平局。")
            )
            npc_line = await gnpc.npc_line(self.ai, rival, scene)

        rows = [f"⚔️ {res['label']}｜{me['name']} {res['va']} VS {res['vb']} {rival['name']}{'(NPC)' if rival.get('is_npc') else ''}"]
        bonus = []
        if res.get("pa", 0) > 0.001:
            bonus.append(f"{me['name']} +{int(round(res['pa'] * 100))}%")
        if res.get("pb", 0) > 0.001:
            bonus.append(f"{rival['name']} +{int(round(res['pb'] * 100))}%")
        if bonus:
            rows.append(f"  🔥 人气加成：{' / '.join(bonus)}")
        rows.append(self._pk_tail(me, rival, res))
        if pop_line:
            rows.append(pop_line)
        if npc_line:
            rows.append(f"  💬 {rival['name']}：{npc_line}")

        _verdict = (
            "赢了" if res["winner"] == "a" else "输了" if res["winner"] == "b" else "打平"
        )
        fl = await self._flavor(
            me,
            f"和{rival['name']}比了一场「{res['label']}」",
            f"{res['va']} 对 {res['vb']}，{_verdict}",
            8 if res["winner"] == "a" else -4 if res["winner"] == "b" else 0,
            umo=event.unified_msg_origin,
        )
        if fl:
            rows.append(fl)

        if res["winner"] == "a":
            me["coins"] = self._coins(me) + COIN_PK_WIN
            store.save_star(me)
            store.bump(gid, uid, self._month_key(), "win")
            rows.append(f"  💰 星币 +{COIN_PK_WIN}（{self._coins(me)}）")

        for line in self._check_ach(gid, me):
            rows.append(line)

        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield await self._finish(event, body, gid, me)
        event.stop_event()

    @filter.command("排行", alias={"排行榜", "榜单", "排名", "rank"})
    async def cmd_rank(self, event: AstrMessageEvent):
        """排行榜（含 NPC）"""
        if not self._gate(event):
            return
        gid = str(event.get_group_id())
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "排行榜", "排行榜", "排行", "榜单", "排名", "rank")

        if "段位" in arg or "分布" in arg:
            stars = store.all_stars(gid, include_npc=False)
            if not stars:
                yield event.plain_result("本群还没有明星出道，快喊大家「出道」吧～")
                event.stop_event()
                return
            dist: dict = {}
            for s in stars:
                cur, _ = get_tier(total_power(s))
                dist[cur[1]] = dist.get(cur[1], 0) + 1
            rows = [f"📈 本群段位分布（{len(stars)} 人）："]
            for _, name in TIERS:
                if dist.get(name):
                    rows.append(f"  {name}：{dist[name]} 人")
            body = "\n".join(rows)
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        if "人气" in arg or "热度" in arg:
            order_by = "renqi"
        else:
            order_by = next((k for k, nm in ATTRS.items() if nm in arg), "total")
        top = store.ranking(gid, order_by, 15)
        if not top:
            yield event.plain_result("本群还没有明星出道，快喊大家「出道」吧～")
            event.stop_event()
            return

        if order_by == "total":
            label = "综合实力"
        elif order_by == "renqi":
            label = "人气"
        else:
            label = ATTRS[order_by]
        rows = [f"🏅 本群「{label}」榜（真人和 NPC 一起排）："]
        for i, s in enumerate(top, 1):
            if order_by == "total":
                val = total_power(s)
            elif order_by == "renqi":
                val = pop_of(s)
            else:
                val = int(s[order_by])
            cur, _ = get_tier(total_power(s))
            medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
            tag = "·NPC" if s.get("is_npc") else ""
            tail = f"｜{pop_title(val)}" if order_by == "renqi" else f"｜{cur[1]}"
            rows.append(f"  {medal} {s['name']}{tag}｜{val}{tail}")
        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("改名", alias={"改艺名", "设置艺名"})
    async def cmd_rename(self, event: AstrMessageEvent):
        """改艺名"""
        if not self._gate(event):
            return
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        new_name = self._arg(event, "改艺名", "设置艺名", "改名")
        if not new_name:
            yield event.plain_result("用法：改名 你的新艺名")
            event.stop_event()
            return
        if len(new_name) > 12:
            yield event.plain_result("艺名太长啦，12 个字以内。")
            event.stop_event()
            return
        star["name"] = new_name
        self.store.save_star(star)  # type: ignore[union-attr]
        msg = f"✅ 艺名已改为「{new_name}」。"
        msg += await self._flavor(
            star, f"把艺名改成了「{new_name}」", "换了新身份", 0, umo=event.unified_msg_origin
        )
        yield event.plain_result(msg)
        event.stop_event()

    @filter.command("运势", alias={"今日运势", "luck"})
    async def cmd_fortune(self, event: AstrMessageEvent):
        """今日运势（彩蛋）"""
        if not self._gate(event):
            return
        msg = f"🔮 今日运势：{random.choice(FORTUNES)}"
        gid, uid, star, _ = self._player(event)  # type: ignore[misc]
        msg += await self._flavor(
            star, "看了今日运势", "仅供参考", 0, umo=event.unified_msg_origin
        )
        yield event.plain_result(msg)
        event.stop_event()

    # ---------------- 商店 / 背包 ----------------
    @filter.command("商店", alias={"礼品店", "shop"})
    async def cmd_shop(self, event: AstrMessageEvent):
        """礼品商店：看货架"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)
        body = (
            "🛍 礼品商店\n"
            + gsocial.gift_menu()
            + f"\n\n💰 你的星币：{self._coins(me)}\n"
            "用法：买 鲜花 2　／　看完去「送礼 名字 礼物」"
        )
        bag = store.inv_get(gid, uid)
        if bag:
            body += "\n🎒 背包：" + "、".join(f"{k}×{v}" for k, v in bag.items())
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("买", alias={"购买", "buy"})
    async def cmd_buy(self, event: AstrMessageEvent):
        """买礼物：买 鲜花 2"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None

        arg = self._arg(event, "买", "购买", "buy")
        if not arg:
            yield event.plain_result("要买什么？例如「买 鲜花 2」，发「商店」看清单。")
            event.stop_event()
            return
        gift = next((g for g in GIFT_SHOP if g in arg), None)
        if not gift:
            yield event.plain_result("商店里没有这个，发「商店」看清单～")
            event.stop_event()
            return
        mt = re.search(r"(?<![0-9])([1-9][0-9]?)(?![0-9])", arg.replace(gift, " "))
        count = int(mt.group(1)) if mt else 1
        count = max(1, min(20, count))
        if gift == "求婚戒指":
            count = 1

        cost = int(GIFT_SHOP[gift]["price"]) * count
        have = self._coins(me)
        if have < cost:
            yield event.plain_result(
                f"💰 星币不够：{gift}×{count} 要 {cost}，你只有 {have}。\n"
                "  接戏、采访、邀约、签到都能来钱。"
            )
            event.stop_event()
            return

        self._gain(me, -cost)
        total = store.inv_add(gid, uid, gift, count)
        body = (
            f"🛍 买下 {gift}×{count}，花了 {cost} 星币（剩 {self._coins(me)}）\n"
            f"  🎒 背包里现在有 {total} 个\n"
            f"  用法：送礼 名字 {gift}"
        )
        if store.unlock(gid, uid, "shopper"):
            body += "\n🏅 成就解锁 🛍️「会花钱」— 第一次在礼品店买东西"
        if gift == "求婚戒指":
            body += "\n  💍 这枚戒指只能用来「求婚」，送不出去。"
        for line in self._check_ach(gid, me):
            body += "\n" + line
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("背包", alias={"我的东西", "bag"})
    async def cmd_bag(self, event: AstrMessageEvent):
        """看背包"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)
        bag = store.inv_get(gid, uid)
        if not bag:
            body = "🎒 背包是空的，去「商店」看看？"
        else:
            rows = ["🎒 背包："]
            for item, cnt in bag.items():
                desc = GIFT_SHOP.get(item, {}).get("desc", "")
                rows.append(f"  · {item}×{cnt}" + (f" — {desc}" if desc else ""))
            rows.append(f"\n💰 星币：{self._coins(me)}")
            body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    # ---------------- 恋爱 ----------------
    @filter.command("送礼", alias={"礼物", "gift"})
    async def cmd_gift(self, event: AstrMessageEvent):
        """送礼（加好感）：送礼 名字 礼物"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "礼物", "送礼", "gift")
        if not arg:
            body = "🛍 礼物要先在「商店」买（发「商店」看价格）：\n" + gsocial.gift_menu()
            body += "\n用法：送礼 林晚星 奶茶"
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        gift = next((g for g in gsocial.GIFTS if g in arg), None)
        name = re.sub(r"\s+", " ", arg).replace(gift, "").strip() if gift else arg
        target = gsocial.resolve_target(store, gid, self._pick_person(name), uid)
        if not gift:
            yield event.plain_result("没有这种礼物，发「礼物」看看清单～")
            event.stop_event()
            return
        if not target:
            yield event.plain_result(f"找不到「{name}」这个人，可以用「明星」看看 NPC 名单。")
            event.stop_event()
            return

        rel = store.get_relation(gid, uid, target["qq_id"])
        ok, used = gsocial.gift_allowed(rel, gift)
        if not ok:
            yield event.plain_result(f"今天已经送过 {used} 次「{gift}」了，明天再来吧～")
            event.stop_event()
            return

        if not store.inv_take(gid, uid, gift, 1):
            price = int(GIFT_SHOP[gift]["price"])
            yield event.plain_result(
                f"🎒 背包里没有「{gift}」了。\n"
                f"  先去「商店」买：{gift} {price} 星币（你有 {self._coins(me)}）"
            )
            event.stop_event()
            return

        delta, rel = gsocial.apply_gift(store, gid, uid, target["qq_id"], gift)
        rows = [
            f"🎁 {me['name']} 送了 {target['name']} 一份「{gift}」",
            f"  好感 +{delta}｜{gsocial.affection_bar(rel['affection'])}（{gsocial.affection_word(rel['affection'])}）",
        ]
        if rel.get("couple"):
            rows.append("  💞 你们已经在交往了，对方笑得很明显。")
        body = "\n".join(rows)
        body += await self._flavor(
            me,
            f"送了{target['name']}一份{gift}",
            f"好感 +{delta}",
            delta,
            umo=event.unified_msg_origin,
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("表白", alias={"告白", "confess"})
    async def cmd_confess(self, event: AstrMessageEvent):
        """表白：表白 名字"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "告白", "表白", "confess")
        at_qq = self._at_target(event)
        target = (
            store.get_star(gid, at_qq)
            if at_qq
            else gsocial.resolve_target(store, gid, self._pick_person(arg), uid)
        )
        if not target:
            yield event.plain_result("要跟谁表白？写名字，例如「表白 林晚星」。")
            event.stop_event()
            return
        if target["qq_id"] == uid:
            yield event.plain_result("自己跟自己表白…也不是不行，但程序不允许。")
            event.stop_event()
            return

        mine = store.partner_of(gid, uid)
        theirs = store.partner_of(gid, target["qq_id"])
        if mine or theirs:
            yield event.plain_result("有人已经在恋爱中了，先「分手」再谈吧～")
            event.stop_event()
            return

        rel = store.get_relation(gid, uid, target["qq_id"])
        need = gsocial.confess_threshold(target, rel["affection"])

        if target.get("is_npc"):
            if rel["affection"] < need:
                store.add_affection(gid, uid, target["qq_id"], -5)
                delta = -5
                body = (
                    f"💔 {target['name']} 愣了一下，笑着把话题岔开了。\n"
                    f"  当前好感 {rel['affection']}/{need}，再刷一刷吧（送礼、比拼都行）。"
                )
            else:
                gsocial.make_couple(store, gid, uid, target["qq_id"])
                delta = 8
                line = ""
                if self.ai is not None:
                    line = await gnpc.npc_line(
                        self.ai, target, f"{me['name']} 对你表白了，你答应了。"
                    )
                body = (
                    f"💞 {target['name']} 沉默两秒，说：「{line or '……好。'}」\n"
                    f"  你和 {target['name']} 开始交往了！"
                )
                for ach_line in self._check_ach(gid, me):
                    body += "\n" + ach_line
        else:
            store.add_pending(gid, "confess", uid, target["qq_id"])
            delta = 0
            body = (
                f"💌 你把心意说给了 {target['name']} 听。\n"
                f"  等对方发「答应」或「拒绝」吧。"
            )

        body += await self._flavor(
            me,
            f"向{target['name']}表白了",
            "成了" if delta >= 6 else ("被婉拒了" if delta < 0 else "还在等回音"),
            delta,
            umo=event.unified_msg_origin,
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("求婚", alias={"求婚吧", "propose"})
    async def cmd_propose(self, event: AstrMessageEvent):
        """求婚：求婚 名字（需要背包里有求婚戒指）"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "求婚", "求婚吧", "propose")
        at_qq = self._at_target(event)
        target = (
            store.get_star(gid, at_qq)
            if at_qq
            else gsocial.resolve_target(store, gid, self._pick_person(arg), uid)
        )
        if not target:
            yield event.plain_result("要跟谁求婚？写名字，例如「求婚 林晚星」。")
            event.stop_event()
            return
        if target["qq_id"] == uid:
            yield event.plain_result("自己娶自己…程序不允许。")
            event.stop_event()
            return
        if not store.inv_take(gid, uid, "求婚戒指", 1):
            yield event.plain_result(
                "💍 你还没有求婚戒指。\n"
                f"  去「商店」买一枚：求婚戒指 {int(GIFT_SHOP['求婚戒指']['price'])} 星币"
            )
            event.stop_event()
            return

        rel = store.get_relation(gid, uid, target["qq_id"])
        aff = int(rel["affection"])
        mine = store.married_of(gid, uid)
        theirs = store.married_of(gid, target["qq_id"])
        if mine or theirs:
            store.inv_add(gid, uid, "求婚戒指", 1)
            yield event.plain_result("有一方已经结婚了，戒指退给你，先处理一下关系吧～")
            event.stop_event()
            return

        if target.get("is_npc"):
            if aff < MARRY_AFFECTION:
                store.inv_add(gid, uid, "求婚戒指", 1)
                body = (
                    f"💍 你单膝跪下，{target['name']} 愣了很久，轻轻摇头。\n"
                    f"  当前好感 {aff}/{MARRY_AFFECTION}，戒指留着了。"
                )
                delta = -2
            else:
                gsocial.marry(store, gid, uid, target["qq_id"])
                line = ""
                if self.ai is not None:
                    line = await gnpc.npc_line(
                        self.ai, target, f"{me['name']} 向你求婚，你答应了。"
                    )
                body = (
                    f"💍 {target['name']} 眼圈红了，说：「{line or '……嗯。'}」\n"
                    f"  🎉 {me['name']} 和 {target['name']} 结婚了！"
                )
                delta = 10
        else:
            store.add_pending(gid, "marry", uid, target["qq_id"])
            body = (
                f"💍 你向 {target['name']} 求婚了，戒指已经交到对方手上。\n"
                f"  等对方发「答应」或「拒绝」吧。"
            )
            delta = 0

        for line in self._check_ach(gid, me):
            body += "\n" + line
        body += await self._flavor(
            me,
            f"向{target['name']}求婚",
            "答应了" if delta >= 8 else ("被拒了" if delta < 0 else "等回音"),
            delta,
            umo=event.unified_msg_origin,
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("答应", alias={"接受"})
    async def cmd_accept(self, event: AstrMessageEvent):
        """答应表白"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        pend = store.pendings_to(gid, uid)
        if not pend:
            yield event.plain_result("现在没有人对你表白哦。")
            event.stop_event()
            return
        p = pend[0]
        if (p.get("kind") or "confess") == "marry":
            if store.married_of(gid, uid) or store.married_of(gid, p["from_id"]):
                yield event.plain_result("有一方已经结婚了，这门亲事办不了。")
                event.stop_event()
                return
            gsocial.marry(store, gid, uid, p["from_id"])
            store.del_pending(gid, "marry", p["from_id"], uid)
            other = store.get_star(gid, p["from_id"])
            name = other["name"] if other else "对方"
            body = f"💍 {me['name']} 答应了 {name} 的求婚，两人结婚了！"
            for line in self._check_ach(gid, me):
                body += "\n" + line
            if other:
                for line in self._check_ach(gid, other):
                    body += "\n" + line
            body += await self._flavor(
                me, f"嫁给了{name}", "修成正果", 10, umo=event.unified_msg_origin
            )
            yield event.plain_result(body)
            event.stop_event()
            return
        if store.partner_of(gid, uid) or store.partner_of(gid, p["from_id"]):
            yield event.plain_result("有一方已经在恋爱中了，先处理一下关系吧～")
            event.stop_event()
            return
        gsocial.make_couple(store, gid, uid, p["from_id"])
        store.del_pending(gid, "confess", p["from_id"], uid)
        other = store.get_star(gid, p["from_id"])
        name = other["name"] if other else "对方"
        extra = ""
        for line in self._check_ach(gid, me):
            extra += "\n" + line
        if other:
            for line in self._check_ach(gid, other):
                extra += "\n" + line
        body = (
            f"💞 {me['name']} 答应了 {name} 的表白，两人开始交往！{extra}"
        )
        body += await self._flavor(
            me, f"答应了{name}的表白", "在一起了", 8, umo=event.unified_msg_origin
        )
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("拒绝")
    async def cmd_reject(self, event: AstrMessageEvent):
        """拒绝表白"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        pend = store.pendings_to(gid, uid)
        if not pend:
            yield event.plain_result("现在没有人对你表白哦。")
            event.stop_event()
            return
        p = pend[0]
        if (p.get("kind") or "confess") == "marry":
            store.del_pending(gid, "marry", p["from_id"], uid)
            other = store.get_star(gid, p["from_id"])
            store.add_affection(gid, p["from_id"], uid, -10)
            name = other["name"] if other else "对方"
            body = (
                f"💔 {me['name']} 没有收下 {name} 的戒指，"
                "戒指留在对方手里了。"
            )
            body += await self._flavor(
                me, f"拒绝了{name}的求婚", "有点伤人", -4,
                umo=event.unified_msg_origin,
            )
            yield event.plain_result(body)
            event.stop_event()
            return
        store.del_pending(gid, "confess", p["from_id"], uid)
        other = store.get_star(gid, p["from_id"])
        if other:
            store.add_affection(gid, p["from_id"], uid, -10)
            body = f"💔 {me['name']} 婉拒了 {other['name']} 的表白。"
            body += await self._flavor(
                me,
                f"婉拒了{other['name']}",
                "关系有点僵",
                -4,
                umo=event.unified_msg_origin,
            )
            yield event.plain_result(body)
        else:
            yield event.plain_result("已经拒绝了。")
        event.stop_event()

    @filter.command("分手", alias={"离婚", "分手吧"})
    async def cmd_breakup(self, event: AstrMessageEvent):
        """分手"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        pid = store.partner_of(gid, uid)
        if not pid:
            yield event.plain_result("你现在是单身，分手也没人可分的说…")
            event.stop_event()
            return
        married = bool(store.married_of(gid, uid))
        if married:
            gsocial.divorce(store, gid, uid, pid)
        else:
            gsocial.breakup(store, gid, uid, pid)
        other = store.get_star(gid, pid)
        oname = other["name"] if other else "对方"
        if married:
            body = (
                f"💔 {me['name']} 和 {oname} 离婚了。\n"
                f"  双方好感 -{MARRY_DIVORCE_PENALTY}，婚戒不退，江湖再见。"
            )
        else:
            body = (
                f"💔 {me['name']} 和 {oname} 结束了这段关系。\n"
                "  双方好感 -30，江湖再见。"
            )
        body += await self._flavor(
            me, "结束了这段关系", "各走各的", -4, umo=event.unified_msg_origin
        )
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("情侣", alias={"cp", "CP", "关系"})
    async def cmd_couple(self, event: AstrMessageEvent):
        """看本群的情侣关系"""
        if not self._gate(event):
            return
        gid = str(event.get_group_id())
        store = self.store
        assert store is not None
        head = self._daily(gid)
        couples = store.couples(gid)
        rows = ["💞 本群 CP 榜："] if couples else ["💞 本群还没有一对 CP，去「表白」试试？"]
        for r in couples[:10]:
            a = store.get_star(gid, r["a_id"])
            b = store.get_star(gid, r["b_id"])
            if not a or not b:
                continue
            rows.append(
                f"  · {a['name']} × {b['name']}｜好感 {r['affection']}"
            )
        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    # ================= AI 剧情：通告 / 采访 / 发博 / 搭讪 / 月报 =================
    def _story_timeout(self) -> int:
        return max(5, self._i("story_timeout_min", 30)) * 60

    def _load_story(self, gid: str, uid: str, kind: str):
        """读剧情状态：返回 None（没有）、{'expired': True}（超时作废）、或故事 dict。"""
        store = self.store
        if store is None:
            return None
        st = store.get_story(gid, uid, kind)
        if not st:
            return None
        if seconds_since(st.get("updated_at")) > self._story_timeout():
            store.del_story(gid, uid, kind)
            return {"expired": True}
        return st

    def _apply_effects(self, store: Store, star: dict, effects: dict) -> str:
        rows = []
        for k, v in (effects or {}).items():
            if k == "renqi":
                star["renqi"] = max(0, pop_of(star) + int(v))
                rows.append(f"人气{fmt_gain(int(v))}")
            elif k in ATTR_KEYS:
                star[k] = max(0, int(star[k]) + int(v))
                rows.append(f"{ATTRS[k]}{fmt_gain(int(v))}")
        store.save_star(star)
        return "、".join(rows) or "人气波动（无属性变化）"

    @filter.command("接戏", alias={"通告", "试镜", "进组"})
    async def cmd_drama(self, event: AstrMessageEvent):
        """接一部通告，进入 AI 互动剧本"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        cur = self._load_story(gid, uid, "drama")
        if cur and not cur.get("expired"):
            d = cur["data"]
            opts = "\n".join(
                f"  {chr(65 + i)}. {o}" for i, o in enumerate(d.get("options") or [])
            )
            body = (
                f"你手上还有《{d.get('title', '')}》第 {cur['step']} 幕没拍完。\n"
                f"{d.get('scene', '')}\n{opts}\n回「选 A/B/C」继续，或者「放弃」。"
            )
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return
        if cur and cur.get("expired"):
            head = (head + "\n" if head else "") + "（上一部通告超时作废了）"

        setup = random.choice(DRAMA_SETUPS)
        scene = None
        if self.ai is not None:
            scene = await self.ai.drama_scene(setup["title"], setup["role"], 1, "")
        if not scene:
            body = "剧组那边没回话（模型没接上），过一会儿再「接戏」试试。"
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        store.save_story(
            gid,
            uid,
            "drama",
            1,
            {
                "title": setup["title"],
                "role": setup["role"],
                "scene": scene["scene"],
                "options": scene["options"],
                "history": [],
            },
        )
        opts = "\n".join(f"  {chr(65 + i)}. {o}" for i, o in enumerate(scene["options"]))
        body = (
            f"🎬 你拿到了新通告：{setup['title']}\n"
            f"你的角色：{setup['role']}\n"
            "──────────────\n"
            f"第 1 幕｜{scene['scene']}\n"
            f"{opts}\n"
            "回「选 A / B / C」推进剧情（3 幕定生死）。"
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("选", alias={"选择"})
    async def cmd_choose(self, event: AstrMessageEvent):
        """在通告剧情里做选择：选 A / B / C"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None

        st = self._load_story(gid, uid, "drama")
        if not st:
            yield event.plain_result("你现在没有在拍的戏，先「接戏」接一部。")
            event.stop_event()
            return
        if st.get("expired"):
            yield event.plain_result("那部通告超时作废了，重新「接戏」吧。")
            event.stop_event()
            return

        d = st["data"]
        opts = d.get("options") or []
        arg = self._arg(event, "选择", "选").upper()
        letter = next((c for c in "ABC" if c in arg), None)
        idx = "ABC".index(letter) if letter else None
        if idx is None:
            digits = re.findall(r"[123]", arg)
            idx = int(digits[0]) - 1 if digits else None
        if idx is None or idx >= len(opts):
            rows = "\n".join(f"  {chr(65 + i)}. {o}" for i, o in enumerate(opts))
            yield event.plain_result(f"请回「选 A / B / C」～\n{rows}")
            event.stop_event()
            return

        chosen = opts[idx]
        hist = d.get("history") or []
        hist.append({"step": st["step"], "choice": chosen})
        step = int(st["step"]) + 1
        hist_text = "\n".join(f"第{h['step']}幕：{h['choice']}" for h in hist)

        if step <= 3:
            scene = None
            if self.ai is not None:
                scene = await self.ai.drama_scene(d["title"], d["role"], step, hist_text)
            if not scene:
                # 写不出下一幕就直接收尾，别把玩家卡住
                st["step"] = step
                d["history"] = hist
                store.save_story(gid, uid, "drama", step, d)
                scene = {
                    "scene": "导演突然宣布：档期被砍，剩下的戏全部并进最后一场。",
                    "options": ["硬着头皮演完", "要求改剧本", "借机加一段独白"],
                }
            store.save_story(
                gid,
                uid,
                "drama",
                step,
                {"title": d["title"], "role": d["role"], "scene": scene["scene"],
                 "options": scene["options"], "history": hist},
            )
            rows = "\n".join(f"  {chr(65 + i)}. {o}" for i, o in enumerate(scene["options"]))
            yield event.plain_result(
                f"🎬{d['title']}｜第 {step} 幕\n{scene['scene']}\n{rows}\n回「选 A / B / C」。"
            )
            event.stop_event()
            return

        # 三幕结束，结算
        end = None
        if self.ai is not None:
            end = await self.ai.drama_end(d["title"], hist_text)
        if not end:
            end = {
                "ending": FALLBACK_ENDING,
                "score": random.randint(40, 70),
                "effects": {random.choice(ATTR_KEYS): random.randint(3, 8)},
            }

        effs = dict(end.get("effects") or {})
        if "renqi" not in effs:
            sc = int(end.get("score", 50))
            effs["renqi"] = 25 if sc >= 85 else 12 if sc >= 60 else -5
        eff_text = self._apply_effects(store, me, effs)
        store.del_story(gid, uid, "drama")
        store.log_event(gid, "通告", f"《{d['title']}》杀青，表现分 {end['score']}")

        grade = "封神" if end["score"] >= 85 else "合格" if end["score"] >= 60 else "翻车"
        fee = max(0, int(DRAMA_BASE_FEE + int(end["score"]) * DRAMA_SCORE_FEE))
        self._gain(me, fee)
        fl = await self._flavor(
            me,
            f"拍完了《{d['title']}》",
            f"表现分 {end['score']}/100（{grade}）",
            10 if end["score"] >= 85 else 3 if end["score"] >= 60 else -5,
            umo=event.unified_msg_origin,
        )
        ach = self._check_ach(gid, me)
        yield event.plain_result(
            f"🎬 {d['title']} 杀青（{grade}）\n"
            f"{end['ending']}\n"
            f"  📊 表现分：{end['score']}/100\n"
            f"  → {eff_text}\n"
            f"  💰 片酬 +{fee}（{self._coins(me)}）{fl}"
            + ("\n" + "\n".join(ach) if ach else "")
        )
        event.stop_event()

    @filter.command("采访", alias={"记者", "被采访"})
    async def cmd_interview(self, event: AstrMessageEvent):
        """接受一次八卦采访，回答得好有加成"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        st = self._load_story(gid, uid, "interview")
        if st and not st.get("expired"):
            q = st["data"].get("q", "")
            body = f"记者还在等你回答刚才那句：\n「{q}」\n回「回答 你的话」。"
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        q = None
        if self.ai is not None:
            q = await self.ai.interview_question(me["name"])
        if not q:
            q = random.choice(FALLBACK_QUESTIONS)
        store.save_story(gid, uid, "interview", 1, {"q": q})
        body = f"🎤 记者把话筒怼到你面前：\n「{q}」\n回「回答 你的话」——答得好会涨路人缘。"
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("回答", alias={"应答", "答记者问"})
    async def cmd_answer(self, event: AstrMessageEvent):
        """回答记者的提问"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None

        st = self._load_story(gid, uid, "interview")
        if not st:
            yield event.plain_result("现在没有记者在等你，发「采访」叫一个来。")
            event.stop_event()
            return
        if st.get("expired"):
            yield event.plain_result("这场采访超时散场了，重新「采访」吧。")
            event.stop_event()
            return

        ans = self._arg(event, "答记者问", "应答", "回答")
        if len(ans) < 2:
            yield event.plain_result("回答得太短了，记者不会信的，多说两句～")
            event.stop_event()
            return
        q = st["data"].get("q", "")
        res = None
        if self.ai is not None:
            res = await self.ai.judge_answer(q, ans)
        if not res:
            res = {
                "comment": "现场安静了两秒，记者把话筒收了回去。",
                "headline": f"{me['name']} 采访现场语塞",
                "score": random.randint(3, 6),
                "effects": {},
            }

        effs = dict(res.get("effects") or {})
        if "renqi" not in effs:
            score = int(res.get("score", 5))
            effs["renqi"] = 6 if score >= 8 else 2 if score >= 5 else -3
        eff_text = self._apply_effects(store, me, effs)
        store.del_story(gid, uid, "interview")
        store.log_event(gid, "采访", f"回应「{q[:16]}…」：{res['headline']}")

        score = int(res.get("score", 5))
        fl = await self._flavor(
            me,
            "刚被记者堵了一次",
            f"表现分 {score}/10，明天见报《{res['headline']}》",
            6 if score >= 8 else 2 if score >= 5 else -3,
            umo=event.unified_msg_origin,
        )
        ach = self._check_ach(gid, me)
        tail = "\n" + "\n".join(ach) if ach else ""
        self._gain(me, INTERVIEW_FEE)

        yield event.plain_result(
            f"🎤 记者把这段话记了下来。\n"
            f"  「{res['comment']}」\n"
            f"  📈 表现分 {score}/10｜{eff_text}\n"
            f"  💰 采访费 +{INTERVIEW_FEE}（{self._coins(me)}）\n"
            f"  📰 明天见报：《{res['headline']}》{fl}{tail}"
        )
        event.stop_event()

    @filter.command("发博", alias={"微博", "发文", "营业"})
    async def cmd_post(self, event: AstrMessageEvent):
        """发一条微博，AI 生成评论区舆论"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        content = self._arg(event, "发博", "微博", "发文", "营业")
        if len(content) < 2:
            body = "用法：发博 今天练到脚趾头抽筋，但那段舞我拿下了"
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return
        limit = self._i("post_daily_limit", 3)
        if store.count_activity(gid, uid, "发博") >= limit:
            yield event.plain_result(f"今天已经发了 {limit} 条了，再发就变刷屏小号了。")
            event.stop_event()
            return

        store.mark_activity(gid, uid, "发博")
        cur, _ = get_tier(total_power(me))
        res = None
        if self.ai is not None:
            res = await self.ai.judge_post(me["name"], cur[1], total_power(me), content)
        if not res:
            res = {
                "comments": list(FALLBACK_POST_COMMENTS),
                "sentiment": "neutral",
                "effects": {},
            }

        effs = dict(res.get("effects") or {})
        if "renqi" not in effs:
            effs["renqi"] = {"positive": 5, "negative": -5, "neutral": 1}[res["sentiment"]]
        eff_text = self._apply_effects(store, me, effs)
        mood = {"positive": "正面", "negative": "翻车", "neutral": "平平"}[res["sentiment"]]
        store.log_event(gid, "发博", f"{me['name']}：{content[:24]}（{mood}）")

        rows = [
            f"📱 {me['name']} 发了一条微博：",
            f"  「{content}」",
            "──────────────",
            "评论区：",
        ]
        rows += [f"  · {c}" for c in res["comments"]]
        rows.append(f"  📊 舆论：{mood}｜{eff_text}")
        me["coins"] = self._coins(me) + COIN_POST
        store.save_star(me)
        rows.append(f"  💰 星币 +{COIN_POST}（{self._coins(me)}）")

        d_pop = int(effs.get("renqi", 0) or 0)
        fl = await self._flavor(
            me,
            "发了条微博",
            f"评论区舆论{mood}",
            d_pop,
            umo=event.unified_msg_origin,
        )
        ach = self._check_ach(gid, me)
        body = "\n".join(rows) + fl + ("\n" + "\n".join(ach) if ach else "")
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("搭讪", alias={"撩", "私聊", "聊天"})
    async def cmd_chat(self, event: AstrMessageEvent):
        """跟 NPC 自由聊天（涨好感）"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        arg = self._arg(event, "搭讪", "私聊", "聊天", "撩")
        if not arg or " " not in arg.strip() and len(arg) < 3:
            body = "用法：搭讪 温软 今天练舞了吗\n（目前只能搭讪「明星」里的 NPC）"
            if head:
                body = f"{head}\n\n{body}"
            yield event.plain_result(body)
            event.stop_event()
            return

        parts = arg.split(None, 1)
        name = self._pick_person(parts[0])
        msg = parts[1].strip() if len(parts) > 1 else ""
        target = gsocial.resolve_target(store, gid, name, uid) if name else None
        if not target:
            yield event.plain_result(f"找不到「{name}」这个人，用「明星」看看名单。")
            event.stop_event()
            return
        if not target.get("is_npc"):
            yield event.plain_result("真人之间还是用「送礼」和「表白」吧，我不好替你聊天～")
            event.stop_event()
            return
        if not msg:
            yield event.plain_result("想跟他们说什么？补一句，例如「搭讪 温软 今天练舞了吗」。")
            event.stop_event()
            return

        limit = self._i("chat_daily_limit", 3)
        key = f"搭讪:{target['qq_id']}"
        if store.count_activity(gid, uid, key) >= limit:
            yield event.plain_result(f"今天已经跟 {target['name']} 聊了 {limit} 次，留点话明天说吧。")
            event.stop_event()
            return

        rel = store.get_relation(gid, uid, target["qq_id"])
        scene = f"{me['name']} 对你说：「{msg}」（你们目前好感 {rel['affection']}/100）"
        if rel.get("couple"):
            scene += "，你们正在交往。"
        reply = FALLBACK_CHAT_REPLY
        if self.ai is not None:
            reply = await gnpc.npc_line(self.ai, target, scene)

        store.mark_activity(gid, uid, key)
        delta = random.randint(2, 6) + (2 if rel.get("couple") else 0)
        rel = store.add_affection(gid, uid, target["qq_id"], delta)

        body = (
            f"💬 你：{msg}\n"
            f"{target['name']}：{reply}\n"
            f"  好感 +{delta}｜{gsocial.affection_bar(rel['affection'])}（{gsocial.affection_word(rel['affection'])}）"
        )
        body += await self._flavor(
            me,
            f"跟{target['name']}聊了几句",
            f"好感 +{delta}",
            delta,
            umo=event.unified_msg_origin,
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("放弃", alias={"弃演", "退出剧情", "不演了"})
    async def cmd_giveup(self, event: AstrMessageEvent):
        """放弃进行中的通告/采访"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        had = False
        for kind in ("drama", "interview"):
            if store.get_story(gid, uid, kind):
                store.del_story(gid, uid, kind)
                had = True
        yield event.plain_result(
            "已经退出了手上的剧情。" if had else "你现在没有进行中的剧情。"
        )
        event.stop_event()

    @filter.command("月报", alias={"星途月报", "回顾", "小结"})
    async def cmd_report(self, event: AstrMessageEvent):
        """让 AI 写一段你的星途月报"""
        if not self._gate(event):
            return
        gid, uid, me, _ = self._player(event)  # type: ignore[misc]
        store = self.store
        assert store is not None
        head = self._daily(gid)

        cur, nxt = get_tier(total_power(me))
        all_stars = store.ranking(gid, "total", 99)
        rank = next((i for i, s in enumerate(all_stars, 1) if s["qq_id"] == uid), 0)
        partner = store.partner_of(gid, uid)
        p_name = ""
        if partner:
            p = store.get_star(gid, partner)
            p_name = p["name"] if p else ""
        evs = store.events_today(gid, 20)

        stats = (
            f"段位{cur[1]}，综合实力{total_power(me)}，群内排名{rank}/{len(all_stars)}，"
            f"人气{pop_of(me)}（{pop_title(pop_of(me))}），"
            f"战绩{me['wins']}胜{me['losses']}负{me['draws']}平，"
            f"四项：{ '、'.join(f'{ATTRS[k]}{int(me[k])}' for k in ATTR_KEYS)}，"
            f"今日群内事件{len(evs)}条"
            + (f"，和{p_name}在交往" if p_name else "，目前单身")
        )

        text = ""
        if self.ai is not None:
            text = await self.ai.monthly_report(me["name"], stats)
        if not text:
            text = (
                f"这一个月你把大部分时间耗在了练功房。{cur[1]} 的身份还不稳，"
                "但你至少没在原地打转——娱乐圈最不缺的就是努力的人，缺的是被人记住的那一个。"
            )
        body = (
            f"📖 {me['name']} 的星途月报\n"
            "──────────────\n"
            f"{text}\n"
            "──────────────\n"
            f"  {cur[1]}｜综合 {total_power(me)}｜人气 {pop_of(me)}（{pop_title(pop_of(me))}）｜群内第 {rank} 名"
            + (f"｜恋人 {p_name}" if p_name else "")
        )
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    # ---------------- 信息 ----------------
    @filter.command("明星", alias={"NPC", "npc", "艺人"})
    async def cmd_npcs(self, event: AstrMessageEvent):
        """本群的系统 NPC 名单"""
        if not self._gate(event):
            return
        gid = str(event.get_group_id())
        store = self.store
        assert store is not None
        head = self._daily(gid)
        if not self._b("npc_enabled", True):
            yield event.plain_result("这个群没开 NPC，去「排行」跟真人比吧～")
            event.stop_event()
            return
        npcs = store.npcs(gid)
        rows = ["🎭 本群的虚拟艺人（可以「比拼」也可以「表白」）："]
        for s in sorted(npcs, key=lambda x: total_power(x), reverse=True):
            cur, _ = get_tier(total_power(s))
            persona = next((n for n in NPC_ROSTER if n["key"] == s["npc_key"]), {})
            rows.append(f"  · {s['name']}｜{cur[1]}｜{total_power(s)}｜{persona.get('tag', '')}")
        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("事件", alias={"今日事件", "热搜", "新闻"})
    async def cmd_events(self, event: AstrMessageEvent):
        """今天的突发事件与热搜"""
        if not self._gate(event):
            return
        gid = str(event.get_group_id())
        store = self.store
        assert store is not None
        head = self._daily(gid)
        evs = store.events_today(gid, 10)
        rows = ["📰 今日事件："] if evs else ["📰 今天还没出什么事。"]
        for e in evs:
            rows.append(f"  · [{e['kind']}] {e['text']}")
        pool = store.pool_size(gid)
        rows.append(f"  （待触发事件池：{pool} 条）")
        body = "\n".join(rows)
        if head:
            body = f"{head}\n\n{body}"
        yield event.plain_result(body)
        event.stop_event()

    @filter.command("帮助", alias={"菜单", "玩法", "help", "星途帮助"})
    async def cmd_help(self, event: AstrMessageEvent):
        """完整玩法手册（默认发一张图，发「帮助 文字」看纯文本版）"""
        if not self._gate(event):
            return
        arg = self._arg(event, "帮助", "菜单", "玩法", "星途帮助", "help")
        want_text = any(k in arg for k in ("文字", "文本", "版", "text"))

        # 默认发表格图，群里不会刷屏
        if not want_text and self._b("help_image", True) and HELP_IMG.exists():
            try:
                yield event.image_result(str(HELP_IMG))
                event.stop_event()
                return
            except Exception as e:
                logger.warning(f"[star_game] 帮助图发送失败，改用文字：{e}")

        tier_rows = "｜".join(f"{th} {nm.split()[-1]}" for th, nm in TIERS)
        draw_cd = self._i("draw_cooldown_min", 8)
        pk_cd = self._i("pk_cooldown_min", 3)
        post_cap = self._i("post_daily_limit", 3)
        chat_cap = self._i("chat_daily_limit", 3)
        ev_cap = self._i("event_daily_cap", 8)
        msg = (
            "🎬《娱乐圈星途》玩法手册\n"
            "══════════════\n"
            "【一、你在玩什么】\n"
            "这个群是一家造星工厂，你就是里面的艺人。\n"
            "练功涨实力、营业涨人气，最后在排行榜上抢位置。\n"
            "\n"
            "【二、你有两样身家】\n"
            "· 实力：唱跳 / 创作 / 舞蹈 / 声乐，四项之和＝综合实力\n"
            "· 人气：不看实力只看热度。作用有三个——\n"
            "    1) 比拼时给加成（最高 +15%）\n"
            "    2) 人气越高越容易被事件盯上（好事坏事都会多）\n"
            f"    3) 每天不营业会掉 {POP_DECAY_PERCENT}%（低于 {POP_DECAY_KEEP} 不掉）\n"
            "\n"
            "【三、段位（只看综合实力）】\n"
            f"  {tier_rows}\n"
            "\n"
            "【四、每天的练功】\n"
            "· 签到        四项各 +1~3，随机一项再 +3~10，人气 +1~3\n"
            "· 抽签        随机 0~100 注入属性；可在前面加「欧皇 / 反向 / 单项」\n"
            f"              冷却 {draw_cd} 分钟\n"
            "· 参加 选秀   每天每项限一次：\n"
            "              选秀(唱跳) 写歌(创作) 斗舞(舞蹈) 开嗓(声乐) 盛典(四项)\n"
            "\n"
            "【五、对抗】\n"
            "· 比拼 @某人 [单项]   不写单项＝比综合实力\n"
            "· 比拼               不写对手＝随机挑一个实力接近的 NPC\n"
            "  双方各带 0.9~1.1 的运气系数，人气再给加成\n"
            "  胜者四项 +8~18、人气 +2~5；败者 +1~6（安慰奖，不会白打）\n"
            f"  冷却 {pk_cd} 分钟；被 NPC 主动约战不占你的冷却\n"
            "\n"
            "【六、AI 剧情（模型现场写的）】\n"
            "· 接戏 →「选 A / B / C」   三幕互动剧本，\n"
            "                           每幕三个选择，杀青按表现分给属性和人气\n"
            "· 采访 →「回答 你的话」    记者现场提问，AI 评判你的回答\n"
            "                           （表现分 0~10，还给你一条见报标题）\n"
            "· 发博 内容               AI 生成评论区（粉丝/路人/黑子/营销号），\n"
            f"                           舆论好坏直接改人气，每天 {post_cap} 条\n"
            "· 搭讪 NPC 一句话          按人设回你，涨好感\n"
            f"                           每个 NPC 每天 {chat_cap} 次\n"
            "· 月报                    AI 根据你的数据写一段星途回顾\n"
            "· 回应 A / 回应 你的话   NPC 突然找你搭话时，选一个选项或者自己写一句\n"
            "· 放弃                    中断进行中的通告或采访\n"
            "\n"
            "【七、恋爱与结婚】\n"
            "· 商店             礼品店：奶茶 30 / 鲜花 60 / 手写情书 90 / VIP票 180 /\n"
            "                   限量项链 300 / 求婚戒指 520（星币）\n"
            "· 买 礼物 数量     从商店买进背包，送礼必须有货\n"
            "· 背包             看自己买了什么、还剩多少\n"
            "· 送礼 名字 礼物    消耗背包里的一件，加好感（每天每种有限量）\n"
            "· 表白 名字         NPC 好感够了就答应；真人要对方回「答应」\n"
            "· 求婚 名字         需要一枚求婚戒指；NPC 好感 ≥ 90 直接答应，\n"
            "                   真人会收到求婚、等他回「答应」或「拒绝」\n"
            "· 答应 / 拒绝       处理别人的表白或求婚\n"
            "· 分手 / 离婚       情侣分手好感 -30；夫妻离婚好感 -20，戒指不退\n"
            "· 情侣             看本群 CP 榜\n"
            "  交往后：签到双方四项各 +2；结婚后签到加成更高\n"
            "\n"
            "【八、金钱】\n"
            f"· 起始 {COIN_START} 星币。赚钱：签到 +8、活动演出费 +12、发博 +6、\n"
            f"  比拼胜 +10、采访 +{INTERVIEW_FEE}、接戏片酬 {DRAMA_BASE_FEE}+表现分×1.2、\n"
            "  邀约 +25~45、助理日结、每天热搜榜\n"
            f"· 花钱：练功场地费 {ACTIVITY_COST}、买礼物、雇助理（300/900/2200）、\n"
            f"  应援 {FAN_CHEER_COST}\n"
            "\n"
            "【九、随机事件】\n"
            "签到/抽签/活动后有概率触发 AI 事件：爆红、绯闻、翻车、塌房、资源、综艺…\n"
            f"真的会改属性和人气，每群每天最多 {ev_cap} 条。\n"
            "发「事件」看今天出过什么。\n"
            "\n"
            "【十、经营与邀约】\n"
            "· 事务所            看星币、助理等级、下一级要多少钱\n"
            "· 雇助理            花星币请助理，每天自动帮你接一个通告（分 3 级）\n"
            "· 粉丝团            粉丝 = 人气 × 37 ＋ 连签 × 20\n"
            f"· 应援              花 {FAN_CHEER_COST} 星币打投，每天一次，人气 +{FAN_CHEER_POP[0]}~{FAN_CHEER_POP[1]}\n"
            "· 热搜              本群人气 Top5；自己在前 3 每小时首次看榜加人气\n"
            "· 考勤              本月签到/活动/胜场，每月 1 号按这个发年终奖\n"
            "· 接邀 / 推辞       NPC 发来邀约时用：接下得星币、属性、好感和人气；\n"
            f"                    推辞掉好感。邀约 {INVITE_TTL_MIN} 分钟内有效\n"
            "  星币怎么来：签到 +8、活动演出费 +12（要扣 10 场地费）、发博 +6、\n"
            "  比拼胜 +10、采访 +25、接戏按表现分给片酬、邀约 +25~45\n"
            "\n"
            "【十一、查看类】\n"
            "· 属性              现场画一张艺人卡（段位进度/四项/人气/星币/背包/成就/\n"
            "                   连签/今日待办/最近动态/伴侣）；加「文字」出文字版\n"
            "· 成就              成就墙（13 个，达成自动播报）\n"
            "· 排行              综合榜｜排行 唱跳｜排行 人气｜排行 段位\n"
            "· 明星              NPC 名单（可以挑战、可以表白）\n"
            "· 改名 新艺名 / 运势\n"
            "\n"
            "【十二、群设置】\n"
            "· 关AI / 关掉ai回应   这个群不再让大模型接话，只留游戏\n"
            "· 开AI                恢复聊天\n"
            "· AI状态              看现在是开还是关\n"
            "· 防封号              插件对发送做了四道保护：\n"
            f"                      每分钟最多 {self._i('guard_per_min', 12)} 条、同内容 {self._i('guard_dedupe_sec', 3)} 秒内去重、\n"
            "                      超长自动截断、链接和长数字替换掉\n"
            "\n"
            "【小贴士】\n"
            "· 群里要 @机器人，或者用 / 开头\n"
            "· 人气是双刃剑：越红越容易被黑，翻车也掉得更响\n"
            "· 连签 3 / 7 / 14 / 30 天各有一份连签奖励，断一天就从头数\n"
            "· 新人先打「温软」「白鹤」，别一上来找沈砚\n"
            "· 出结果后冒出的那行 💬 是 AI 随口点评，不当真也不影响数值\n"
            "· NPC 也会被事件波及，那种标题写「圈内动静」，只算在 NPC 身上\n"
            "· 有 NPC 突然 @ 你搭话，15 分钟内回「回应 A」或「回应 你想说的话」，好感涨得快\n"
            "· 回应得好（好感 +4 以上），NPC 第二天会主动再提起这事，还会顺手给你点资源\n"
            "· 礼物现在要花钱：先在「商店」买，再去「送礼」；求婚戒指 520 星币，\n"
            "  攒够钱、好感刷到 90 再求婚，成功率最高\n"
            "· 每天第一次签到会自动结算：助理通告、上月考勤、以及前一天搭话的后续\n"
            "· 在拍戏时发别的指令不会打断剧情，30 分钟不作答才作废"
            "\n"
            "（这是文字版；群里发「帮助」默认发一张图）"
        )
        yield event.plain_result(msg)
        event.stop_event()
