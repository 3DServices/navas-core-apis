"""
Which alerts GET /notifications/<owner_uid>/list returns.

Without `since` the list is the latest LATEST alerts, as it always was: the
alerts screen and the dashboard badges only need what is recent.

With `?since=` it is every alert raised at or after that moment, up to
SINCE_CAP. The OLIWA dashboard's alert analytics reads 7-day, 30-day and
month-to-date windows from this list, and the latest 200 undercounted any
fleet busier than that. The cap only keeps one request from reading an
unbounded history; when it is hit the route says so in the X-Truncated
header.

`since` is a date ("2026-10-08", meaning its midnight) or a date and time
("2026-10-08 06:00:00" or "2026-10-08T06:00:00"). date_triggered is stored as
Kampala local time without a zone, so a value carrying a zone is converted to
Kampala time first.

Pure: no Flask, no database.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

LATEST = 200
SINCE_CAP = 5000

_KLA = ZoneInfo('Africa/Kampala')


class BadSince(ValueError):
    """`since` is not a date or a date and time."""


def window(since_arg):
    """(since, limit) for the list: since is a naive Kampala datetime, or
    None for "the latest LATEST". Raises BadSince for an unreadable value."""
    raw = (since_arg or '').strip()
    if not raw:
        return None, LATEST
    try:
        since = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        raise BadSince(raw) from None
    if since.tzinfo is not None:
        since = since.astimezone(_KLA).replace(tzinfo=None)
    return since, SINCE_CAP
