"""Fixed morning intake windows, independent of workflow start/retry time."""
import datetime as dt
from zoneinfo import ZoneInfo

TIMEZONE="America/Los_Angeles"
CUTOFF_HOUR=6
INTAKE_VERSION="la-0600-arxiv24h-previous-journal-day-v1"

def issue_window(day):
    date=dt.date.fromisoformat(day)
    end=dt.datetime.combine(date,dt.time(CUTOFF_HOUR),ZoneInfo(TIMEZONE)).astimezone(dt.timezone.utc)
    start=end-dt.timedelta(hours=24)
    return {"version":INTAKE_VERSION,"timezone":TIMEZONE,
        "arxiv_start":start.isoformat(),"arxiv_end":end.isoformat(),
        "journal_publication_date":(date-dt.timedelta(days=1)).isoformat()}

def announcement_time(listing_day):
    """arXiv labels the 20:00 Eastern release with the following UTC day."""
    previous=dt.date.fromisoformat(listing_day)-dt.timedelta(days=1)
    return dt.datetime.combine(previous,dt.time(20),ZoneInfo("America/New_York")).astimezone(dt.timezone.utc)

def announcement_in_window(listing_day,window):
    announced=announcement_time(listing_day)
    return dt.datetime.fromisoformat(window["arxiv_start"])<=announced<dt.datetime.fromisoformat(window["arxiv_end"])
