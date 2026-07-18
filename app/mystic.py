"""神秘的东方力量 — 内置万年历推演 + 命盘生成(纯娱乐,无任何科学依据)。

全部本地确定性计算,不依赖外部接口:
- 日干支:以 1949-10-01(甲子日)为锚点做 60 甲子模运算(已用 2000-01-01=戊午 验证)
- 农历:zhdate(1900-2100)
- 建除十二神:建星 =(日支 − 月建支)mod 12;吉凶按口诀「建满平收黑,除危定执黄,
  成开皆可用,闭破不相当」
- 命盘:SHA-256(姓名|农历生辰|性别|出生地|当日干支建星|首盘 slug)为种子,
  结合各盘口时辰五行与年命五行的生克关系,推演 50 盘方向与星级
同一个人在同一天启动,命盘完全一致(可复现)。
"""
import hashlib
import json
import random
import time
from datetime import date, datetime, timedelta, timezone

from zhdate import ZhDate

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
BRANCH_ELEM = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
               "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
               "戌": "土", "亥": "水"}
STEM_ELEM = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
             "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 我生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}      # 我克
JIANXING = "建除满平定执破危成收开闭"
LUCKY_JX = set("除危定执成开")            # 黄道;建满平收黑,闭破不相当
ANIMALS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
_ANCHOR = date(1949, 10, 1)               # 甲子日锚点

YI_POOL = ["纳财", "开市", "交易", "立券", "求财", "开仓", "会友", "出行"]
JI_POOL = ["追高", "重仓", "逆势", "扛单", "梭哈", "借贷", "夜盘冲动"]


def day_ganzhi(d):
    idx = (d - _ANCHOR).days % 60
    return STEMS[idx % 10] + BRANCHES[idx % 12], idx


def year_ganzhi(year):
    return STEMS[(year - 4) % 10] + BRANCHES[(year - 4) % 12]


def jianxing_of(d, lunar_month):
    """建星:正月建寅,月建支 = (寅 + 农历月 - 1);建星 = 日支 - 月建支。"""
    _, idx = day_ganzhi(d)
    day_branch = idx % 12
    month_jian = (2 + lunar_month - 1) % 12
    return JIANXING[(day_branch - month_jian) % 12]


def almanac(d=None):
    """今日黄历(北京时间)。"""
    bj = datetime.now(timezone(timedelta(hours=8)))
    d = d or bj.date()
    z = ZhDate.from_datetime(datetime(d.year, d.month, d.day))
    gz, _ = day_ganzhi(d)
    jx = jianxing_of(d, z.lunar_month)
    lucky = jx in LUCKY_JX
    rng = random.Random(f"almanac|{d.isoformat()}")
    return {
        "date": d.isoformat(),
        "lunar": z.chinese(),
        "day_ganzhi": gz,
        "jianxing": jx,
        "is_lucky_day": lucky,
        "label": "黄道吉日" if lucky else "黑道日",
        "yi": rng.sample(YI_POOL, 3),
        "ji": rng.sample(JI_POOL, 3),
    }


def profile_fate(name, birth_ymd, gender, birthplace):
    """农历生辰 + 年命五行 + 生肖。birth_ymd: 'YYYY-MM-DD'"""
    y, m, dd = (int(x) for x in birth_ymd.split("-"))
    z = ZhDate.from_datetime(datetime(y, m, dd))
    ygz = year_ganzhi(z.lunar_year)
    elem = STEM_ELEM[ygz[0]]
    animal = ANIMALS[(z.lunar_year - 4) % 12]
    return {"lunar_birth": z.chinese(), "year_ganzhi": ygz,
            "element": elem, "animal": animal,
            "yin_yang": "阳" if STEMS.index(ygz[0]) % 2 == 0 else "阴"}


def _relation(branch_elem, my_elem):
    if branch_elem == my_elem:
        return "比和", 0.06
    if SHENG[branch_elem] == my_elem:
        return "相生", 0.14
    if SHENG[my_elem] == branch_elem:
        return "泄气", -0.05
    if KE[branch_elem] == my_elem:
        return "相克", -0.14
    return "受制", 0.03                    # 我克之,得财


def _shichen(ts):
    """北京时间时辰地支。"""
    bj = datetime.fromtimestamp(ts, timezone(timedelta(hours=8)))
    return BRANCHES[((bj.hour + 1) // 2) % 12]


def build_plan(name, birth_ymd, gender, birthplace, first_start_ts, n=50):
    fate = profile_fate(name, birth_ymd, gender, birthplace)
    alm = almanac()
    seed_src = "|".join([name.strip(), fate["lunar_birth"], gender,
                         birthplace.strip(), alm["day_ganzhi"], alm["jianxing"],
                         str(first_start_ts)])
    seed = hashlib.sha256(seed_src.encode("utf-8")).hexdigest()
    rng = random.Random(seed)
    luck_boost = 0.04 if alm["is_lucky_day"] else -0.02
    entries = []
    for i in range(n):
        start = first_start_ts + i * 300
        br = _shichen(start)
        be = BRANCH_ELEM[br]
        rel, bias = _relation(be, fate["element"])
        p_up = min(0.85, max(0.15, 0.5 + bias + luck_boost
                             + rng.uniform(-0.18, 0.18)))
        side = "up" if rng.random() < p_up else "down"
        conf = abs(p_up - 0.5)
        stars = 1 + min(4, int(conf * 12))
        reason = (f"🔮{br}时{be}气{rel}{fate['element']}命·"
                  f"{'吉星高照' if stars >= 4 else '卦象' + ('偏阳' if side == 'up' else '偏阴')}"
                  f"·{'★' * stars}")
        entries.append({"i": i + 1, "slug": f"btc-updown-5m-{start}",
                        "start_ts": start, "side": side, "stars": stars,
                        "reason": reason})
    return {"created": int(time.time()), "seed": seed[:16], "fate": fate,
            "almanac": alm, "profile": {"name": name.strip()[:20],
                                        "birth": birth_ymd, "gender": gender,
                                        "birthplace": birthplace.strip()[:30]},
            "entries": entries}
