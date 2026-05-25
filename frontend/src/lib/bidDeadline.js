const MS_PER_DAY = 24 * 60 * 60 * 1000;

function parseDateTimeSafe(value) {
  if (!value) return null;

  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;

  return parsed;
}

function formatMonthDay(date) {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function formatFullMonthDay(date) {
  return date.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
}

export function getRollingBidUntilDate({
  firstVisibleAt,
  now = new Date(),
  windowDays = 3,
}) {
  const openedAt = parseDateTimeSafe(firstVisibleAt);
  const nowDate = parseDateTimeSafe(now);

  if (!openedAt || !nowDate || !windowDays) return null;

  const windowMs = windowDays * MS_PER_DAY;
  let deadline = new Date(openedAt.getTime() + windowMs);

  while (deadline.getTime() <= nowDate.getTime()) {
    deadline = new Date(deadline.getTime() + windowMs);
  }

  return deadline;
}

export function getCompactBidUntilLabel({
  firstVisibleAt,
  now = new Date(),
  windowDays = 3,
}) {
  const deadline = getRollingBidUntilDate({
    firstVisibleAt,
    now,
    windowDays,
  });

  if (!deadline) return null;

  return `Until ${formatMonthDay(deadline)}`;
}

export function getFullBidUntilLabel({
  firstVisibleAt,
  now = new Date(),
  windowDays = 3,
}) {
  const deadline = getRollingBidUntilDate({
    firstVisibleAt,
    now,
    windowDays,
  });

  if (!deadline) return null;

  return `Bid until ${formatMonthDay(deadline)}`;
}

export function getBidMicroDisplay(shift) {
  const review = shift?.bid_review || {};
  const compact = review.bid_display_label || null;
  const full = review.bid_display_full_label || null;
  const deadline = parseDateTimeSafe(review.next_bid_review_at);

  if (!compact) return null;

  return {
    compact,
    full: full || compact,
    aria: full && deadline ? `Open seat, bid until ${formatFullMonthDay(deadline)}` : full || compact,
    state: review.bid_display_state || 'none',
  };
}
