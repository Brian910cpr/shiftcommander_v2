from datetime import timedelta


ROLE_ATTENDANT = 'ATTENDANT'
ROLE_DRIVER = 'DRIVER'
ROLE_QRV = 'QRV'


def shift_key(iso_date, shift_name):
    return f"{iso_date}:{shift_name}"


def week_key_for(date_obj):
    iso_year, iso_week, _ = date_obj.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def hours_for_shift(settings, shift_name):
    defs = settings.get('shift_definitions', {}) or {}
    return int((defs.get(shift_name, {}) or {}).get('hours', 12) or 12)


def is_qrv_candidate(member):
    return member.get('medical') == 'ALS' and bool(member.get('qrv_certified'))


def can_attend(member, rule):
    medical = member.get('medical', 'NONE')
    if medical == 'ALS':
        return 'strict'
    if medical == 'EMT':
        return 'fallback'
    return None


def can_drive(member, unit, waiver_active):
    if not bool((member.get('drive') or {}).get(unit, False)):
        return False
    cert = member.get('cert', 'NONE')
    if cert == 'NCLD' and not waiver_active:
        return False
    return cert in ['ALS', 'EMT', 'EMR', 'NCLD']


def attendant_bonus(member, rule):
    medical = member.get('medical', 'NONE')
    if medical == 'ALS':
        return 12 if rule == 'ALS+EMT' else 10
    if medical == 'EMT':
        return -3 if rule == 'ALS+EMT' else 1
    return -999


def driver_bonus(member, waiver_active, rule):
    medical = member.get('medical', 'NONE')
    cert = member.get('cert', 'NONE')
    if medical == 'EMT':
        return 10 if rule == 'ALS+EMT' else 8
    if medical == 'EMR':
        return 7 if rule == 'ALS+EMT' else 5
    if cert == 'NCLD':
        return 4 if waiver_active else -999
    if medical == 'ALS':
        return -14
    return -999


def compute_shift_quality(unit, slots):
    if unit == 'QRV':
        qrv = next((s for s in slots if s['role'] == 'QRV'), None)
        if not qrv or not qrv.get('member_id'):
            return ('MISSING_QRV', 0, 'red')
        return ('QRV_OK', 100, 'green')

    attendant = next((s for s in slots if s['role'] == 'ATTENDANT'), None)
    driver = next((s for s in slots if s['role'] == 'DRIVER'), None)

    if not attendant and not driver:
        return ('MISSING_BOTH', 0, 'red')
    if not attendant or not attendant.get('member_id'):
        return ('MISSING_ATTENDANT', 10, 'red')
    if not driver or not driver.get('member_id'):
        return ('MISSING_DRIVER', 20, 'red')

    att_cert = attendant.get('cert', 'NONE')
    drv_cert = driver.get('cert', 'NONE')

    if att_cert == 'ALS' and drv_cert == 'EMT':
        return ('GOLD', 100, 'green')
    if att_cert == 'ALS' and drv_cert == 'EMR':
        return ('STRONG_EMR_DRIVER', 90, 'yellow')
    if att_cert == 'ALS' and drv_cert == 'NCLD':
        return ('WAIVER_ALS_NCLD', 80, 'red')
    if att_cert == 'ALS' and drv_cert == 'ALS':
        return ('ALS_DRIVER_LAST_RESORT', 55, 'yellow')
    if att_cert == 'EMT' and drv_cert == 'EMT':
        return ('BLS_DOUBLE_EMT', 65, 'green')
    if att_cert == 'EMT' and drv_cert == 'EMR':
        return ('BLS_EMR_DRIVER', 55, 'yellow')
    if att_cert == 'EMT' and drv_cert == 'NCLD':
        return ('WAIVER_BLS_NCLD', 45, 'red')

    return ('INVALID_CREW', 0, 'red')


def shift_start(date_obj, shift_name):
    if shift_name == 'AM':
        return date_obj.replace(hour=6, minute=0, second=0, microsecond=0)
    if shift_name == 'PM':
        return date_obj.replace(hour=18, minute=0, second=0, microsecond=0)
    return date_obj.replace(hour=6, minute=0, second=0, microsecond=0)


def shift_end(date_obj, shift_name, settings):
    return shift_start(date_obj, shift_name) + timedelta(hours=hours_for_shift(settings, shift_name))


def violates_rest_gap(member_state, start_dt, min_hours=8):
    last_end = member_state.get('last_end_dt')
    if not last_end:
        return False
    return (start_dt - last_end).total_seconds() < (min_hours * 3600)
