import { addDays, addMonths, differenceInCalendarDays, startOfWeek } from 'date-fns';

export const MEMBER_AVAILABILITY_MONTHS_AHEAD = 6;

export function getAvailabilityVisibleRange(displayWeeks = 8, now = new Date()) {
  const start = startOfWeek(addDays(now, 1), { weekStartsOn: 4 });
  start.setHours(0, 0, 0, 0);

  const end = addDays(start, displayWeeks * 7);
  end.setHours(0, 0, 0, 0);

  return { start, end };
}

export function getDefaultMemberAvailabilityWeeks(now = new Date()) {
  const { start } = getAvailabilityVisibleRange(1, now);
  const end = addMonths(now, MEMBER_AVAILABILITY_MONTHS_AHEAD);
  end.setHours(0, 0, 0, 0);
  return Math.max(1, Math.ceil(differenceInCalendarDays(end, start) / 7));
}
