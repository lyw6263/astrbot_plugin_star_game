"""SQLite 数据层：明星（真人 + NPC）、活动、事件池、关系（好感/恋爱）、待办。

所有表都以 group_id 隔离，多群玩不会串档。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .engine import now_iso, today


def pair(a: str, b: str) -> Tuple[str, str]:
    """关系表用无向对，统一成 (小, 大)。"""
    return (a, b) if a < b else (b, a)


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------------- 建表 ----------------
    def init(self) -> None:
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS stars (
                    group_id   TEXT NOT NULL,
                    qq_id      TEXT NOT NULL,
                    name       TEXT NOT NULL,
                    changtiao  INTEGER NOT NULL DEFAULT 10,
                    chuangzuo  INTEGER NOT NULL DEFAULT 10,
                    wudao      INTEGER NOT NULL DEFAULT 10,
                    shengyue   INTEGER NOT NULL DEFAULT 10,
                    renqi      INTEGER NOT NULL DEFAULT 10,
                    coins      INTEGER NOT NULL DEFAULT 150,
                    wins       INTEGER NOT NULL DEFAULT 0,
                    losses     INTEGER NOT NULL DEFAULT 0,
                    draws      INTEGER NOT NULL DEFAULT 0,
                    last_sign  TEXT,
                    last_draw  TEXT,
                    last_pk    TEXT,
                    sign_streak INTEGER NOT NULL DEFAULT 0,
                    is_npc     INTEGER NOT NULL DEFAULT 0,
                    npc_key    TEXT,
                    persona    TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, qq_id)
                );

                CREATE TABLE IF NOT EXISTS activity_log (
                    group_id TEXT NOT NULL,
                    qq_id    TEXT NOT NULL,
                    act_key  TEXT NOT NULL,
                    day      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_pool (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id   TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    title      TEXT NOT NULL,
                    text       TEXT NOT NULL,
                    effects    TEXT NOT NULL,
                    target     TEXT NOT NULL DEFAULT 'one',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id   TEXT NOT NULL,
                    day        TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    text       TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relations (
                    group_id  TEXT NOT NULL,
                    a_id      TEXT NOT NULL,
                    b_id      TEXT NOT NULL,
                    affection INTEGER NOT NULL DEFAULT 0,
                    couple    INTEGER NOT NULL DEFAULT 0,
                    since     TEXT,
                    gifts     TEXT NOT NULL DEFAULT '{}',
                    married   INTEGER NOT NULL DEFAULT 0,
                    married_at TEXT,
                    PRIMARY KEY (group_id, a_id, b_id)
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    group_id TEXT NOT NULL,
                    qq_id    TEXT NOT NULL,
                    item     TEXT NOT NULL,
                    count    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (group_id, qq_id, item)
                );

                CREATE TABLE IF NOT EXISTS pending (
                    group_id   TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    from_id    TEXT NOT NULL,
                    to_id      TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, kind, from_id, to_id)
                );

                CREATE TABLE IF NOT EXISTS meta (
                    group_id TEXT NOT NULL,
                    key      TEXT NOT NULL,
                    value    TEXT,
                    PRIMARY KEY (group_id, key)
                );

                CREATE TABLE IF NOT EXISTS stories (
                    group_id   TEXT NOT NULL,
                    qq_id      TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    step       INTEGER NOT NULL DEFAULT 0,
                    data       TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, qq_id, kind)
                );

                CREATE TABLE IF NOT EXISTS achievements (
                    group_id TEXT NOT NULL,
                    qq_id    TEXT NOT NULL,
                    key      TEXT NOT NULL,
                    day      TEXT NOT NULL,
                    PRIMARY KEY (group_id, qq_id, key)
                );

                CREATE TABLE IF NOT EXISTS counters (
                    group_id TEXT NOT NULL,
                    qq_id    TEXT NOT NULL,
                    month    TEXT NOT NULL,
                    key      TEXT NOT NULL,
                    value    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (group_id, qq_id, month, key)
                );
                """
            )
        self._migrate()

    def _migrate(self) -> None:
        """老库补列：人气是 v2.2 才加的，连签天数是 v2.9 才加的。"""
        with self._conn() as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(stars)").fetchall()}
            if "renqi" not in cols:
                c.execute(
                    "ALTER TABLE stars ADD COLUMN renqi INTEGER NOT NULL DEFAULT 10"
                )
            if "sign_streak" not in cols:
                c.execute(
                    "ALTER TABLE stars ADD COLUMN sign_streak INTEGER NOT NULL DEFAULT 0"
                )
            if "coins" not in cols:
                c.execute(
                    "ALTER TABLE stars ADD COLUMN coins INTEGER NOT NULL DEFAULT 150"
                )
            rcols = {r["name"] for r in c.execute("PRAGMA table_info(relations)").fetchall()}
            if "married" not in rcols:
                c.execute(
                    "ALTER TABLE relations ADD COLUMN married INTEGER NOT NULL DEFAULT 0"
                )
            if "married_at" not in rcols:
                c.execute("ALTER TABLE relations ADD COLUMN married_at TEXT")

    # ---------------- 明星 ----------------
    def get_star(self, gid: str, uid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM stars WHERE group_id=? AND qq_id=?", (gid, uid)
            ).fetchone()
        return dict(row) if row else None

    def create_star(
        self,
        gid: str,
        uid: str,
        name: str,
        is_npc: bool = False,
        npc_key: str = "",
        attrs: Optional[dict] = None,
        persona: str = "",
        renqi: int = 10,
    ) -> dict:
        attrs = attrs or {}
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO stars
                   (group_id,qq_id,name,changtiao,chuangzuo,wudao,shengyue,renqi,coins,
                    is_npc,npc_key,persona,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    gid,
                    uid,
                    name,
                    int(attrs.get("changtiao", 10)),
                    int(attrs.get("chuangzuo", 10)),
                    int(attrs.get("wudao", 10)),
                    int(attrs.get("shengyue", 10)),
                    max(0, int(renqi)),
                    int(attrs.get("coins", 150)),
                    1 if is_npc else 0,
                    npc_key,
                    persona,
                    now_iso(),
                ),
            )
        return self.get_star(gid, uid)  # type: ignore[return-value]

    def ensure_star(self, gid: str, uid: str, name: str) -> Tuple[dict, bool]:
        """有则返回，没有就建。返回 (档案, 是否新建)。"""
        s = self.get_star(gid, uid)
        if s:
            return s, False
        if not name:
            name = f"艺人{uid[-4:]}"
        return self.create_star(gid, uid, name[:20]), True

    def save_star(self, s: dict) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE stars SET name=?, changtiao=?, chuangzuo=?, wudao=?, shengyue=?,
                       renqi=?, coins=?, wins=?, losses=?, draws=?, last_sign=?, last_draw=?, last_pk=?,
                       sign_streak=?
                   WHERE group_id=? AND qq_id=?""",
                (
                    s["name"],
                    int(s["changtiao"]),
                    int(s["chuangzuo"]),
                    int(s["wudao"]),
                    int(s["shengyue"]),
                    max(0, int(s.get("renqi", 10) or 0)),
                    max(0, int(s.get("coins", 150) or 0)),
                    int(s["wins"]),
                    int(s["losses"]),
                    int(s["draws"]),
                    s.get("last_sign"),
                    s.get("last_draw"),
                    s.get("last_pk"),
                    int(s.get("sign_streak") or 0),
                    s["group_id"],
                    s["qq_id"],
                ),
            )

    def all_stars(self, gid: str, include_npc: bool = True) -> List[dict]:
        sql = "SELECT * FROM stars WHERE group_id=?"
        args: List[str] = [gid]
        if not include_npc:
            sql += " AND is_npc=0"
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def players(self, gid: str) -> List[dict]:
        return self.all_stars(gid, include_npc=False)

    def npcs(self, gid: str) -> List[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM stars WHERE group_id=? AND is_npc=1", (gid,)
            ).fetchall()
        return [dict(r) for r in rows]

    def ranking(self, gid: str, order_by: str = "total", limit: int = 50) -> List[dict]:
        if order_by in ("changtiao", "chuangzuo", "wudao", "shengyue", "renqi"):
            col = order_by
        else:
            col = "(changtiao+chuangzuo+wudao+shengyue)"
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM stars WHERE group_id=? ORDER BY {col} DESC LIMIT ?",
                (gid, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_by_name(self, gid: str, name: str) -> List[dict]:
        """按艺名模糊找人（真人优先）。"""
        name = (name or "").strip()
        if not name:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM stars WHERE group_id=? AND name LIKE ? ORDER BY is_npc ASC",
                (gid, f"%{name}%"),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 活动 ----------------
    def mark_activity(self, gid: str, uid: str, act_key: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO activity_log (group_id,qq_id,act_key,day) VALUES (?,?,?,?)",
                (gid, uid, act_key, today()),
            )

    def activity_done(self, gid: str, uid: str, act_key: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM activity_log WHERE group_id=? AND qq_id=? AND act_key=? AND day=?",
                (gid, uid, act_key, today()),
            ).fetchone()
        return row is not None

    def count_activity(self, gid: str, uid: str, act_key: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(1) AS n FROM activity_log WHERE group_id=? AND qq_id=? AND act_key=? AND day=?",
                (gid, uid, act_key, today()),
            ).fetchone()
        return int(row["n"]) if row else 0

    # ---------------- 剧情状态（通告 / 采访） ----------------
    def save_story(self, gid: str, uid: str, kind: str, step: int, data: dict) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO stories (group_id,qq_id,kind,step,data,updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(group_id,qq_id,kind) DO UPDATE SET
                     step=excluded.step, data=excluded.data, updated_at=excluded.updated_at""",
                (gid, uid, kind, int(step), json.dumps(data, ensure_ascii=False), now_iso()),
            )

    def get_story(self, gid: str, uid: str, kind: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM stories WHERE group_id=? AND qq_id=? AND kind=?",
                (gid, uid, kind),
            ).fetchone()
        if not row:
            return None
        s = dict(row)
        try:
            s["data"] = json.loads(s.get("data") or "{}")
        except Exception:
            s["data"] = {}
        return s

    def del_story(self, gid: str, uid: str, kind: str) -> None:
        with self._conn() as c:
            c.execute(
                "DELETE FROM stories WHERE group_id=? AND qq_id=? AND kind=?",
                (gid, uid, kind),
            )

    # ---------------- meta ----------------
    def meta_get(self, gid: str, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute(
                "SELECT value FROM meta WHERE group_id=? AND key=?", (gid, key)
            ).fetchone()
        return row["value"] if row and row["value"] is not None else default

    def meta_set(self, gid: str, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO meta (group_id,key,value) VALUES (?,?,?) "
                "ON CONFLICT(group_id,key) DO UPDATE SET value=excluded.value",
                (gid, key, value),
            )

    # ---------------- 事件池 ----------------
    def add_events(self, gid: str, events: List[dict]) -> int:
        n = 0
        with self._conn() as c:
            for e in events:
                c.execute(
                    """INSERT INTO event_pool (group_id,kind,title,text,effects,target,created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        gid,
                        str(e.get("kind", "绯闻"))[:8],
                        str(e.get("title", ""))[:20],
                        str(e.get("text", ""))[:200],
                        json.dumps(e.get("effects") or {}, ensure_ascii=False),
                        "all" if e.get("target") == "all" else "one",
                        now_iso(),
                    ),
                )
                n += 1
        return n

    def pool_size(self, gid: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(1) AS n FROM event_pool WHERE group_id=?", (gid,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def pop_event(self, gid: str, require_placeholder: bool = True) -> Optional[dict]:
        """抽一条事件并从池里删掉。

        require_placeholder：只抽主角写成 {name} 占位符的事件。
        老版本的池子里混着模型自己编人名的条目（事件写别人、效果扣玩家），
        抽不到合规条目时把这些脏数据整批清掉，让上层重新生成。
        """
        with self._conn() as c:
            if require_placeholder:
                row = c.execute(
                    "SELECT * FROM event_pool WHERE group_id=? AND instr(text,'{name}')>0 "
                    "ORDER BY RANDOM() LIMIT 1",
                    (gid,),
                ).fetchone()
                if not row:
                    c.execute(
                        "DELETE FROM event_pool WHERE group_id=? AND instr(text,'{name}')=0",
                        (gid,),
                    )
                    return None
            else:
                row = c.execute(
                    "SELECT * FROM event_pool WHERE group_id=? ORDER BY RANDOM() LIMIT 1",
                    (gid,),
                ).fetchone()
                if not row:
                    return None
            c.execute("DELETE FROM event_pool WHERE id=?", (row["id"],))
        e = dict(row)
        try:
            e["effects"] = json.loads(e.get("effects") or "{}")
        except Exception:
            e["effects"] = {}
        return e

    def log_event(self, gid: str, kind: str, text: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO event_log (group_id,day,kind,text,created_at) VALUES (?,?,?,?,?)",
                (gid, today(), kind, text, now_iso()),
            )

    def events_today(self, gid: str, limit: int = 12) -> List[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM event_log WHERE group_id=? AND day=? ORDER BY id DESC LIMIT ?",
                (gid, today(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def events_today_count(self, gid: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(1) AS n FROM event_log WHERE group_id=? AND day=?",
                (gid, today()),
            ).fetchone()
        return int(row["n"]) if row else 0

    # ---------------- 关系 ----------------
    def get_relation(self, gid: str, x: str, y: str) -> dict:
        a, b = pair(x, y)
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM relations WHERE group_id=? AND a_id=? AND b_id=?",
                (gid, a, b),
            ).fetchone()
        if row:
            r = dict(row)
            try:
                r["gifts"] = json.loads(r.get("gifts") or "{}")
            except Exception:
                r["gifts"] = {}
            return r
        return {
            "group_id": gid,
            "a_id": a,
            "b_id": b,
            "affection": 0,
            "couple": 0,
            "since": None,
            "gifts": {},
            "married": 0,
            "married_at": None,
        }

    def save_relation(self, r: dict) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO relations
                     (group_id,a_id,b_id,affection,couple,since,gifts,married,married_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(group_id,a_id,b_id) DO UPDATE SET
                     affection=excluded.affection,
                     couple=excluded.couple,
                     since=excluded.since,
                     gifts=excluded.gifts,
                     married=excluded.married,
                     married_at=excluded.married_at""",
                (
                    r["group_id"],
                    r["a_id"],
                    r["b_id"],
                    int(r["affection"]),
                    1 if r.get("couple") else 0,
                    r.get("since"),
                    json.dumps(r.get("gifts") or {}, ensure_ascii=False),
                    1 if r.get("married") else 0,
                    r.get("married_at"),
                ),
            )

    def add_affection(self, gid: str, x: str, y: str, delta: int) -> dict:
        r = self.get_relation(gid, x, y)
        r["affection"] = max(0, min(100, int(r["affection"]) + delta))
        self.save_relation(r)
        return r

    def couples(self, gid: str) -> List[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM relations WHERE group_id=? AND couple=1", (gid,)
            ).fetchall()
        return [dict(r) for r in rows]

    def partner_of(self, gid: str, uid: str) -> Optional[str]:
        for r in self.couples(gid):
            if r["a_id"] == uid:
                return r["b_id"]
            if r["b_id"] == uid:
                return r["a_id"]
        return None

    def married_of(self, gid: str, uid: str) -> Optional[str]:
        for r in self.couples(gid):
            if not r.get("married"):
                continue
            if r["a_id"] == uid:
                return r["b_id"]
            if r["b_id"] == uid:
                return r["a_id"]
        return None

    # ---------------- 背包 ----------------
    def inv_get(self, gid: str, uid: str) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT item, count FROM inventory WHERE group_id=? AND qq_id=? AND count>0",
                (gid, uid),
            ).fetchall()
        return {r["item"]: int(r["count"]) for r in rows}

    def inv_count(self, gid: str, uid: str, item: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT count FROM inventory WHERE group_id=? AND qq_id=? AND item=?",
                (gid, uid, item),
            ).fetchone()
        return int(row["count"]) if row else 0

    def inv_add(self, gid: str, uid: str, item: str, n: int = 1) -> int:
        with self._conn() as c:
            c.execute(
                """INSERT INTO inventory (group_id,qq_id,item,count) VALUES (?,?,?,?)
                   ON CONFLICT(group_id,qq_id,item) DO UPDATE SET count=count+excluded.count""",
                (gid, uid, item, int(n)),
            )
            row = c.execute(
                "SELECT count FROM inventory WHERE group_id=? AND qq_id=? AND item=?",
                (gid, uid, item),
            ).fetchone()
        return int(row["count"]) if row else 0

    def inv_take(self, gid: str, uid: str, item: str, n: int = 1) -> bool:
        if self.inv_count(gid, uid, item) < n:
            return False
        with self._conn() as c:
            c.execute(
                "UPDATE inventory SET count=count-? WHERE group_id=? AND qq_id=? AND item=?",
                (int(n), gid, uid, item),
            )
        return True

    # ---------------- 待办（表白请求） ----------------
    def add_pending(self, gid: str, kind: str, from_id: str, to_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO pending (group_id,kind,from_id,to_id,created_at) VALUES (?,?,?,?,?)",
                (gid, kind, from_id, to_id, now_iso()),
            )

    def get_pending(self, gid: str, kind: str, from_id: str, to_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM pending WHERE group_id=? AND kind=? AND from_id=? AND to_id=?",
                (gid, kind, from_id, to_id),
            ).fetchone()
        return dict(row) if row else None

    def pendings_to(
        self, gid: str, to_id: str, kind: Optional[str] = None
    ) -> List[dict]:
        """发给某人的待办；kind 为 None 时表白和求婚都返回。"""
        with self._conn() as c:
            if kind is None:
                rows = c.execute(
                    "SELECT * FROM pending WHERE group_id=? AND to_id=? "
                    "ORDER BY created_at DESC",
                    (gid, to_id),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM pending WHERE group_id=? AND kind=? AND to_id=? "
                    "ORDER BY created_at DESC",
                    (gid, kind, to_id),
                ).fetchall()
        return [dict(r) for r in rows]

    def del_pending(self, gid: str, kind: str, from_id: str, to_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "DELETE FROM pending WHERE group_id=? AND kind=? AND from_id=? AND to_id=?",
                (gid, kind, from_id, to_id),
            )

    # ---------------- 成就 ----------------
    def unlock(self, gid: str, uid: str, key: str) -> bool:
        """解锁一个成就；已经有的返回 False。"""
        with self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO achievements (group_id,qq_id,key,day) VALUES (?,?,?,?)",
                (gid, uid, key, today()),
            )
            return cur.rowcount > 0

    def achs_of(self, gid: str, uid: str) -> List[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT key FROM achievements WHERE group_id=? AND qq_id=? ORDER BY day",
                (gid, uid),
            ).fetchall()
        return [r["key"] for r in rows]

    # ---------------- 个人动态 ----------------
    def recent_for(self, gid: str, name: str, limit: int = 3) -> List[dict]:
        """最近提到这个人的事件流水（自己触发的事件正文里会带名字）。"""
        name = (name or "").strip()
        if not name:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT kind,text FROM event_log WHERE group_id=? AND instr(text,?)>0 "
                "ORDER BY id DESC LIMIT ?",
                (gid, name, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 月度考勤 ----------------
    def bump(self, gid: str, uid: str, month: str, key: str, n: int = 1) -> int:
        """月度计数器 +1，返回加完后的值。"""
        with self._conn() as c:
            c.execute(
                "INSERT INTO counters (group_id,qq_id,month,key,value) VALUES (?,?,?,?,?) "
                "ON CONFLICT(group_id,qq_id,month,key) DO UPDATE SET value=value+excluded.value",
                (gid, uid, month, key, int(n)),
            )
            row = c.execute(
                "SELECT value FROM counters WHERE group_id=? AND qq_id=? AND month=? AND key=?",
                (gid, uid, month, key),
            ).fetchone()
        return int(row["value"]) if row else 0

    def counters_of(self, gid: str, uid: str, month: str) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT key,value FROM counters WHERE group_id=? AND qq_id=? AND month=?",
                (gid, uid, month),
            ).fetchall()
        return {r["key"]: int(r["value"]) for r in rows}
