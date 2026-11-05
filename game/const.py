"""星途 2.0 常量：段位、属性、活动、抽签、礼物、NPC 名册。

数值按「4 人小群」重新校准：
- 抽签仍是 0-100（原设定），但冷却拉长，四项各抽不再让人一天登顶
- 段位阈值整体上调，配合 NPC 的成长速度，节奏约 1~2 周
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------- 四项属性 ----------------
ATTRS: Dict[str, str] = {
    "changtiao": "唱跳",
    "chuangzuo": "创作",
    "wudao": "舞蹈",
    "shengyue": "声乐",
}
ATTR_KEYS: List[str] = list(ATTRS.keys())

# ---------------- 段位 ----------------
TIERS: List[Tuple[int, str]] = [
    (0, "🔰 练习生"),
    (300, "🎤 新人歌手"),
    (900, "🌟 人气偶像"),
    (1800, "💎 实力明星"),
    (3200, "👑 顶流巨星"),
    (5000, "🏆 天王／天后"),
    (8000, "🌈 传奇偶像"),
    (12000, "⚡ 不灭神话"),
]

# ---------------- 活动 ----------------
ACTIVITIES: Dict[str, Tuple[str, str]] = {
    "选秀": ("changtiao", "站上选秀舞台，比拼综合舞台表现力"),
    "写歌": ("chuangzuo", "闭关写歌作曲，打磨创作硬实力"),
    "斗舞": ("wudao", "街头／舞台斗舞，纯舞蹈硬碰硬"),
    "开嗓": ("shengyue", "声乐训练营，开嗓飙高音"),
    "盛典": ("total", "年度颁奖盛典，四项全能一起冲"),
}

# ---------------- 抽签 ----------------
DRAW_TYPES: Dict[str, dict] = {
    "全能": {"desc": "四项各抽 0-100", "mode": "all", "range": (0, 100)},
    "单项": {"desc": "随机一项抽 0-100", "mode": "single", "range": (0, 100)},
    "欧皇": {
        "desc": "15% 概率随机一项抽 80-100（稀有），否则普通单项",
        "mode": "lucky",
        "range": (80, 100),
        "chance": 0.15,
    },
    "反向": {"desc": "随机一项 -0~30（霉运签）", "mode": "penalty", "range": (0, 30)},
}

# ---------------- 签到 ----------------
SIGN_BASE = (1, 3)
SIGN_BIG = (3, 10)

# ---------------- 送礼 / 礼品商店 ----------------
# 礼物名 -> {price 售价, lo/hi 好感区间, cap 每天每人同种上限, desc 介绍}
GIFT_SHOP: Dict[str, dict] = {
    "奶茶": {"price": 30, "lo": 3, "hi": 5, "cap": 3, "desc": "顺手带的，不贵但有温度"},
    "鲜花": {"price": 60, "lo": 5, "hi": 8, "cap": 2, "desc": "九十九朵，助理替你叫的花店"},
    "手写情书": {"price": 90, "lo": 7, "hi": 10, "cap": 2, "desc": "自己写的，字有点丑"},
    "演唱会VIP票": {"price": 180, "lo": 9, "hi": 13, "cap": 1, "desc": "前排，能看清对方的笑"},
    "限量项链": {"price": 300, "lo": 12, "hi": 18, "cap": 1, "desc": "品牌联名，刻了你的名字"},
    "求婚戒指": {"price": 520, "lo": 0, "hi": 0, "cap": 1, "desc": "只用来求婚，送出去就是承诺"},
}

# 兼容老代码：礼物名 -> (lo, hi, cap)
GIFTS: Dict[str, Tuple[int, int, int]] = {
    k: (v["lo"], v["hi"], v["cap"]) for k, v in GIFT_SHOP.items()
}

# ---------------- 收支 ----------------
COIN_START = 150          # 出道的启动资金
ACTIVITY_COST = 10        # 练功/参加活动的场地费
DRAMA_BASE_FEE = 40       # 接戏通告费基础
DRAMA_SCORE_FEE = 1.2     # 每分表现分折合的星币
INTERVIEW_FEE = 25        # 采访车马费
MARRY_AFFECTION = 90      # NPC 答应的求婚门槛
MARRY_DIVORCE_PENALTY = 20  # 离婚掉的好感

# ---------------- NPC 名册 ----------------
# attrs 是初始四项；growth 是每日成长系数；love 是表白成功所需好感
NPC_ROSTER: List[dict] = [
    {
        "key": "wenruan",
        "name": "温软",
        "tag": "刚出道的甜妹练习生",
        "gender": "女",
        "style": "甜妹系练习生",
        "fans": 86000,
        "attrs": {"changtiao": 28, "chuangzuo": 12, "wudao": 22, "shengyue": 18},
        "growth": 1.0,
        "love": 45,
        "persona": "软软的、爱脸红、说话带鼻音，追星比自己出名还上心",
        "lines": ["我、我还能再练一遍吗…", "谢谢你陪我练舞！", "呜…被夸了会睡不着的"],
    },
    {
        "key": "baihe",
        "name": "白鹤",
        "tag": "中二病舞担",
        "gender": "男",
        "style": "中二舞担",
        "fans": 120000,
        "attrs": {"changtiao": 40, "chuangzuo": 25, "wudao": 78, "shengyue": 30},
        "growth": 1.05,
        "love": 55,
        "persona": "中二、爱说冷笑话、自称被月光选中的舞者",
        "lines": ["月光指引我拿下了这一局。", "你的舞步…还不错，勉强合格。", "哈？才不是因为你才来的。"],
    },
    {
        "key": "linwanxing",
        "name": "林晚星",
        "tag": "国民妹妹",
        "gender": "女",
        "style": "元气少女",
        "fans": 1200000,
        "attrs": {"changtiao": 120, "chuangzuo": 70, "wudao": 150, "shengyue": 110},
        "growth": 1.1,
        "love": 60,
        "persona": "甜的、爱吃甜食、营业时元气，私下有点小迷糊",
        "lines": ["今天也要元气满满！", "赢了就请我吃蛋糕好不好～", "嘿嘿，被你夸到了。"],
    },
    {
        "key": "jiangye",
        "name": "江野",
        "tag": "叛逆摇滚主唱",
        "gender": "男",
        "style": "摇滚主唱",
        "fans": 950000,
        "attrs": {"changtiao": 150, "chuangzuo": 130, "wudao": 60, "shengyue": 140},
        "growth": 1.15,
        "love": 65,
        "persona": "暴躁、嘴硬、其实很在意别人，讨厌客套",
        "lines": ["少废话，上台。", "…唱得还行，别得意。", "你要是输了，我给你写首歌。"],
    },
    {
        "key": "suli",
        "name": "苏黎",
        "tag": "温柔声乐天后",
        "gender": "女",
        "style": "温柔情歌",
        "fans": 3400000,
        "attrs": {"changtiao": 260, "chuangzuo": 200, "wudao": 160, "shengyue": 330},
        "growth": 1.15,
        "love": 62,
        "persona": "温柔、易哭、把所有人都当小孩照顾",
        "lines": ["别急，慢慢来。", "你今天…唱得让我有点想哭。", "要好好吃饭呀。"],
    },
    {
        "key": "luzhixia",
        "name": "陆知夏",
        "tag": "学院派制作人",
        "gender": "男",
        "style": "学院派制作人",
        "fans": 3000000,
        "attrs": {"changtiao": 210, "chuangzuo": 420, "wudao": 120, "shengyue": 180},
        "growth": 1.2,
        "love": 70,
        "persona": "毒舌、严谨、夸人像在挑错",
        "lines": ["这段可以，但还差三个月。", "你的音准…算了，有进步。", "别哭，哭解决不了编曲。"],
    },
    {
        "key": "xuqinghe",
        "name": "许清和",
        "tag": "老牌天王",
        "gender": "男",
        "style": "老牌天王",
        "fans": 8000000,
        "attrs": {"changtiao": 500, "chuangzuo": 460, "wudao": 300, "shengyue": 520},
        "growth": 1.1,
        "love": 75,
        "persona": "稳、温和、话不多但每句都算数",
        "lines": ["台上的三分钟，台下要还。", "你比我想的有韧性。", "喝杯茶？"],
    },
    {
        "key": "shenyan",
        "name": "沈砚",
        "tag": "高冷影帝级顶流",
        "gender": "男",
        "style": "高冷影帝",
        "fans": 15000000,
        "attrs": {"changtiao": 700, "chuangzuo": 780, "wudao": 420, "shengyue": 620},
        "growth": 1.25,
        "love": 80,
        "persona": "话极少、冷感、护短，夸人只用两个字",
        "lines": ["嗯。", "可以。", "……别逞强。"],
    },
    {
        "key": "xiazhi",
        "name": "夏栀",
        "tag": "电台出身的清唱新人",
        "gender": "女",
        "style": "民谣清唱",
        "fans": 260000,
        "attrs": {"changtiao": 170, "chuangzuo": 150, "wudao": 120, "shengyue": 200},
        "growth": 1.05,
        "cap": 899,
        "love": 55,
        "persona": "慢热、说话轻、把每首歌都当成讲一个故事，唱到动情处会停半拍",
        "lines": ["这段我想再唱一遍，刚才有点想哭。", "你听出来了吗，最后一句我改了。", "别急着夸我，我先给你弹完。"],
    },
    {
        "key": "chengye",
        "name": "程也",
        "tag": "舞台机器级顶流爱豆",
        "gender": "男",
        "style": "舞台爱豆",
        "fans": 38000000,
        "attrs": {"changtiao": 1100, "chuangzuo": 780, "wudao": 1050, "shengyue": 670},
        "growth": 1.25,
        "cap": 4999,
        "love": 72,
        "persona": "永远在营业、笑容标准得像贴上去的，私下累到不想说话，但对粉丝一句重话都没有",
        "lines": ["镜头还在，先笑。", "这个动作我练了四千遍。", "……扶我一下，三秒就好。"],
    },
    {
        "key": "nieqingshuang",
        "name": "聂清霜",
        "tag": "歌坛天后",
        "gender": "女",
        "style": "冷艳天后",
        "fans": 52000000,
        "attrs": {"changtiao": 1600, "chuangzuo": 1350, "wudao": 1250, "shengyue": 1600},
        "growth": 1.2,
        "cap": 7999,
        "love": 68,
        "persona": "冷、不解释、对专业苛刻，夸人只夸细节",
        "lines": ["气口错了半个字。", "再来。这次别用嗓子，用耳朵。", "你今天…有点东西。"],
    },
    {
        "key": "peitinglan",
        "name": "裴听澜",
        "tag": "退隐又复出的传奇",
        "gender": "女",
        "style": "九十年代传奇",
        "fans": 68000000,
        "attrs": {"changtiao": 2400, "chuangzuo": 2650, "wudao": 1900, "shengyue": 2250},
        "growth": 1.15,
        "cap": 11999,
        "love": 74,
        "persona": "温和、话里有话、什么场面都见过，喜欢看新人出丑也喜欢看新人翻盘",
        "lines": ["我退过，所以我知道什么时候该退。", "你这一手，二十年前我也用过。", "别学我，学我你会输。"],
    },
    {
        "key": "changye",
        "name": "长夜",
        "tag": "从不露面的神话",
        "gender": "不明",
        "style": "神秘歌者",
        "fans": 120000000,
        "attrs": {"changtiao": 3400, "chuangzuo": 3500, "wudao": 3200, "shengyue": 3400},
        "growth": 1.1,
        "love": 80,
        "persona": "神秘、只以声音出现、名字就是全部信息，没人见过本尊",
        "lines": ["听见就够了。", "名字不重要，声音才算数。", "……你离得很近了。"],
    },
    {
        "key": "guxiaoman",
        "name": "顾小满",
        "tag": "刚签到公司的练习生",
        "gender": "女",
        "style": "新手练习生",
        "fans": 12000,
        "attrs": {"changtiao": 40, "chuangzuo": 25, "wudao": 28, "shengyue": 20},
        "growth": 1.0,
        "cap": 299,
        "love": 42,
        "persona": "紧张、记不住词、被夸一句能脸红半天，练功房最后一个走",
        "lines": ["我、我再来一遍…这次真的记住了。", "能不能别看我，我会忘词的。", "谢谢…我会加油的，真的。"],
    },
    {
        "key": "tangtang",
        "name": "南星",
        "tag": "练了三年还没出道的练习生",
        "gender": "女",
        "style": "熬了三年的练习生",
        "fans": 34000,
        "attrs": {"changtiao": 70, "chuangzuo": 55, "wudao": 67, "shengyue": 60},
        "growth": 1.0,
        "cap": 299,
        "love": 50,
        "persona": "爱笑、嘴硬、心里知道自己差在哪，最怕别人说「你还年轻」",
        "lines": ["我练了三年，不是来听安慰的。", "这次别再让我等通知了。", "笑什么，我认真的。"],
    },
    {
        "key": "fushiye",
        "name": "傅时野",
        "tag": "稳坐实力派的中坚",
        "gender": "男",
        "style": "实力派中坚",
        "fans": 6600000,
        "attrs": {"changtiao": 700, "chuangzuo": 620, "wudao": 480, "shengyue": 400},
        "growth": 1.2,
        "cap": 3199,
        "love": 70,
        "persona": "话少、技术流、从不上热搜也从不掉队，最看不惯靠话题吃饭的人",
        "lines": ["活儿说话。", "你这版，第二段是抄的吧。", "别急，先把手上的做完。"],
    },
    {
        "key": "nuomi",
        "name": "糯米",
        "tag": "童星出身的甜妹练习生",
        "gender": "女",
        "style": "童星甜妹",
        "fans": 9000,
        "attrs": {"changtiao": 18, "chuangzuo": 14, "wudao": 16, "shengyue": 12},
        "growth": 1.0,
        "cap": 299,
        "love": 40,
        "persona": "嘴甜爱撒娇、习惯被夸、其实很怕别人说她还小，练舞会偷偷哭",
        "lines": ["我小时候就上过电视的！", "人家已经很努力了嘛…", "别摸我头，我不是小孩。"],
    },
    {
        "key": "tingyu",
        "name": "周听雨",
        "tag": "抱着吉他的民谣新人",
        "gender": "男",
        "style": "民谣创作",
        "fans": 450000,
        "attrs": {"changtiao": 220, "chuangzuo": 240, "wudao": 120, "shengyue": 200},
        "growth": 1.05,
        "cap": 899,
        "love": 58,
        "persona": "安静、写歌慢、不太会营业，一进录音棚就像换了个人",
        "lines": ["这首歌写了两年，你别催。", "我不太会说话，我唱给你听。", "……嗯，那就这样说定了。"],
    },
    {
        "key": "alan",
        "name": "阿岚",
        "tag": "地下说唱新人",
        "gender": "男",
        "style": "地下说唱",
        "fans": 220000,
        "attrs": {"changtiao": 150, "chuangzuo": 160, "wudao": 120, "shengyue": 90},
        "growth": 1.1,
        "cap": 899,
        "love": 52,
        "persona": "冲、呛、不服就写歌骂你，但只骂有资格的对手",
        "lines": ["写歌比说话快，你听好。", "这 flow 你也敢接？", "骂你不是恨你，是看得起你。"],
    },
    {
        "key": "zhongli",
        "name": "钟离",
        "tag": "男团门面担当",
        "gender": "男",
        "style": "男团门面",
        "fans": 2100000,
        "attrs": {"changtiao": 380, "chuangzuo": 260, "wudao": 420, "shengyue": 340},
        "growth": 1.15,
        "cap": 1799,
        "love": 66,
        "persona": "镜头感天生、话不多、被拍到永远在状态，私底下爱偷偷吃东西",
        "lines": ["站我右边，出片。", "粉丝说的是对的，我确实好看。", "……这个我能吃吗？就一口。"],
    },
    {
        "key": "zhuqing",
        "name": "祝晴",
        "tag": "甜系人气女歌手",
        "gender": "女",
        "style": "甜系流行",
        "fans": 1800000,
        "attrs": {"changtiao": 300, "chuangzuo": 280, "wudao": 260, "shengyue": 360},
        "growth": 1.1,
        "cap": 1799,
        "love": 64,
        "persona": "笑起来甜到齁、情商极高、把所有人都哄得服服帖帖",
        "lines": ["你今天的努力我看见了哦。", "别丧嘛，笑一个给我看。", "夸你的话我说过很多次，一次都不是客套。"],
    },
    {
        "key": "shenyu",
        "name": "沈屿",
        "tag": "音乐剧出来的实力派",
        "gender": "男",
        "style": "音乐剧实力派",
        "fans": 6600000,
        "attrs": {"changtiao": 780, "chuangzuo": 820, "wudao": 600, "shengyue": 750},
        "growth": 1.2,
        "cap": 3199,
        "love": 70,
        "persona": "戏痴、开口就是台词、认真到有点吓人，最烦「差不多就行」",
        "lines": ["再来一遍，这次我要看见角色。", "差不多的东西，观众一眼就看穿。", "你刚才那句，是活的。"],
    },
    {
        "key": "qinghe",
        "name": "沈青禾",
        "tag": "顶流中的顶流",
        "gender": "男",
        "style": "顶流天花板",
        "fans": 42000000,
        "attrs": {"changtiao": 1200, "chuangzuo": 1000, "wudao": 1150, "shengyue": 1150},
        "growth": 1.25,
        "cap": 4999,
        "love": 76,
        "persona": "天生该站在灯下的人，不解释、不辩白、只赢；对新人意外地有耐心",
        "lines": ["灯亮的时候别眨眼。", "我不需要你喜欢我，我需要你看见我。", "你刚才那一下，我可以教你。"],
    },
    {
        "key": "shiyan",
        "name": "时晏",
        "tag": "唱作一体的顶流",
        "gender": "男",
        "style": "摇滚顶流",
        "fans": 36000000,
        "attrs": {"changtiao": 1250, "chuangzuo": 1300, "wudao": 1100, "shengyue": 1050},
        "growth": 1.25,
        "cap": 4999,
        "love": 74,
        "persona": "清醒、爱怼人、自己的歌一句都不许别人改，但对真心的夸奖会当场红耳朵",
        "lines": ["我唱我写的，谁也改不了一个字。", "别夸我，说具体点。", "……再说一遍？刚才这句。"],
    },
    {
        "key": "bailu",
        "name": "白鹭",
        "tag": "大银幕顶流",
        "gender": "女",
        "style": "影视顶流",
        "fans": 29000000,
        "attrs": {"changtiao": 980, "chuangzuo": 1100, "wudao": 1050, "shengyue": 970},
        "growth": 1.2,
        "cap": 4999,
        "love": 72,
        "persona": "镜头前贵气逼人、私下爱蹲在路边吃烤串，最讨厌别人叫她神仙姐姐",
        "lines": ["别叫我神仙姐姐，我吃辣条的。", "这一条我想素颜来。", "戏比天大，别的都是点缀。"],
    },
    {
        "key": "guhanchuan",
        "name": "顾寒川",
        "tag": "天王",
        "gender": "男",
        "style": "古典跨界",
        "fans": 61000000,
        "attrs": {"changtiao": 1800, "chuangzuo": 1750, "wudao": 1500, "shengyue": 1750},
        "growth": 1.15,
        "cap": 7999,
        "love": 76,
        "persona": "贵气、疏离、说话像在颁奖，从不上综艺，一开口全场安静",
        "lines": ["音乐不必热闹。", "你有天分，但缺十年。", "坐吧，我弹给你听。"],
    },
    {
        "key": "wenyining",
        "name": "温以宁",
        "tag": "天后",
        "gender": "女",
        "style": "国民情歌",
        "fans": 75000000,
        "attrs": {"changtiao": 1900, "chuangzuo": 1900, "wudao": 1600, "shengyue": 2000},
        "growth": 1.15,
        "cap": 7999,
        "love": 78,
        "persona": "温柔到有点狠、每首歌都像在讲自己的事，从不需要飙高音证明什么",
        "lines": ["这首，是写给一个人的。", "别学我高音，学我怎么忍住。", "唱哭了不丢人，假唱才丢人。"],
    },
    {
        "key": "yezhiqiu",
        "name": "叶知秋",
        "tag": "传奇",
        "gender": "女",
        "style": "时代之声",
        "fans": 92000000,
        "attrs": {"changtiao": 2600, "chuangzuo": 2750, "wudao": 2400, "shengyue": 2750},
        "growth": 1.1,
        "cap": 11999,
        "love": 80,
        "persona": "活成了一个时代、说话慢、眼睛却亮，见过太多人红了又掉下去",
        "lines": ["我红的时候，你还没出生。", "这个圈子唯一不变的是它一直在变。", "别急，先活过第一年。"],
    },
    {
        "key": "shangqing",
        "name": "商青",
        "tag": "传奇",
        "gender": "男",
        "style": "舞台传奇",
        "fans": 105000000,
        "attrs": {"changtiao": 2800, "chuangzuo": 2600, "wudao": 3100, "shengyue": 3000},
        "growth": 1.1,
        "cap": 11999,
        "love": 78,
        "persona": "二十年没离开过舞台、把身体练成乐器，最烦「流量」两个字",
        "lines": ["舞台不会骗人，人会。", "再跳一遍，跳到腿抖为止。", "你脚下这块地板，我跪过。"],
    },
    {
        "key": "guiling",
        "name": "归零",
        "tag": "神话",
        "gender": "不明",
        "style": "无人可定义",
        "fans": 180000000,
        "attrs": {"changtiao": 4400, "chuangzuo": 4400, "wudao": 4400, "shengyue": 4300},
        "growth": 1.05,
        "love": 82,
        "persona": "没人知道是男是女、是几岁、长什么样，每次出现都像从没离开过",
        "lines": ["又是你。", "我已经不需要名字了。", "看台上那个人，像不像你。"],
    },
    {
        "key": "wuming",
        "name": "无名",
        "tag": "神话",
        "gender": "男",
        "style": "隐世宗师",
        "fans": 150000000,
        "attrs": {"changtiao": 4100, "chuangzuo": 4000, "wudao": 3900, "shengyue": 4000},
        "growth": 1.05,
        "love": 80,
        "persona": "多年前就退圈、没人见过他现代的样子，只留一句「唱完就走」",
        "lines": ["唱完就走。", "名字是给别人叫的。", "你唱得不错，别学我退。"],
    },
]

NPC_BY_KEY: Dict[str, dict] = {n["key"]: n for n in NPC_ROSTER}
NPC_BY_NAME: Dict[str, dict] = {n["name"]: n for n in NPC_ROSTER}

# ---------------- 事件库 ----------------
EVENT_KINDS: List[str] = [
    "绯闻",
    "爆红",
    "翻车",
    "资源",
    "恋情",
    "黑热搜",
    "综艺",
    "塌房",
    "代言",
    "影视",
    "音乐",
    "时尚",
    "应援",
    "争议",
    "私生",
    "黑料",
    "解约",
]

# 事件的「方向」：+1 好事只加不减，-1 坏事只减不加，0 不限。
# 这样一条事件里不会同时出现「舞蹈-2、唱跳+3」这种玩家看不懂的加减。
EVENT_POLARITY: Dict[str, int] = {
    "爆红": 1,
    "资源": 1,
    "综艺": 1,
    "恋情": 1,
    "代言": 1,
    "影视": 1,
    "音乐": 1,
    "时尚": 1,
    "应援": 1,
    "绯闻": -1,
    "黑热搜": -1,
    "塌房": -1,
    "翻车": -1,
    "争议": -1,
    "私生": -1,
    "黑料": -1,
    "解约": -1,
}

# AI 不可用时的兜底事件（手写，保证游戏永远有事件可抽）
FALLBACK_EVENTS: List[dict] = [
    {
        "kind": "爆红",
        "title": "深夜路透爆火",
        "text": "有人在深夜街头拍到你在便利店买关东煮，一段失焦视频冲上热搜，全网都在夸这张脸。",
        "effects": {"changtiao": 4, "shengyue": 3, "renqi": 12},
        "target": "one",
    },
    {
        "kind": "绯闻",
        "title": "同款外套疑云",
        "text": "营销号发现你和一个陌生身影穿了同款外套，配文只有三个字：『有点东西』，评论区已经开始编故事，路人缘掉了一截。",
        "effects": {"renqi": -6},
        "target": "one",
    },
    {
        "kind": "资源",
        "title": "大导新片试镜",
        "text": "一部年度大片的副导演半夜给你发来试镜邀约，附带一句『别让公司知道』。",
        "effects": {"changtiao": 6},
        "target": "one",
    },
    {
        "kind": "翻车",
        "title": "直播口误现场",
        "text": "你在直播里把赞助商名字念错了，弹幕笑成一片，公关正在加班写道歉稿。",
        "effects": {"chuangzuo": -3},
        "target": "one",
    },
    {
        "kind": "综艺",
        "title": "综艺救场名场面",
        "text": "综艺录制现场有人忘词，你接过话筒即兴唱了两句，全场起立鼓掌。",
        "effects": {"shengyue": 5, "wudao": 2},
        "target": "one",
    },
    {
        "kind": "黑热搜",
        "title": "被剪成反派",
        "text": "节目组的剪刀手把你剪成了全片最讨厌的人，热搜下全是让你退圈的评论。",
        "effects": {"changtiao": -4, "shengyue": -2, "renqi": -10},
        "target": "one",
    },
    {
        "kind": "爆红",
        "title": "一段清唱出圈",
        "text": "后台随手清唱的一段被工作人员录下来发到网上，播放量破了千万，评论区全是『求出单曲』。",
        "effects": {"shengyue": 7, "renqi": 14},
        "target": "one",
    },
    {
        "kind": "恋情",
        "title": "狗仔蹲到了",
        "text": "狗仔拍到你和一位同行并肩走过整条街，标题写着：『这次是真的吗？』",
        "effects": {"changtiao": 2, "chuangzuo": 2},
        "target": "one",
    },
    {
        "kind": "塌房",
        "title": "旧interview被翻出",
        "text": "三年前的一段采访被翻出来，你当时说的话和现在完全相反，粉丝开始分裂。",
        "effects": {"chuangzuo": -5, "renqi": -12},
        "target": "one",
    },
    {
        "kind": "资源",
        "title": "时尚刊封面",
        "text": "一线时尚刊把你放上了封面，摄影师说：『这组片子能挂十年。』",
        "effects": {"changtiao": 4, "wudao": 3},
        "target": "one",
    },
    {
        "kind": "代言",
        "title": "饮料代言官宣",
        "text": "你官宣了一个饮料代言，第二天地铁灯箱全换成了你的脸，路过的人都得抬头看你一眼。",
        "effects": {"changtiao": 3, "renqi": 6},
        "target": "one",
    },
    {
        "kind": "代言",
        "title": "品牌方凌晨撤海报",
        "text": "一个国民品牌原定上午官宣，凌晨却把海报换成了别人，只剩你的粉丝还在等那条微博。",
        "effects": {"renqi": -5},
        "target": "one",
    },
    {
        "kind": "影视",
        "title": "客串只剩背影",
        "text": "你去客串了三场戏，播出时只留下一个背影，观众却在弹幕里认出那是你。",
        "effects": {"changtiao": 2, "renqi": 4},
        "target": "one",
    },
    {
        "kind": "影视",
        "title": "角色被临时换掉",
        "text": "剧组临时换角，官宣名单里你的名字消失了，通告单上你的场次被一笔划掉。",
        "effects": {"chuangzuo": -4, "renqi": -5},
        "target": "one",
    },
    {
        "kind": "影视",
        "title": "杀青宴被导演点名夸",
        "text": "杀青宴上导演当着全组说「这孩子能处」，第二天就有人传你要接他的下一部。",
        "effects": {"chuangzuo": 3, "renqi": 5},
        "target": "one",
    },
    {
        "kind": "音乐",
        "title": "半夜爬上榜单的 demo",
        "text": "你随手发的一首 demo 凌晨爬上了榜单，评论区全是「这歌怎么突然会唱了」。",
        "effects": {"shengyue": 5, "renqi": 7},
        "target": "one",
    },
    {
        "kind": "音乐",
        "title": "音乐节破音切片",
        "text": "音乐节直播里你一句高音破了，切片被反复播放，粉丝替你解释说是耳返坏了。",
        "effects": {"shengyue": -4, "renqi": -4},
        "target": "one",
    },
    {
        "kind": "时尚",
        "title": "看秀同款售罄",
        "text": "你穿了件谁都没见过的外套去看秀，第二天同款售罄，品牌方直接邀你拍大片。",
        "effects": {"renqi": 6, "changtiao": 2},
        "target": "one",
    },
    {
        "kind": "时尚",
        "title": "红毯造型被嘲",
        "text": "你的红毯造型被时尚博主点名，说像「刚下夜班的打工人」，话题挂了一下午。",
        "effects": {"renqi": -5},
        "target": "one",
    },
    {
        "kind": "应援",
        "title": "粉丝包下一条街",
        "text": "粉丝给你包了一条街的灯箱，路人拍下来问「这谁啊」，你名字第一次被陌生人念出来。",
        "effects": {"renqi": 8},
        "target": "one",
    },
    {
        "kind": "应援",
        "title": "跟了三年的站子关站",
        "text": "跟了你三年的站子突然宣布关站，最后一条微博只有四个字：祝你好运。",
        "effects": {"renqi": -6},
        "target": "one",
    },
    {
        "kind": "争议",
        "title": "一句话被剪成标题",
        "text": "你在采访里随口一句被剪成了标题，营销号说你耍大牌，越解释越像在狡辩。",
        "effects": {"renqi": -8},
        "target": "one",
    },
    {
        "kind": "争议",
        "title": "素脸澄清反而圈粉",
        "text": "一段十分钟的澄清视频里你素着脸把话说完，路人反而觉得你挺实在。",
        "effects": {"renqi": 7},
        "target": "one",
    },
    {
        "kind": "私生",
        "title": "行程被扒到分钟",
        "text": "有人把你这周的全部行程精确到分钟发在了超话里，你连回家的路都不敢走直。",
        "effects": {"renqi": -5, "changtiao": -2},
        "target": "one",
    },
    {
        "kind": "黑料",
        "title": "出道前旧照被做成对比图",
        "text": "有人翻出你出道前的旧照做成对比图，配文「包装得真好」，你团队连夜开会。",
        "effects": {"renqi": -7},
        "target": "one",
    },
    {
        "kind": "黑料",
        "title": "前同事发长文",
        "text": "一个前同事发长文说你当年在组里爱摆架子，评论区吵成一锅粥，你一句话都没回。",
        "effects": {"renqi": -6, "chuangzuo": -2},
        "target": "one",
    },
    {
        "kind": "解约",
        "title": "合约到期谈判僵住",
        "text": "你和公司的合约到期了，续约谈崩在那儿，所有通告被按了暂停键。",
        "effects": {"renqi": -4, "changtiao": -3},
        "target": "one",
    },
    {
        "kind": "解约",
        "title": "开了自己的工作室",
        "text": "你宣布成立个人工作室，第一条动态是「以后自己说了算」，粉丝一夜涨了几十万。",
        "effects": {"renqi": 9, "chuangzuo": 2},
        "target": "one",
    },
    {
        "kind": "爆红",
        "title": "一个白眼成了表情包",
        "text": "你在综艺里一个翻白眼的表情被做成表情包传遍全网，连不看综艺的人都在用。",
        "effects": {"renqi": 12, "changtiao": 2},
        "target": "one",
    },
    {
        "kind": "综艺",
        "title": "常驻名单里没有你",
        "text": "你常驻的综艺新一季名单里没有你，节目组只说「档期原因」。",
        "effects": {"renqi": -6},
        "target": "one",
    },
    {
        "kind": "资源",
        "title": "副导演半夜的短信",
        "text": "副导演半夜发来一句「明天来试个镜，别跟公司说」，你盯着屏幕想了很久。",
        "effects": {"changtiao": 5},
        "target": "one",
    },
    {
        "kind": "恋情",
        "title": "同进一栋楼被拍",
        "text": "你和一个人连着两天被拍到走进同一栋楼，双方团队都没否认，也没承认。",
        "effects": {"renqi": 6},
        "target": "one",
    },
    {
        "kind": "翻车",
        "title": "口播念错品牌名",
        "text": "直播里你把赞助商的名字念错了两个字，弹幕刷得比你还快，品牌方没回应。",
        "effects": {"renqi": -5},
        "target": "one",
    },
    {
        "kind": "绯闻",
        "title": "和对手戏演员的合照",
        "text": "一张你和对戏演员并排站着的模糊合照被放出来，配文只有一个问号。",
        "effects": {"renqi": -4},
        "target": "one",
    },
    {
        "kind": "黑热搜",
        "title": "被挂上「不敬业」词条",
        "text": "一个匿名帖子说你拍戏用替身，词条挂了六个小时，剧组没人出来说话。",
        "effects": {"renqi": -7, "changtiao": -2},
        "target": "one",
    },
    {
        "kind": "塌房",
        "title": "商务一夜清零",
        "text": "合作方排队发来解约函，你微博首页的代言图全被撤了，像从没存在过。",
        "effects": {"renqi": -12},
        "target": "one",
    },
    {
        "kind": "爆红",
        "title": "路人拍的生图",
        "text": "有人在机场随手拍了一张你的生图，没滤镜没修音，转评赞一夜破了百万。",
        "effects": {"renqi": 9, "changtiao": 2},
        "target": "one",
    },
    {
        "kind": "资源",
        "title": "综艺常驻邀约",
        "text": "一档新综艺的制片人亲自打电话来，说这季就想找个「不像艺人的艺人」。",
        "effects": {"renqi": 5, "shengyue": 2},
        "target": "one",
    },
    {
        "kind": "综艺",
        "title": "被剪成搞笑担当",
        "text": "节目播出后你成了全片最出圈的那个，弹幕全在等你下一个表情。",
        "effects": {"renqi": 7, "wudao": 1},
        "target": "one",
    },
    {
        "kind": "时尚",
        "title": "被时尚杂志点名",
        "text": "一本杂志把你的私服评为本周最佳，编辑还专门写了段「这人不装」。",
        "effects": {"renqi": 5, "chuangzuo": 1},
        "target": "one",
    },
    {
        "kind": "应援",
        "title": "粉丝替你打抱不平",
        "text": "粉丝把某条造谣微博的举报量刷到了首页，平台最后删了帖，你只发了句「别累着」。",
        "effects": {"renqi": 4},
        "target": "one",
    },
    {
        "kind": "争议",
        "title": "被问到敏感问题",
        "text": "采访里记者问了个不好答的问题，你愣了两秒，笑着把话题绕回作品。",
        "effects": {"renqi": 2, "shengyue": 1},
        "target": "one",
    },
    {
        "kind": "私生",
        "title": "被跟到小区门口",
        "text": "有人跟到了你住的小区门口，保安拦下来的时候你已经在楼上报警了。",
        "effects": {"renqi": -4},
        "target": "one",
    },
    {
        "kind": "黑料",
        "title": "被剪辑成冲突片段",
        "text": "一段没头没尾的剪辑里你和工作人员像在吵架，实际上你在问对方要不要喝水。",
        "effects": {"renqi": -6},
        "target": "one",
    },
    {
        "kind": "音乐",
        "title": "被乐评人写长文",
        "text": "一个乐评人写了三千字夸你这首歌的结构，虽然你其实没想那么多。",
        "effects": {"shengyue": 6, "renqi": 3},
        "target": "one",
    },
    {
        "kind": "影视",
        "title": "试镜被刷",
        "text": "你为一角色准备了两个月，最后导演选了更有流量的那个，你只回了句「知道了」。",
        "effects": {"chuangzuo": -3, "renqi": -2},
        "target": "one",
    },
    {
        "kind": "代言",
        "title": "续约加价",
        "text": "品牌方主动提出续约并加价，说你的带货数据比预想的好太多。",
        "effects": {"renqi": 5},
        "target": "one",
    },
    {
        "kind": "解约",
        "title": "老东家发律师函",
        "text": "老东家发了律师函，说你违约，你团队把合同扫描件贴了出来，两边都在等对方先动。",
        "effects": {"renqi": -5, "chuangzuo": -2},
        "target": "one",
    },
]

# ---------------- 文案 ----------------
FORTUNES: List[str] = [
    "今天灵感爆棚，写歌手到擒来！",
    "舞台运势上佳，抽签容易出大数字～",
    "小心绯闻缠身，今天适合低调练功。",
    "贵人运强，比拼胜率+10%（玄学）。",
    "创作瓶颈期，但舞蹈手感绝佳。",
    "全能之日，四项皆宜冲刺。",
    "今天适合去撩一下某人，成功率略高。",
    "运势平平，但有人在偷偷看你。",
]

# ---------------- 人气 ----------------
# 人气是「路人盘」：AI 事件、发博、采访、通告都会动它，每天不营业会自然掉。
# 它不参与综合实力（段位只看四项），但会给比拼加成，也会让事件更容易找上你。
POP_INIT = 10

POP_TITLES: List[Tuple[int, str]] = [
    (0, "查无此人"),
    (20, "小有名气"),
    (60, "有点热度"),
    (120, "当红"),
    (200, "顶流"),
    (300, "国民级"),
    (400, "传说"),
]

POP_DECAY_KEEP = 20      # 低于这个人气就不再自然衰减
POP_DECAY_PERCENT = 2    # 每天掉 2%（至少 1）

POP_PK_DIVISOR = 2400    # 240 人气 ≈ +10%，360 人气封顶 +15%
POP_PK_CAP = 0.15

# ---------------- 通告剧本（AI 写幕，这里只给设定） ----------------
DRAMA_SETUPS: List[dict] = [
    {"title": "长夜未眠", "role": "民国谍战片里潜伏在敌营的双面特工"},
    {"title": "春江月", "role": "古装剧里刚被废黜、还没认输的太子妃"},
    {"title": "第七封信", "role": "悬疑片里唯一活着、但没人相信的证人"},
    {"title": "她不说话", "role": "文艺片里失去声音、靠手指说话的钢琴师"},
    {"title": "狼烟", "role": "战争片里混在撤退队伍中的随军记者"},
    {"title": "出租屋", "role": "都市剧里北漂八年、明天就要交不起房租的群演"},
    {"title": "星落", "role": "科幻片里最后一位醒来的宇航员"},
    {"title": "蜜糖陷阱", "role": "偶像剧里人人喊打、其实最清醒的女二号"},
    {"title": "旧照片", "role": "家庭片里返乡整理遗物、发现秘密的长子"},
    {"title": "午夜电台", "role": "深夜电台里接起最后一通电话的主持人"},
]

# 模型写不出剧本时的兜底结局
FALLBACK_ENDING = "导演喊了收工。这部戏最后剪成了什么样，谁也说不准，但你在片场熬过的那些夜是真的。"

# 发博兜底评论（模型不可用时）
FALLBACK_POST_COMMENTS: List[str] = [
    "蹲一个解释，这波操作看不懂。",
    "说实话有点东西，但还是那句话：作品说话。",
    "别发微博了，好好练功吧。",
    "营销号已经在写你了，注意点。",
]

# 搭讪兜底（NPC 没有台词可用时）
FALLBACK_CHAT_REPLY = "……嗯，我在听。"

# ---------------- 结果点评（AI 对当事人随口说一句） ----------------
# 意思是：每次出结果，有概率让「群里那位嘴碎的经纪人人格」点评一句。
# 模型不可用、或返回空/太长时用这些兜底，保证这件事本身不依赖模型。
FLAVOR_GOOD: List[str] = [
    "这波可以，别飘，明天照样练。",
    "状态在线，我记你一笔。",
    "有点东西，可惜还差一口气。",
    "行啊，这运气我替你高兴。",
    "今晚别发微博，先谢天谢地。",
]

FLAVOR_BAD: List[str] = [
    "……要不今天先到这儿？",
    "别灰心，娱乐圈从不缺翻盘故事。",
    "这运气，建议你去拜一拜。",
    "输赢正常，别上热搜就行。",
    "明天早课别迟到，掰回来。",
]

FLAVOR_FLAT: List[str] = [
    "稳，稳得像白开水。",
    "不功不过，观众记不住你。",
    "这数据放群里不算显眼。",
    "还没到能吹的程度，继续。",
]

# ---------------- 连签奖励 ----------------
# 天数 -> (人气, 四项各加, 说明)。只在「正好到这一档」的那天发一次，之后每天走普通签到。
STREAK_REWARDS: Dict[int, Tuple[int, int, str]] = {
    3: (3, 0, "连签 3 天，开始有点职业素养了"),
    7: (6, 2, "连签 7 天，一周不断更，粉丝开始盯你了"),
    14: (10, 3, "连签半个月，这股狠劲儿少见"),
    30: (20, 5, "连签 30 天，你已经不是新人了"),
}

# ---------------- 成就 ----------------
# key -> (图标, 名字, 条件说明)。条件都在 main._ach_hits 里即时判定。
ACHIEVEMENTS: Dict[str, Tuple[str, str, str]] = {
    "debut": ("🎬", "初登场", "第一次以艺人身份出道"),
    "first_sign": ("📆", "打卡第一天", "完成第一次签到"),
    "streak7": ("🔥", "自律成瘾", "连续签到 7 天"),
    "pop100": ("📣", "有点热度", "人气达到 100"),
    "pop500": ("🌋", "全民热议", "人气达到 500"),
    "diamond": ("💎", "实力派", "段位到达「实力明星」"),
    "king": ("👑", "顶流巨星", "段位到达「顶流巨星」"),
    "first_win": ("⚔️", "首胜", "赢下第一场比拼"),
    "couple": ("💞", "官宣", "在群里谈上恋爱"),
    "married": ("💍", "修成正果", "和某个人结婚"),
    "rich": ("💰", "小富豪", "星币存到 1000"),
    "shopper": ("🛍️", "会花钱", "第一次在礼品店买东西"),
    "allround": ("🏅", "四项全能", "四项属性都达到 300"),
    "streak30": ("🗓️", "铁打的艺人", "连续签到 30 天"),
    "sixdim": ("🧭", "六边形战士", "四项属性各达到 600"),
    "legend": ("⚡", "不灭神话", "段位到达「不灭神话」"),
    "warlord": ("🥇", "常胜将军", "累计赢下 20 场比拼"),
    "fighter": ("🩹", "屡败屡战", "累计输掉 10 场比拼"),
    "tycoon": ("🏦", "豪门", "星币存到 5000"),
    "famous": ("🌟", "国民度", "粉丝突破 1000 万"),
    "gifter": ("🎁", "送礼狂魔", "累计送出 30 份礼物"),
    "busy": ("🏃", "劳模", "本月参加活动满 40 次"),
    "poster": ("📱", "营业狂", "累计发博 30 条"),
    "collector": ("🎒", "收藏癖", "背包里同时有 5 种东西"),
    "veteran": ("🎖️", "元老", "出道满 30 天"),
}

# ---------------- NPC 主动搭话 ----------------
# 模型不可用时用这些兜底：{npc} 会替换成 NPC 名字
TALK_OPEN_FALLBACK: List[str] = [
    "{npc} 在走廊里叫住你：「喂，你就是最近老上热搜那个？」",
    "{npc} 把耳机摘下来，看了你两秒：「你那场舞台，我看了。」",
    "{npc} 递过来一瓶水：「练到这么晚，不要命了？」",
    "{npc} 靠在门框上：「听说你要跟我抢那个角色？」",
    "{npc} 从化妆间出来，撞见你：「……你在这站多久了。」",
    "{npc} 把手机屏幕转过来：「这条通稿，是你团队发的？」",
]

TALK_OPTIONS_FALLBACK: List[List[str]] = [
    ["抬头迎上他的目光", "假装看手机走开", "笑一下，不接话"],
    ["认真解释自己怎么练的", "轻描淡写说「还行」", "反问他为什么在意"],
    ["把水接过来道谢", "说自己还能再练两小时", "问他是不是也在赶通告"],
]

# NPC 对这次回答的反应（模型不可用时用）
TALK_REPLY_FALLBACK: List[str] = [
    "{npc} 挑了下眉，没再说什么，转身走了。",
    "{npc} 盯了你一会儿，忽然笑了一声：「有点意思。」",
    "{npc} 抱着手臂点头：「行，那我等你。」",
    "{npc} 沉默两秒，把话咽了回去：「算了，练你的吧。」",
]

# ---------------- 星币 / 事务所 ----------------
COIN_SIGN = 8
COIN_ACTIVITY = 12
COIN_POST = 6
COIN_PK_WIN = 10

# 等级 -> (升到这一级的花费, 每天自动通告的星币, 说明)
ASSISTANT_LEVELS: Dict[int, Tuple[int, int, str]] = {
    1: (300, 12, "助理小周：每天帮你接一个通告"),
    2: (900, 26, "助理阿凯：手里开始有资源了"),
    3: (2200, 45, "经纪人大姐：通告排到下周"),
}
ASSISTANT_MAX = 3

FAN_PER_POP = 37  # 人气换算粉丝的系数
FAN_CHEER_COST = 30  # 粉丝团应援花费
FAN_CHEER_POP = (2, 4)  # 应援加的人气区间

# ---------------- 热搜榜 ----------------
HOT_TOP_N = 5
# 名次 -> 每小时首次看榜加的人气（只有前 3 有）
HOT_REWARD: Dict[int, int] = {1: 3, 2: 2, 3: 1}

# ---------------- 月度结算 ----------------
MONTHLY_BASE = 20  # 年终奖底薪
MONTHLY_SIGN = 8  # 每签到一天折合的星币
MONTHLY_ACT = 4  # 每次活动
MONTHLY_WIN = 10  # 每场比拼胜利

# ---------------- NPC 邀约 ----------------
INVITE_TTL_MIN = 30
INVITE_FALLBACK: List[str] = [
    "{npc}：明天那场戏缺个对手，你来不来？",
    "{npc}：我这儿有个通告档期撞了，你要不要接？",
    "{npc}：路演缺人，我把你名字报上去了，别丢我的脸。",
    "{npc}：新戏试镜，我顺手推了你一把。",
]
FOLLOWUP_GOOD: List[str] = [
    "{npc} 隔天在群里@你：「昨天那句话，我记住了。」顺手把一个通告推给了你。",
    "{npc} 第二天发来一条消息：「那事我帮你问过了，成了。」",
]
FOLLOWUP_BAD: List[str] = [
    "{npc} 隔天见到你，只是点了下头就走了。",
    "{npc} 后来没再找过你。",
]


# ---------------- 内容池扩展（素材见 game/content.py） ----------------
from . import content as _content  # noqa: E402  （放在末尾，避免循环引用）

EVENT_KINDS = sorted(set(EVENT_KINDS) | set(_content.MORE_EVENT_KINDS))
EVENT_POLARITY = {**_content.MORE_EVENT_POLARITY, **EVENT_POLARITY}
for _k in EVENT_KINDS:
    EVENT_POLARITY.setdefault(_k, 0)

FALLBACK_EVENTS = list(FALLBACK_EVENTS) + list(_content.MORE_FALLBACK_EVENTS)
DRAMA_SETUPS = list(DRAMA_SETUPS) + list(_content.MORE_DRAMA_SETUPS)
FALLBACK_POST_COMMENTS = list(FALLBACK_POST_COMMENTS) + list(_content.MORE_POST_COMMENTS)
FLAVOR_GOOD = list(FLAVOR_GOOD) + list(_content.MORE_FLAVOR_GOOD)
FLAVOR_BAD = list(FLAVOR_BAD) + list(_content.MORE_FLAVOR_BAD)
FLAVOR_FLAT = list(FLAVOR_FLAT) + list(_content.MORE_FLAVOR_FLAT)
TALK_OPEN_FALLBACK = list(TALK_OPEN_FALLBACK) + list(_content.MORE_TALK_OPEN)
TALK_OPTIONS_FALLBACK = list(TALK_OPTIONS_FALLBACK) + list(_content.MORE_TALK_OPTIONS)
TALK_REPLY_FALLBACK = list(TALK_REPLY_FALLBACK) + list(_content.MORE_TALK_REPLY)
FORTUNES = list(FORTUNES) + list(_content.MORE_FORTUNES)
INVITE_FALLBACK = list(INVITE_FALLBACK) + list(_content.MORE_INVITE_FALLBACK)
FOLLOWUP_GOOD = list(FOLLOWUP_GOOD) + list(_content.MORE_FOLLOWUP_GOOD)
FOLLOWUP_BAD = list(FOLLOWUP_BAD) + list(_content.MORE_FOLLOWUP_BAD)
