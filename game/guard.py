"""发送守门员：控频、去重、截断、抹链接，降低 QQ 风控概率。

QQ 侧封号/禁言通常来自这几类行为，这里逐一压住：
- 单位时间发太多条      → 每群每分钟配额 + 最小间隔 + 抖动
- 同一条内容反复刷       → 短窗口内相同文本直接不发
- 消息太长/带链接        → 截断、URL 换成 [链接]、长数字串换成 [数字]
- 敏感词               → 可配置替换成 *
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Dict, List, Tuple

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
LONG_NUM_RE = re.compile(r"\d{11,}")
SPACE_RE = re.compile(r"\s+")


class SendGuard:
    def __init__(
        self,
        *,
        per_min: int = 12,
        min_interval: float = 1.2,
        jitter: Tuple[float, float] = (0.2, 0.8),
        max_len: int = 1200,
        dedupe_sec: float = 3.0,
        words: Tuple[str, ...] = (),
    ) -> None:
        self.per_min = max(1, int(per_min))
        self.min_interval = max(0.0, float(min_interval))
        self.jitter = jitter if jitter else (0.0, 0.0)
        self.max_len = max(200, int(max_len))
        self.dedupe_sec = max(0.0, float(dedupe_sec))
        self.words = tuple(w for w in words if w)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last: Dict[str, float] = {}
        self._win: Dict[str, List[float]] = {}
        self._recent: Dict[str, Tuple[str, float]] = {}

    # ---------------- 文本处理 ----------------
    def prepare(self, text: str) -> str:
        """抹掉容易被平台判定为营销/引流的内容，并做长度保护。"""
        text = text or ""
        if not text:
            return text
        text = URL_RE.sub("[链接]", text)
        text = LONG_NUM_RE.sub("[数字]", text)
        for w in self.words:
            if w in text:
                text = text.replace(w, "*" * len(w))
        if len(text) > self.max_len:
            cut = text[: self.max_len]
            nl = cut.rfind("\n")
            if nl > self.max_len * 0.6:
                cut = cut[:nl]
            text = cut + "\n……（太长截断了）"
        return text

    def is_duplicate(self, gid: str, text: str) -> bool:
        """同群短时间发一模一样的文本 → 判重（这是最容易被判刷屏的行为）。"""
        if self.dedupe_sec <= 0 or not text:
            return False
        now = time.monotonic()
        prev, ts = self._recent.get(gid, ("", 0.0))
        if prev == text and now - ts < self.dedupe_sec:
            return True
        self._recent[gid] = (text, now)
        return False

    # ---------------- 节流 ----------------
    async def pace(self, gid: str) -> float:
        """按配额和最小间隔排队，返回实际等待秒数。"""
        lock = self._locks.setdefault(gid, asyncio.Lock())
        waited = 0.0
        async with lock:
            now = time.monotonic()
            window = [t for t in self._win.get(gid, []) if now - t < 60.0]
            if len(window) >= self.per_min:
                wait = 60.0 - (now - window[0]) + 0.5
                # 最多等 5 秒：宁可稍微超一点，也不要把回复卡成静默
                wait = min(wait, 5.0)
                await asyncio.sleep(wait)
                waited += wait
                now = time.monotonic()
                window = [t for t in window if now - t < 60.0]

            gap = self._last.get(gid, 0.0) + self.min_interval - now
            if gap > 0:
                await asyncio.sleep(gap)
                waited += gap

            jitter = random.uniform(*self.jitter)
            if jitter > 0:
                await asyncio.sleep(jitter)
                waited += jitter

            stamp = time.monotonic()
            self._last[gid] = stamp
            window.append(stamp)
            self._win[gid] = window
        return waited


def norm_text(text: str) -> str:
    """归一化：去空格、转小写，用来做自然语言开关匹配。"""
    return SPACE_RE.sub("", text or "").lower()
