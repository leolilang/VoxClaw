"""本地日历/时间工具：回答日期、星期、当前时间等问题。"""

from __future__ import annotations

import calendar as py_calendar
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config.settings import CalendarToolConfig

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAY_ALIASES = {
    "一": 0, "1": 0, "二": 1, "2": 1, "三": 2, "3": 2, "四": 3, "4": 3,
    "五": 4, "5": 4, "六": 5, "6": 5, "日": 6, "天": 6, "七": 6, "7": 6,
}
CHINESE_MONTHS = {
    "一": 1, "正": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
}
CALENDAR_INTENT_KEYWORDS = (
    "星期", "周几", "礼拜", "几号", "几日", "日期", "几月几", "多少号", "什么日子",
    "现在几点", "几点了", "当前时间", "现在时间", "几点钟", "今年", "明年", "去年",
    "这个月", "本月", "下个月", "上个月", "月有多少天", "多少天", "有几天",
)


@dataclass
class CalendarQuery:
    target: datetime
    relation: str
    wants_time: bool = False
    wants_weekday: bool = False
    wants_date: bool = False
    wants_year: bool = False
    wants_month_days: bool = False


class CalendarTool:
    def __init__(self, config: CalendarToolConfig):
        self._config = config

    @property
    def available(self) -> bool:
        return self._config.enabled

    def matches(self, text: str) -> bool:
        if not self._config.enabled:
            return False
        compact = normalize_text(text)
        if any(keyword in compact for keyword in CALENDAR_INTENT_KEYWORDS):
            return True
        return bool(parse_weekday_target(compact, datetime.now(ZoneInfo(self._config.timezone))))

    def reply(self, text: str) -> str:
        now = datetime.now(ZoneInfo(self._config.timezone))
        compact = normalize_text(text)
        query = parse_calendar_query(compact, now)
        return format_calendar_reply(query, now)


def normalize_text(text: str) -> str:
    return re.sub(r"[，。！？、\s?？!！]", "", text)


def parse_calendar_query(text: str, now: datetime) -> CalendarQuery:
    if "明年" in text and not any(keyword in text for keyword in ("几号", "几日", "星期", "周", "礼拜", "月")):
        return CalendarQuery(now.replace(year=now.year + 1), "明年", wants_year=True)
    if "去年" in text and not any(keyword in text for keyword in ("几号", "几日", "星期", "周", "礼拜", "月")):
        return CalendarQuery(now.replace(year=now.year - 1), "去年", wants_year=True)
    if "今年" in text and not any(keyword in text for keyword in ("几号", "几日", "星期", "周", "礼拜", "月")):
        return CalendarQuery(now, "今年", wants_year=True)

    if any(keyword in text for keyword in ("现在几点", "几点了", "当前时间", "现在时间", "几点钟")):
        return CalendarQuery(now, "现在", wants_time=True, wants_date="今天" in text or "日期" in text, wants_weekday="星期" in text or "周" in text)

    month_days = parse_month_days_query(text, now)
    if month_days:
        return month_days

    weekday_target = parse_weekday_target(text, now)
    if weekday_target:
        target, relation = weekday_target
        return CalendarQuery(
            target,
            relation,
            wants_weekday="星期" in text or "周" in text or "礼拜" in text or "什么日子" in text,
            wants_date="几号" in text or "几日" in text or "日期" in text or "多少号" in text or "是几" in text or "什么日子" in text,
        )

    target, relation = parse_relative_day(text, now)
    return CalendarQuery(
        target,
        relation,
        wants_weekday="星期" in text or "周几" in text or "礼拜" in text or "什么日子" in text,
        wants_date="几号" in text or "几日" in text or "日期" in text or "多少号" in text or "几月几" in text or "什么日子" in text,
        wants_year="今年" in text or "明年" in text or "去年" in text,
    )


def parse_relative_day(text: str, now: datetime) -> tuple[datetime, str]:
    mapping = [
        ("大后天", 3), ("后天", 2), ("明天", 1), ("今天", 0),
        ("大前天", -3), ("前天", -2), ("昨天", -1),
    ]
    for label, offset in mapping:
        if label in text:
            return now + timedelta(days=offset), label
    return now, "今天"


def parse_weekday_target(text: str, now: datetime) -> tuple[datetime, str] | None:
    match = re.search(r"(?:(下下|下个|下|本|这|这个|上个|上)?(?:星期|周|礼拜))([一二三四五六日天七1-7])", text)
    if not match:
        return None
    prefix = match.group(1) or ""
    weekday = WEEKDAY_ALIASES[match.group(2)]
    current = now.weekday()

    if prefix == "下下":
        delta = (weekday - current) + 14
        relation = f"下下{WEEKDAYS[weekday]}"
    elif prefix in ("下个", "下"):
        delta = (weekday - current) + 7
        relation = f"下{WEEKDAYS[weekday]}"
    elif prefix in ("上个", "上"):
        delta = (weekday - current) - 7
        relation = f"上{WEEKDAYS[weekday]}"
    elif prefix in ("本", "这", "这个"):
        delta = weekday - current
        relation = f"本{WEEKDAYS[weekday]}"
    else:
        delta = weekday - current
        if delta < 0:
            delta += 7
        relation = WEEKDAYS[weekday]
    return now + timedelta(days=delta), relation


def parse_month_days_query(text: str, now: datetime) -> CalendarQuery | None:
    if "月" not in text or not any(keyword in text for keyword in ("多少天", "几天", "有几天")):
        return None
    year = now.year
    month = now.month
    relation = "这个月"
    if "下个月" in text:
        month += 1
        relation = "下个月"
    elif "上个月" in text:
        month -= 1
        relation = "上个月"
    elif "明年" in text:
        year += 1
        relation = "明年这个月"
    elif "去年" in text:
        year -= 1
        relation = "去年这个月"

    match = re.search(r"(\d{1,2})月", text)
    if match:
        month = int(match.group(1))
        relation = f"{month}月"
    else:
        chinese_match = re.search(r"(十一|十二|十|正|一|二|三|四|五|六|七|八|九)月", text)
        if chinese_match:
            month = CHINESE_MONTHS[chinese_match.group(1)]
            relation = f"{month}月"
    if month > 12:
        year += 1
        month = 1
    elif month < 1:
        year -= 1
        month = 12
    target = now.replace(year=year, month=month, day=1)
    return CalendarQuery(target, relation, wants_month_days=True)


def format_calendar_reply(query: CalendarQuery, now: datetime) -> str:
    target = query.target
    date_text = f"{target.year}年{target.month}月{target.day}日"
    weekday = WEEKDAYS[target.weekday()]

    if query.wants_time:
        time_text = f"{now.hour}点{now.minute:02d}分"
        if query.wants_date or query.wants_weekday:
            return f"现在是{date_text}，{weekday}，{time_text}。"
        return f"现在是{time_text}。"

    if query.wants_month_days:
        days = py_calendar.monthrange(target.year, target.month)[1]
        return f"{query.relation}是{target.year}年{target.month}月，一共有{days}天。"

    if query.wants_year and not query.wants_date and not query.wants_weekday:
        return f"{query.relation}是{target.year}年。"

    if query.wants_weekday and not query.wants_date:
        return f"{query.relation}是{weekday}。"
    if query.wants_date and not query.wants_weekday:
        return f"{query.relation}是{date_text}。"
    return f"{query.relation}是{date_text}，{weekday}。"
