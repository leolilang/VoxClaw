"""本地提醒工具：解析口语化定时提醒，并持久化待触发提醒。"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import PROJECT_ROOT, ReminderToolConfig

REMINDER_KEYWORDS = ("提醒", "叫我", "喊我", "闹钟", "定时", "倒计时")
RELATIVE_SUFFIX = r"(?:之后|以后|后面|后)"
CANCEL_KEYWORDS = ("取消", "删除", "不用", "别", "不要")
QUERY_KEYWORDS = ("查询", "查一下", "查看", "看看", "看一下", "列出", "还有", "有哪些", "有什么", "多少", "几个")
TASK_KEYWORDS = ("提醒", "任务", "闹钟", "定时", "倒计时", "待办")
ALL_KEYWORDS = ("全部", "所有", "全部的", "所有的")
PERIODS = ("凌晨", "早上", "早晨", "上午", "中午", "下午", "傍晚", "晚上", "夜里", "夜间")
ORDINALS = ("第一个", "第二个", "第三个", "第四个", "第五个", "第六个", "第七个", "第八个", "第九个", "第十个")


@dataclass
class Reminder:
    id: str
    due_at: str
    message: str
    created_at: str
    source_text: str


class ReminderTool:
    def __init__(self, config: ReminderToolConfig):
        self._config = config
        self._timezone = ZoneInfo(config.timezone)
        self._storage_path = resolve_storage_path(config.storage_path)
        self._reminders: list[Reminder] = []
        self._load()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def check_interval_s(self) -> float:
        return self._config.check_interval_s

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False
        compact = normalize_text(text)
        if is_query_request(compact):
            return True
        if is_cancel_request(compact):
            return True
        if any(keyword in compact for keyword in REMINDER_KEYWORDS):
            return has_time_expression(compact)
        return bool(parse_due_time(compact, datetime.now(self._timezone)))

    def handle(self, text: str) -> str:
        compact = normalize_text(text)
        if is_query_request(compact):
            return self.list_reply()
        if is_cancel_request(compact):
            return self.cancel_from_text(compact)
        _, reply = self.create_from_text(text)
        return reply

    def create_from_text(self, text: str) -> tuple[Reminder, str]:
        now = datetime.now(self._timezone)
        compact = normalize_text(text)
        due_at = parse_due_time(compact, now)
        if due_at is None:
            raise ValueError("没有识别到提醒时间")
        message = extract_message(compact)
        reminder = Reminder(
            id=str(uuid.uuid4()),
            due_at=due_at.isoformat(),
            message=message,
            created_at=now.isoformat(),
            source_text=text,
        )
        self._reminders.append(reminder)
        self._reminders.sort(key=lambda item: item.due_at)
        self._save()
        return reminder, build_confirmation(reminder, self._timezone)

    def update_message(self, reminder_id: str, message: str) -> Reminder | None:
        message = cleanup_message(message)
        for reminder in self._reminders:
            if reminder.id == reminder_id:
                reminder.message = message
                self._save()
                return reminder
        return None

    def confirmation(self, reminder: Reminder) -> str:
        return build_confirmation(reminder, self._timezone)

    def cancel_from_text(self, text: str) -> str:
        compact = normalize_text(text)
        if not self._reminders:
            return "现在没有待取消的提醒。"

        if any(keyword in compact for keyword in ALL_KEYWORDS):
            self._reminders = []
            self._save()
            return "好的，我已经取消了。"

        now = datetime.now(self._timezone)
        target_time = parse_due_time(compact, now)
        if target_time is not None:
            index = min(
                range(len(self._reminders)),
                key=lambda i: abs(datetime.fromisoformat(self._reminders[i].due_at) - target_time),
            )
        else:
            index = min(
                range(len(self._reminders)),
                key=lambda i: datetime.fromisoformat(self._reminders[i].due_at),
            )
        self._reminders.pop(index)
        self._save()
        return "好的，我已经取消了。"

    def list_reply(self) -> str:
        if not self._reminders:
            return "现在没有待提醒的任务。"

        self._reminders.sort(key=lambda item: item.due_at)
        count = len(self._reminders)
        items = [build_list_item(item, index, self._timezone) for index, item in enumerate(self._reminders)]
        return f"你现在有{count}个提醒。" + "；".join(items) + "。"

    def pop_due(self, now: datetime | None = None) -> list[Reminder]:
        now = now or datetime.now(self._timezone)
        due: list[Reminder] = []
        pending: list[Reminder] = []
        for reminder in self._reminders:
            due_at = datetime.fromisoformat(reminder.due_at)
            if due_at <= now:
                due.append(reminder)
            else:
                pending.append(reminder)
        if due:
            self._reminders = pending
            self._save()
        return due

    def _load(self):
        if not self._storage_path.exists():
            self._reminders = []
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._reminders = [Reminder(**item) for item in data if isinstance(item, dict)]
        except Exception:
            self._reminders = []

    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps([asdict(item) for item in self._reminders], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def resolve_storage_path(path: str) -> Path:
    storage = Path(path)
    if not storage.is_absolute():
        storage = PROJECT_ROOT / storage
    return storage


def normalize_text(text: str) -> str:
    return re.sub(r"[，。！？、\s?？!！]", "", text)


def has_time_expression(text: str) -> bool:
    return parse_due_time(text, datetime.now(ZoneInfo("Asia/Shanghai"))) is not None


def is_cancel_request(text: str) -> bool:
    return any(keyword in text for keyword in CANCEL_KEYWORDS) and any(
        keyword in text for keyword in REMINDER_KEYWORDS
    )


def is_query_request(text: str) -> bool:
    if "现在有哪些任务" in text or "现在有什么任务" in text:
        return True
    return any(keyword in text for keyword in QUERY_KEYWORDS) and any(
        keyword in text for keyword in TASK_KEYWORDS
    )


def parse_due_time(text: str, now: datetime) -> datetime | None:
    return parse_relative_time(text, now) or parse_absolute_time(text, now)


def parse_relative_time(text: str, now: datetime) -> datetime | None:
    if "半小时后" in text or "半个小时后" in text:
        return now + timedelta(minutes=30)
    if "一刻钟后" in text:
        return now + timedelta(minutes=15)
    match = re.search(relative_time_pattern(), text)
    if not match:
        match = re.search(
            r"(?P<num>半|\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+)(?:个)?(?P<unit>秒钟|秒|分钟|分|小时|钟头|天)(?:的)?(?:闹钟|倒计时)",
            text,
        )
    if not match:
        return None
    amount = parse_number(match.group("num"))
    unit = match.group("unit")
    if amount <= 0:
        return None
    if unit in ("秒", "秒钟"):
        return now + timedelta(seconds=amount)
    if unit in ("分", "分钟"):
        return now + timedelta(minutes=amount)
    if unit in ("小时", "钟头"):
        return now + timedelta(hours=amount)
    if unit == "天":
        return now + timedelta(days=amount)
    return None


def parse_absolute_time(text: str, now: datetime) -> datetime | None:
    match = re.search(
        r"(?P<day>今天|明天|后天|大后天)?(?P<period>凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|夜里|夜间)?(?P<hour>\d{1,2}|[零〇一二两三四五六七八九十十一十二]+)点(?P<minute>半|一刻|三刻|\d{1,2}分?|[零〇一二两三四五六七八九十]+分?)?",
        text,
    )
    if not match:
        return None
    day = match.group("day") or "今天"
    period = match.group("period") or ""
    hour = int(parse_number(match.group("hour")))
    minute = parse_minute(match.group("minute"))
    hour = adjust_hour_by_period(hour, period)
    if hour > 23 or minute > 59:
        return None

    offset = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}[day]
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=offset)
    if match.group("day") is None and due <= now:
        due += timedelta(days=1)
    return due


def parse_minute(value: str | None) -> int:
    if not value:
        return 0
    if value == "半":
        return 30
    if value == "一刻":
        return 15
    if value == "三刻":
        return 45
    value = value.removesuffix("分")
    return int(parse_number(value))


def adjust_hour_by_period(hour: int, period: str) -> int:
    if period in ("下午", "傍晚", "晚上", "夜里", "夜间") and hour < 12:
        return hour + 12
    if period == "中午" and hour < 11:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def parse_number(text: str) -> float:
    if text == "半":
        return 0.5
    try:
        return float(text)
    except ValueError:
        pass
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in digits:
        return float(digits[text])
    if text == "十":
        return 10.0
    if "百" in text:
        left, _, right = text.partition("百")
        total = (digits.get(left, 1) if left else 1) * 100
        return float(total + int(parse_number(right)) if right else total)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    total = 0
    for char in text:
        total = total * 10 + digits.get(char, 0)
    return float(total)


def extract_message(text: str) -> str:
    for marker in ("提醒我", "叫我", "喊我"):
        if marker in text:
            content = text.split(marker, 1)[1]
            if content:
                return cleanup_message(remove_time_expressions(content))
    content = remove_time_expressions(text)
    return cleanup_message(content)


def remove_time_expressions(text: str) -> str:
    text = re.sub(relative_time_pattern(named=False), "", text)
    text = re.sub(r"(?:半|\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+)(?:个)?(?:秒钟|秒|分钟|分|小时|钟头|天)(?:的)?(?:闹钟|倒计时)", "", text)
    text = re.sub(r"(?:今天|明天|后天|大后天)?(?:凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|夜里|夜间)?(?:\d{1,2}|[零〇一二两三四五六七八九十十一十二]+)点(?:半|一刻|三刻|\d{1,2}分?|[零〇一二两三四五六七八九十]+分?)?", "", text)
    return re.sub(r"提醒|叫我|喊我|闹钟|定时|倒计时|的时候|时候", "", text)


def relative_time_pattern(named: bool = True) -> str:
    number = r"半|\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+"
    unit = r"秒钟|秒|分钟|分|小时|钟头|天"
    if named:
        return rf"(?:再过|过)?(?P<num>{number})(?:个)?(?P<unit>{unit}){RELATIVE_SUFFIX}"
    return rf"(?:再过|过)?(?:{number})(?:个)?(?:{unit}){RELATIVE_SUFFIX}"


def cleanup_message(content: str) -> str:
    content = re.sub(r"^(帮我|请|麻烦你|设置|设个|定个|定一个|一个|一下)+", "", content)
    content = re.sub(r"(一下|一下子)$", "", content)
    content = content.strip("，。！？、,.!? ")
    return content or "时间到了"


def build_confirmation(reminder: Reminder, timezone: ZoneInfo) -> str:
    due = datetime.fromisoformat(reminder.due_at).astimezone(timezone)
    now = datetime.now(timezone)
    day = "今天" if due.date() == now.date() else "明天" if due.date() == (now + timedelta(days=1)).date() else f"{due.month}月{due.day}日"
    time_text = f"{due.hour}点{due.minute:02d}分"
    delay_text = format_delay(due - now)
    if delay_text:
        if reminder.message == "时间到了":
            return f"好的，我将在{delay_text}后提醒你。"
        return f"好的，我将在{delay_text}后提醒你：{reminder.message}。"
    if reminder.message == "时间到了":
        return f"好的，我会在{day}{time_text}提醒你。"
    return f"好的，我会在{day}{time_text}提醒你：{reminder.message}。"


def build_list_item(reminder: Reminder, index: int, timezone: ZoneInfo) -> str:
    due = datetime.fromisoformat(reminder.due_at).astimezone(timezone)
    prefix = ORDINALS[index] if index < len(ORDINALS) else f"第{index + 1}个"
    time_text = format_due_time_for_speech(due, timezone)
    if reminder.message == "时间到了":
        return f"{prefix}，{time_text}提醒你"
    return f"{prefix}，{time_text}提醒你：{reminder.message}"


def format_due_time_for_speech(due: datetime, timezone: ZoneInfo) -> str:
    now = datetime.now(timezone)
    if due.date() == now.date():
        day = "今天"
    elif due.date() == (now + timedelta(days=1)).date():
        day = "明天"
    elif due.date() == (now + timedelta(days=2)).date():
        day = "后天"
    else:
        day = f"{due.month}月{due.day}日"
    minute_text = "" if due.minute == 0 else f"{due.minute:02d}分"
    return f"{day}{due.hour}点{minute_text}"


def format_delay(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 60:
        return f"{total_seconds}秒"
    total_minutes = round(total_seconds / 60)
    if total_minutes < 60:
        return f"{total_minutes}分钟"
    if total_minutes < 24 * 60:
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 0:
            return f"{hours}小时"
        return f"{hours}小时{minutes}分钟"
    return ""


def build_due_speech(reminder: Reminder) -> str:
    if reminder.message == "时间到了":
        return "时间到了，我来提醒你了。"
    return f"时间到了，提醒你：{reminder.message}。"
