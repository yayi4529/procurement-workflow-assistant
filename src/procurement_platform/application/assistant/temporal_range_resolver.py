import calendar
import re
from datetime import date, datetime, time, timedelta
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class DateTimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end_exclusive: datetime


class TemporalRangeResolver:
    """Deterministically resolve supported Chinese relative-date expressions."""

    _WEEKDAYS: ClassVar[dict[str, int]] = {
        "一": 0,
        "二": 1,
        "三": 2,
        "四": 3,
        "五": 4,
        "六": 5,
        "日": 6,
        "天": 6,
    }

    def resolve(self, expression: str, *, now: datetime) -> DateTimeRange:
        value = expression.strip().replace(" ", "")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        today = now.date()
        if value == "今天":
            return self._days(today, 1, now)
        if value == "昨天":
            return self._days(today - timedelta(days=1), 1, now)
        if value == "前天":
            return self._days(today - timedelta(days=2), 1, now)
        if value in {"本周", "这周"}:
            start = today - timedelta(days=today.weekday())
            return self._days(start, 7, now)
        if value == "上周" or value == "上周一至上周日":
            start = today - timedelta(days=today.weekday() + 7)
            return self._days(start, 7, now)
        if value in {"本月", "这个月"}:
            start = today.replace(day=1)
            return self._range(start, self._next_month(start), now)
        if value == "上个月":
            end = today.replace(day=1)
            start = (end - timedelta(days=1)).replace(day=1)
            return self._range(start, end, now)
        recent = re.fullmatch(r"最近([三七]|\d+)天", value)
        if recent:
            token = recent.group(1)
            count = {"三": 3, "七": 7}.get(token, int(token) if token.isdigit() else 0)
            if not 1 <= count <= 31:
                raise ValueError("recent day range must be between 1 and 31")
            return self._days(today - timedelta(days=count - 1), count, now)
        weekday = re.fullmatch(r"(上周|本周)([一二三四五六日天])", value)
        if weekday:
            week_start = today - timedelta(days=today.weekday())
            if weekday.group(1) == "上周":
                week_start -= timedelta(days=7)
            return self._days(week_start + timedelta(days=self._WEEKDAYS[weekday.group(2)]), 1, now)
        current_weekday = re.fullmatch(r"(?:周|星期)([一二三四五六日天])", value)
        if current_weekday:
            selected_weekday = self._WEEKDAYS[current_weekday.group(1)]
            selected = today - timedelta(days=today.weekday()) + timedelta(days=selected_weekday)
            if selected > today:
                selected -= timedelta(days=7)
            return self._days(selected, 1, now)
        absolute = re.fullmatch(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", value)
        if absolute:
            year = int(absolute.group(1) or today.year)
            selected = date(year, int(absolute.group(2)), int(absolute.group(3)))
            return self._days(selected, 1, now)
        raise ValueError("不支持的时间表达式")

    @staticmethod
    def _next_month(value: date) -> date:
        _, days = calendar.monthrange(value.year, value.month)
        return value + timedelta(days=days)

    def _days(self, start: date, count: int, now: datetime) -> DateTimeRange:
        return self._range(start, start + timedelta(days=count), now)

    @staticmethod
    def _range(start: date, end: date, now: datetime) -> DateTimeRange:
        assert now.tzinfo is not None
        return DateTimeRange(
            start=datetime.combine(start, time.min, tzinfo=now.tzinfo),
            end_exclusive=datetime.combine(end, time.min, tzinfo=now.tzinfo),
        )
