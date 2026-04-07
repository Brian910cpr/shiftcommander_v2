from collections import defaultdict


def get_availability_state(all_availability_months, member_id, iso, shift):
    month_key = iso[:7]
    av_month = all_availability_months.get(month_key, {})
    day = av_month.get(member_id, {}).get(iso, {})
    value = day.get(shift, '')

    if isinstance(value, str):
        value = value.strip().lower()
        if value in ['preferred', 'available', 'unavailable', '']:
            return value

    if value is True:
        return 'available'
    if value is False:
        return 'unavailable'

    return ''


def seed_member_state(roster):
    state = {}
    for member in roster:
        state[member['member_id']] = {
            'assignments': 0,
            'hours_total': 0,
            'hours_by_week': defaultdict(float),
            'roles': defaultdict(int),
            'days_worked': set(),
            'shifts': set(),
            'last_end_dt': None,
        }
    return state
