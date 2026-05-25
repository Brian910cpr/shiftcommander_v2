export function parseShiftDate(value) {
  if (!value) return null;

  const raw = String(value).slice(0, 10);
  if (!raw) return null;

  const [year, month, day] = raw.split('-').map(Number);
  if (![year, month, day].every(Number.isFinite)) return null;

  const parsed = new Date(year, month - 1, day);
  parsed.setHours(0, 0, 0, 0);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function getOperationalVisibleRange(now = new Date()) {
  const current = new Date(now);
  current.setHours(0, 0, 0, 0);

  const day = current.getDay();
  const daysSinceMonday = (day + 6) % 7;

  const start = new Date(current);
  start.setDate(current.getDate() - daysSinceMonday - 7);
  start.setHours(0, 0, 0, 0);

  const end = new Date(start);
  end.setDate(start.getDate() + 42);
  end.setHours(0, 0, 0, 0);

  return { start, end };
}

export function isShiftInOperationalVisibleRange(shift, now = new Date()) {
  const shiftDate = parseShiftDate(shift?.date || shift?.shift_date || shift?.start || shift?.start_time);
  if (!shiftDate) return false;

  const { start, end } = getOperationalVisibleRange(now);
  return shiftDate >= start && shiftDate < end;
}

export function shouldUseCalendarMirrorMode(dateValue) {
  const date = parseShiftDate(dateValue);
  return Boolean(date && date.getFullYear() === 2026 && date.getMonth() === 5);
}
