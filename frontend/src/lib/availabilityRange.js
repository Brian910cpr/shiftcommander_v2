import { addDays, startOfWeek } from 'date-fns';

export function getAvailabilityVisibleRange(displayWeeks = 8, now = new Date()) {
  const start = startOfWeek(addDays(now, 1), { weekStartsOn: 4 });
  start.setHours(0, 0, 0, 0);

  const end = addDays(start, displayWeeks * 7);
  end.setHours(0, 0, 0, 0);

  return { start, end };
}
