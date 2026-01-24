"""Custom Jinja2 filters for email rendering."""
from datetime import datetime
import re
from markupsafe import Markup


FRENCH_MONTHS = [
    '', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
]

FRENCH_DAYS = [
    'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'
]


def format_date(value, fmt='%Y-%m-%d'):
    """Format datetime to string with French month names."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value

    # Replace %B with French month name
    if '%B' in fmt:
        french_month = FRENCH_MONTHS[value.month]
        fmt = fmt.replace('%B', french_month)

    # Replace %A with French day name
    if '%A' in fmt:
        french_day = FRENCH_DAYS[value.weekday()]
        fmt = fmt.replace('%A', french_day)

    return value.strftime(fmt)


def truncate_html(value, length=200, suffix='...'):
    """Truncate HTML content safely."""
    text = re.sub(r'<[^>]+>', '', str(value))
    if len(text) <= length:
        return Markup(text)
    return Markup(text[:length].rsplit(' ', 1)[0] + suffix)


def strip_html(value):
    """Strip HTML tags from content."""
    text = re.sub(r'<[^>]+>', '', str(value))
    return Markup(text)


def relevancy_color(article):
    """Return background color based on relevancy score."""
    score = getattr(article, 'relevancy_score', 0)
    if score >= 0.7:
        return '#28a745'  # Green - High
    elif score >= 0.4:
        return '#ffc107'  # Yellow - Medium
    return '#6c757d'  # Gray - Low


FILTERS = {
    'format_date': format_date,
    'truncate_html': truncate_html,
    'strip_html': strip_html,
    'relevancy_color': relevancy_color,
}
