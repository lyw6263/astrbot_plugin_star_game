"""AI 能力封装：事件库生成、今日热搜、NPC 台词。

设计要点：
- 全部 async + 超时保护，模型挂了游戏照样能玩（有手写兜底事件）
- 事件是「结构化 JSON」而不是自由文本，属性影响必须能解析，避免模型把数值写飞
- 事件提前生成进池子里，玩家触发时直接抽，不阻塞回复
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from typing import List, Optional

from . import content as gcontent
from .const import (
    ATTR_KEYS,
    EVENT_KINDS,
    FALLBACK_EVENTS,
    TALK_OPEN_FALLBACK,
    TALK_OPTIONS_FALLBACK,
    TALK_REPLY_FALLBACK,
)

# 模型可以改动的数值：四项技能 + 人气
EFFECT_KEYS = set(ATTR_KEYS) | {"renqi"}
RENQI_LO, RENQI_HI = -18, 18

EVENT_STYLES = [
    "营销号爆料体：先说传闻，再补一句「知情人称」",
    "狗仔跟拍体：时间地点加一个具体动作细节",
    "工作室声明体：先撇清，再留个尾巴",
    "路人偶遇体：第一人称偶遇，带点主观吐槽",
    "榜单数据体：用排名、销量、播放量说话",
    "品牌官宣体：代言/合作/站台，商业味重一点",
    "综艺花絮体：后台、彩排、剪辑段落里的翻车",
    "粉丝小作文体：情绪浓，带点控评腔",
]

NEWS_STYLES = [
    "四条分别写成：爆料、词条+点评、粉丝控评、路人目击",
    "四条都用「#话题# + 一句吐槽」的热搜词条格式",
    "四条里有两条是夸奖，两条是阴阳怪气",
    "四条都从「工作人员爆料」的角度写",
    "四条里有一条明显是假瓜，写得越像真的越好",
    "四条各自带一个具体场景：机场、片场、后台、发布会",
]

EVENT_SYSTEM = (
    "你是一款 QQ 群『娱乐圈明星养成』文字游戏的事件编辑，负责写娱乐圈八卦事件。"
    "文字要短、有戏、像营销号，但绝对不能涉及真实艺人、真实品牌、政治或色情内容。"
)

EVENT_PROMPT = """请生成 {n} 条娱乐圈突发事件，供游戏随机抽取。

只输出一个 JSON 数组，不要解释、不要 markdown 代码块。每条格式：
{{"kind":"类型","title":"标题","text":"正文","effects":{{"changtiao":0}},"target":"one"}}

规则：
1. kind 只能取：{kinds}；请尽量分散，不要连着好几条都是同一个 kind，一轮里至少用到 4 种不同的 kind（代言/影视/音乐/时尚/应援 这类是好资源，争议/私生/黑料/解约 这类是坏消息）
2. title 不超过 14 个字；text 40~90 个汉字，第三人称，有画面感
3. 事件主角必须写成占位符 {{name}}，系统会替换成玩家艺名，例如「{{name}}在后台被拍到低头刷手机」
4. text 和 title 里除了 {{name}} 不允许出现任何人名：不写其他 NPC、不写真实艺人、不编新名字
5. effects 的 key 只能是 changtiao(唱跳)、chuangzuo(创作)、wudao(舞蹈)、shengyue(声乐)、renqi(人气)，
   取值是 -8 到 +8 的整数（renqi 可以 -18 到 +18），最多写 3 个 key；可以只写一个
6. 同一条事件的所有数值方向必须一致：爆红/资源/综艺/恋情只加不减，绯闻/黑热搜/塌房/翻车只减不加。
   不许出现「舞蹈-2、唱跳+3」这种一半加一半减的写法
7. 正文必须交代每个数值的原因：写清楚是因为哪件事才加/减了哪一项，
   玩家读完能对上账，不许只写「有点东西」这种不解释的句子
8. 娱乐圈里热搜本身就是流量：意外走红、被提名、上综艺要加 renqi；
   翻车、被黑、塌房要减 renqi。别让每条都只改技能属性
9. target: "one" 表示只影响一个人，"all" 表示影响全群
10. {avoid}
11. 文风要杂：不要每条都写成「被拍到/被爆料」；标题也别全是「XX 被曝…」，
    按下面这个方向写本轮：{style}
"""

NEWS_SYSTEM = "你是一个娱乐八卦号的运营，写短句热搜，不涉及真实艺人。"

DRAMA_SYSTEM = (
    "你在为一款 QQ 群娱乐圈文字游戏写互动剧本。"
    "风格是内娱职场+八卦，有冲突有笑点，但绝不涉及真实艺人、真实品牌、政治和色情。"
)

DRAMA_SCENE_PROMPT = """剧本《{title}》，玩家饰演「{role}」。前情：{history}

请写第 {step} 幕：60~100 字场景描写（第二人称，有具体动作和对话），然后给玩家 3 个选择。
本幕文风：{style}
选择要具体、各有代价，不要写「继续」「离开」这种空话。

只输出 JSON：{{"scene":"...","options":["...","...","..."]}}"""

DRAMA_END_PROMPT = """剧本《{title}》杀青了。玩家在三幕里的选择：
{choices}

请写 80~120 字结局旁白（第二人称），并根据选择给表现分和属性奖励。
收尾方式：{style}
只输出 JSON：{{"ending":"...","score":0,"effects":{{"changtiao":0}}}}
score 是 0~100 的整数；effects 的 key 只能是 changtiao/chuangzuo/wudao/shengyue/renqi，
最多三个，取值 -5 到 8（renqi 是 -15 到 15）。"""

INTERVIEW_Q_PROMPT = """你是娱乐记者。请向艺人「{name}」提一个刁钻但有分寸的问题，
涉及作品、绯闻、路透、争议都行，20~40 字。
只输出问题本身，不要加「问：」「记者：」这类前缀。
提问风格：{style}"""

JUDGE_PROMPT = """记者问：「{q}」
艺人回答：「{a}」

请评判这个回答的效果，写出记者或网友的反应，并给一个见报标题。
只输出 JSON：{{"comment":"...","headline":"...","score":0,"effects":{{"shengyue":0}}}}
本轮反应走向：{style}
comment 30 字内，headline 14 字内，score 0~10；effects 最多三个 key，取值 -3 到 4（renqi 可用 -10 到 10）。"""

POST_PROMPT = """艺人「{name}」（{tier}，综合实力 {power}）刚发了一条微博：
「{content}」

请模拟评论区：粉丝、路人、黑子、营销号各一条（每条 12~25 字，带点口吻差异），并判断舆论倾向。
只输出 JSON：{{"comments":["...","...","...","..."],"sentiment":"positive|neutral|negative","effects":{{"changtiao":0}}}}
effects 最多三个 key，取值 -4 到 4（renqi 可用 -12 到 12）。
评论区氛围：{style}"""

MONTHLY_PROMPT = """你是娱乐圈记者，给艺人「{name}」写一段本月的「星途月报」旁白。
要求：第二人称，80~120 字，有画面感，带一点调侃但不要刻薄，不要出现具体真实品牌。
数据：{stats}
只输出正文，不要标题。
调性：{style}"""

FALLBACK_QUESTIONS = [
    "有人说你是靠资源上位的，你怎么看？",
    "最近有传闻说你在剧组耍大牌，是真的吗？",
    "你和某位同行的关系，方便透露一下吗？",
    "有网友说你的作品千篇一律，你想回应吗？",
    "如果这次没拿奖，你会怎么面对粉丝？",
] + list(gcontent.MORE_QUESTIONS)


NEWS_PROMPT = """群里的虚拟艺人：{npcs}
玩家艺人：{players}

请写 4 条今天的「娱乐圈热搜」短句，每条 12~28 字，带一点八卦口吻，
必须至少提到一位上面的虚拟艺人，可以用「疑似」「据传」这种营销号口吻。
本轮排版要求：{style}
只输出 4 行纯文本，不要编号、不要解释。"""

FLAVOR_PROMPT = """群里艺人「{name}」刚做完一件事。
事情：{action}
结果：{outcome}

请用一句话点评他。要求：
1. 第二人称，12~26 个字，像群聊里随口说的；
2. 可以损、可以夸，但别骂人、别提真实品牌和真人；
3. 不要复述具体数字，不要加引号、不要写「他说」这类旁白；
4. 口吻偏：{style}
5. 只输出这一句话。"""

TALK_PROMPT = """你是娱乐圈里的系统 NPC。现在要写一段「NPC 突然找玩家搭话」的现场。

NPC：{npc}（{tag}；性格：{persona}）
玩家：{player}（{tier}，综合实力 {power}）
场合：{scene}

请写：
1. line：NPC 突然开口说的话，第二人称视角，25~55 字，带一个具体动作，符合他的性格；
   不要写「他心想」「气氛变得微妙」这种旁白式总结，直接说出口的话 + 动作。
2. options：给玩家的 3 个回复选项，每个 6~14 字，风格要区分开（一个硬气、一个圆滑、一个走心）。

只输出 JSON：{{"line":"...","options":["...","...","..."]}}"""

TALK_JUDGE_PROMPT = """NPC「{npc}」（性格：{persona}）刚对玩家「{player}」说：
「{line}」

玩家{how}：{choice}

请写 NPC 的反应，并给这次互动的结果。
1. reply：NPC 的反应，第二人称叙事，25~55 字，有表情或动作，符合性格；
2. favor：这次互动让 NPC 对你的好感变化，-6 到 8 的整数（把话说死、冒犯=-，接得住、有分寸=+）；
3. renqi：人气变化，-6 到 6 的整数；
4. effects：最多两个属性加成，key 只能是 changtiao/chuangzuo/wudao/shengyue，取值 0 到 3；
5. mood：6 个字以内的氛围词，例如「气氛升温」「有点尴尬」「被记住了」。

只输出 JSON：{{"reply":"...","favor":0,"renqi":0,"effects":{{}},"mood":"..."}}"""



class AI:
    def __init__(
        self,
        context,
        timeout: float = 15.0,
        enabled: bool = True,
        daily_budget: int = 0,
    ) -> None:
        self.context = context
        self.timeout = timeout
        self.enabled = enabled
        self._lock = asyncio.Lock()
        # 每日 AI 调用上限（0＝不限）。超了就直接返回空串走手写兜底，游戏照样能玩。
        self.daily_budget = max(0, int(daily_budget))
        self._budget_day = ""
        self._budget_used = 0

    def _budget_ok(self) -> bool:
        if self.daily_budget <= 0:
            return True
        day = time.strftime("%Y-%m-%d")
        if day != self._budget_day:
            self._budget_day = day
            self._budget_used = 0
        if self._budget_used >= self.daily_budget:
            return False
        self._budget_used += 1
        return True

    async def _ask(self, prompt: str, system: str, timeout: Optional[float] = None) -> str:
        if not self.enabled:
            return ""
        if not self._budget_ok():
            return ""
        try:
            prov = await self.context.get_using_provider_async()
        except Exception:
            prov = None
        if prov is None:
            return ""
        try:
            resp = await asyncio.wait_for(
                prov.text_chat(prompt=prompt, system_prompt=system),
                timeout=timeout or self.timeout,
            )
            return (resp.completion_text or "").strip()
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

    # ---------------- 事件库 ----------------
    async def generate_events(
        self, n: int = 4, avoid_titles: Optional[List[str]] = None
    ) -> List[dict]:
        avoid = "、".join((avoid_titles or [])[:8]) or "无"
        prompt = EVENT_PROMPT.format(
            n=n + 2,
            kinds="、".join(EVENT_KINDS),
            avoid=f"这几条标题已经用过，换新的：{avoid}",
            style=random.choice(EVENT_STYLES),
        )
        raw = await self._ask(prompt, EVENT_SYSTEM)
        events = parse_events(raw, limit=n + 2)
        # 主角必须是占位符，否则「事件写的是别人、扣的是玩家」——直接丢掉重抽
        events = [e for e in events if "{name}" in str(e.get("text") or "")]
        return events[:n]

    # ---------------- 今日热搜 ----------------
    async def generate_news(self, npc_names: List[str], player_names: List[str]) -> List[str]:
        prompt = NEWS_PROMPT.format(
            npcs="、".join(npc_names) or "无",
            players="、".join(player_names) or "无",
            style=random.choice(NEWS_STYLES),
        )
        raw = await self._ask(prompt, NEWS_SYSTEM, timeout=min(self.timeout, 12.0))
        lines = [ln.strip(" -·•*#") for ln in raw.splitlines() if ln.strip()]
        out = []
        for ln in lines:
            ln = re.sub(r"^\d+[.、)]\s*", "", ln)
            if 6 <= len(ln) <= 60:
                out.append(ln)
        return out[:4]

    # ---------------- NPC 台词 ----------------
    async def generate_line(self, persona: str, scene: str, fallback: str) -> str:
        prompt = (
            f"你正在扮演虚拟明星。人设：{persona}\n"
            f"场景：{scene}\n"
            "说一句符合人设的反应，不超过 20 个字，不要加引号、不要旁白。"
        )
        text = await self._ask(prompt, "你在扮演 QQ 群里的虚拟明星，只输出一句台词。", timeout=8.0)
        text = text.strip().strip("「」“”\"'")
        if not text or len(text) > 40:
            return fallback
        return text

    # ---------------- 结果点评（对当事人说一句） ----------------
    async def flavor_line(
        self,
        name: str,
        action: str,
        outcome: str,
        fallback: str,
        persona: str = "",
        persona_prompt: str = "",
    ) -> str:
        """按这次结果，用机器人自己的人格对当事人随口说一句；失败用兜底话术。

        persona_prompt 是群里那只机器人平时的完整人设（AstrBot 人格卡），
        有它就用它说话，这样点评和群里其他聊天是同一个「人」。
        """
        if not self.enabled:
            return fallback
        base = (persona_prompt or "").strip()
        if base:
            system = (
                base[:600]
                + "\n\n【本次任务】你刚看到群友在玩明星养成游戏，"
                + "只用一句话点评这次结果，12~26 个字，口语，"
                + "不要旁白、不要加引号、不要复述数字。"
            )
        else:
            who = persona or "一个嘴碎但有分寸、很懂娱乐圈的群友"
            system = f"你在 QQ 群里扮演{who}。只输出一句话，不要旁白、不要加引号。"
        prompt = FLAVOR_PROMPT.format(
            name=name,
            action=action,
            outcome=outcome or "无",
            style=random.choice(gcontent.FLAVOR_TONES),
        )
        text = await self._ask(prompt, system, timeout=min(self.timeout, 6.0))
        text = (text or "").strip()
        if not text:
            return fallback
        text = text.splitlines()[0].strip().strip("「」“”\"'`-•· ")
        if not text or len(text) > 40:
            return fallback
        return text

    # ---------------- NPC 主动搭话 ----------------
    async def npc_talk_open(
        self, npc: dict, player_name: str, tier: str, power: int, scene: str = ""
    ) -> dict:
        """NPC 突然找玩家搭话：返回 {"line", "options"}，模型挂了用兜底。"""
        name = npc.get("name") or "某位艺人"
        fallback = {
            "line": random.choice(TALK_OPEN_FALLBACK).format(npc=name),
            "options": list(random.choice(TALK_OPTIONS_FALLBACK)),
        }
        if not self.enabled:
            return fallback
        system = (
            f"你在写娱乐圈群像剧情。NPC「{name}」的性格是"
            f"{npc.get('persona') or '有点拽但讲道理'}，说话短、有情绪、不解释自己。"
        )
        prompt = TALK_PROMPT.format(
            npc=name,
            tag=npc.get("tag") or "艺人",
            persona=npc.get("persona") or "有点拽但讲道理",
            player=player_name,
            tier=tier,
            power=power,
            scene=scene or random.choice(gcontent.TALK_SCENES),
        )
        raw = await self._ask(prompt, system, timeout=min(self.timeout, 12.0))
        data = _load_obj(raw)
        if not data:
            return fallback
        line = str(data.get("line") or "").strip().strip("「」“”\"'")
        opts = data.get("options")
        if not isinstance(opts, list):
            return fallback
        options = [str(o).strip().strip("「」“”\"'")[:24] for o in opts if str(o).strip()]
        if len(line) < 8 or len(line) > 120 or len(options) < 2:
            return fallback
        while len(options) < 3:
            options.append(random.choice(random.choice(TALK_OPTIONS_FALLBACK)))
        return {"line": line, "options": options[:3]}

    async def npc_talk_judge(
        self,
        npc: dict,
        player_name: str,
        line: str,
        choice: str,
        free_text: str = "",
    ) -> dict:
        """判定玩家对 NPC 搭话的回应：返回 {"reply","favor","renqi","effects","mood"}。"""
        name = npc.get("name") or "某位艺人"
        fallback = {
            "reply": random.choice(TALK_REPLY_FALLBACK).format(npc=name),
            "favor": random.randint(1, 3),
            "renqi": random.randint(0, 2),
            "effects": {},
            "mood": "气氛微妙",
        }
        if not self.enabled:
            return fallback
        how = "直接说" if free_text else "选择了"
        said = f"「{free_text}」" if free_text else f"「{choice}」"
        system = (
            f"你在写娱乐圈群像剧情。NPC「{name}」的性格是"
            f"{npc.get('persona') or '有点拽但讲道理'}，反应要短、要像人，不要写成旁白解说。"
        )
        prompt = TALK_JUDGE_PROMPT.format(
            npc=name,
            persona=npc.get("persona") or "有点拽但讲道理",
            player=player_name,
            line=line or "……",
            how=how,
            choice=said,
        )
        raw = await self._ask(prompt, system, timeout=min(self.timeout, 12.0))
        data = _load_obj(raw)
        if not data:
            return fallback
        reply = str(data.get("reply") or "").strip().strip("「」“”\"'")
        if len(reply) < 6 or len(reply) > 120:
            reply = fallback["reply"]
        try:
            favor = max(-6, min(8, int(round(float(data.get("favor", 1))))))
        except (TypeError, ValueError):
            favor = fallback["favor"]
        try:
            renqi = max(-6, min(6, int(round(float(data.get("renqi", 0))))))
        except (TypeError, ValueError):
            renqi = 0
        mood = str(data.get("mood") or "").strip()[:8] or fallback["mood"]
        return {
            "reply": reply,
            "favor": favor,
            "renqi": renqi,
            "effects": clamp_effects(data.get("effects"), 0, 3, max_keys=2),
            "mood": mood,
        }


    # ---------------- 通告剧本（多幕互动） ----------------
    async def drama_scene(
        self, title: str, role: str, step: int, history: str
    ) -> Optional[dict]:
        prompt = DRAMA_SCENE_PROMPT.format(
            title=title,
            role=role,
            step=step,
            history=history or "（故事刚开始）",
            style=random.choice(gcontent.SCENE_STYLES),
        )
        raw = await self._ask(prompt, DRAMA_SYSTEM, timeout=min(self.timeout, 18.0))
        return parse_drama_scene(raw, expect_options=3)

    async def drama_end(self, title: str, choices: str) -> Optional[dict]:
        prompt = DRAMA_END_PROMPT.format(
            title=title, choices=choices, style=random.choice(gcontent.SCENE_STYLES)
        )
        raw = await self._ask(prompt, DRAMA_SYSTEM, timeout=min(self.timeout, 18.0))
        return parse_drama_end(raw)

    # ---------------- 采访 ----------------
    async def interview_question(self, name: str) -> str:
        prompt = INTERVIEW_Q_PROMPT.format(
            name=name, style=random.choice(gcontent.INTERVIEW_TONES)
        )
        text = await self._ask(prompt, NEWS_SYSTEM, timeout=12.0)
        text = text.strip().strip("「」“”\"'")
        if not text or len(text) > 80:
            return random.choice(FALLBACK_QUESTIONS)
        return text

    async def judge_answer(self, question: str, answer: str) -> Optional[dict]:
        prompt = JUDGE_PROMPT.format(
            q=question, a=answer[:200], style=random.choice(gcontent.JUDGE_STYLES)
        )
        raw = await self._ask(prompt, NEWS_SYSTEM, timeout=min(self.timeout, 15.0))
        return parse_judge(raw, lo=-3, hi=4, max_score=10)

    # ---------------- 微博 ----------------
    async def judge_post(
        self, name: str, tier: str, power: int, content: str
    ) -> Optional[dict]:
        prompt = POST_PROMPT.format(
            name=name,
            tier=tier,
            power=power,
            content=content[:200],
            style=random.choice(gcontent.POST_STYLES),
        )
        raw = await self._ask(prompt, NEWS_SYSTEM, timeout=min(self.timeout, 15.0))
        return parse_post(raw)

    # ---------------- 月报 ----------------
    async def monthly_report(self, name: str, stats: str) -> str:
        prompt = MONTHLY_PROMPT.format(
            name=name, stats=stats, style=random.choice(gcontent.MONTHLY_TONES)
        )
        text = await self._ask(prompt, NEWS_SYSTEM, timeout=min(self.timeout, 15.0))
        if not text:
            return ""
        return text.strip()[:400]



# ---------------- 解析与校验 ----------------
def _extract_json_array(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    if raw.startswith("{"):
        raw = "[" + raw + "]"
    i, j = raw.find("["), raw.rfind("]")
    if i >= 0 and j > i:
        return raw[i : j + 1]
    return ""


def parse_events(raw: str, limit: int = 4) -> List[dict]:
    if not raw:
        return []
    body = _extract_json_array(raw)
    if not body:
        return []
    try:
        data = json.loads(body)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    out: List[dict] = []
    for item in data:
        ev = _norm_event(item)
        if ev:
            out.append(ev)
        if len(out) >= limit:
            break
    return out


def _norm_event(item) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "").strip()
    title = str(item.get("title") or "").strip()
    if len(text) < 8:
        return None
    if not title:
        title = text[:14]
    kind = str(item.get("kind") or "").strip()
    if kind not in EVENT_KINDS:
        kind = "绯闻"

    eff_in = item.get("effects") or {}
    effects = clamp_effects(eff_in, -10, 10)

    return {
        "kind": kind,
        "title": title[:20],
        "text": text[:200],
        "effects": effects,
        "target": "all" if item.get("target") == "all" else "one",
    }


def fallback_events(n: int = 4) -> List[dict]:
    """模型不可用时的手写事件。"""
    pool = list(FALLBACK_EVENTS)
    random.shuffle(pool)
    return pool[:n]


# ---------------- 通用 JSON 工具 ----------------
def _extract_json_obj(raw: str) -> str:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    i, j = raw.find("{"), raw.rfind("}")
    if i >= 0 and j > i:
        return raw[i : j + 1]
    return ""


def _load_obj(raw: str) -> Optional[dict]:
    body = _extract_json_obj(raw)
    if not body:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def clamp_effects(eff_in, lo: int, hi: int, max_keys: int = 3) -> dict:
    effects = {}
    if not isinstance(eff_in, dict):
        return effects
    for k, v in eff_in.items():
        if k not in EFFECT_KEYS:
            continue
        try:
            iv = int(round(float(v)))
        except (TypeError, ValueError):
            continue
        if k == "renqi":
            iv = max(RENQI_LO, min(RENQI_HI, iv))
        else:
            iv = max(lo, min(hi, iv))
        if iv:
            effects[k] = iv
    if len(effects) > max_keys:
        effects = dict(list(effects.items())[:max_keys])
    return effects


# ---------------- 各玩法的解析 ----------------
def parse_drama_scene(raw: str, expect_options: int = 3) -> Optional[dict]:
    data = _load_obj(raw)
    if not data:
        return None
    scene = str(data.get("scene") or "").strip()
    if len(scene) < 10:
        return None
    opts = data.get("options")
    if not isinstance(opts, list):
        return None
    options = [str(o).strip()[:60] for o in opts if str(o).strip()]
    if len(options) < 2:
        return None
    return {"scene": scene[:300], "options": options[:expect_options]}


def parse_drama_end(raw: str) -> Optional[dict]:
    data = _load_obj(raw)
    if not data:
        return None
    ending = str(data.get("ending") or "").strip()
    if len(ending) < 10:
        return None
    try:
        score = int(round(float(data.get("score", 50))))
    except (TypeError, ValueError):
        score = 50
    return {
        "ending": ending[:400],
        "score": max(0, min(100, score)),
        "effects": clamp_effects(data.get("effects"), -5, 8),
    }


def parse_judge(raw: str, lo: int = -3, hi: int = 4, max_score: int = 10) -> Optional[dict]:
    data = _load_obj(raw)
    if not data:
        return None
    comment = str(data.get("comment") or "").strip()
    headline = str(data.get("headline") or "").strip()
    if not comment and not headline:
        return None
    try:
        score = int(round(float(data.get("score", max_score // 2))))
    except (TypeError, ValueError):
        score = max_score // 2
    return {
        "comment": comment[:60] or "现场安静了两秒。",
        "headline": headline[:20] or "采访现场一句话上热搜",
        "score": max(0, min(max_score, score)),
        "effects": clamp_effects(data.get("effects"), lo, hi),
    }


def parse_post(raw: str) -> Optional[dict]:
    data = _load_obj(raw)
    if not data:
        return None
    comments = data.get("comments")
    if not isinstance(comments, list):
        return None
    rows = [str(c).strip()[:40] for c in comments if str(c).strip()]
    if not rows:
        return None
    sentiment = str(data.get("sentiment") or "neutral").strip()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"
    return {
        "comments": rows[:5],
        "sentiment": sentiment,
        "effects": clamp_effects(data.get("effects"), -4, 4),
    }


def judge_sentiment_by_effects(effects: dict) -> str:
    total = sum(effects.values())
    if total > 0:
        return "positive"
    if total < 0:
        return "negative"
    return "neutral"
