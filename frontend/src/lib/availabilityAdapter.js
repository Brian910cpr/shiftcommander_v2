function normalizeIntent(value) {
  const key = String(value || '').toLowerCase();
  if (key === 'preferred' || key === 'prefer') return 'prefer';
  if (key === 'available') return 'available';
  if (key === 'do_not_schedule' || key === 'do_not' || key === 'not_available') return 'do_not';
  if (key === 'blank') return 'blank';
  return null;
}

function assignIntent(map, date, period, value) {
  const normalized = normalizeIntent(value);
  if (!date || !period || !normalized) return;
  map[`${date}:${period}`] = normalized;
}

export function entriesToAvailabilityMap(entries) {
  const map = {};
  (entries || []).forEach(entry => {
    assignIntent(map, entry.date, entry.period, entry.member_intent || entry.availability_value || entry.intent);
  });
  return map;
}

export function getMemberAvailabilityMap(availabilityPayload, memberId) {
  if (!availabilityPayload || !memberId) {
    return { map: {}, hasData: false, source: 'missing' };
  }

  const memberKey = String(memberId);
  const map = {};
  const months = availabilityPayload.months || {};

  Object.values(months).forEach(monthBucket => {
    const memberBucket = monthBucket?.[memberKey];
    if (!memberBucket || typeof memberBucket !== 'object') return;

    Object.entries(memberBucket).forEach(([date, periods]) => {
      if (!periods || typeof periods !== 'object') return;
      Object.entries(periods).forEach(([period, value]) => {
        assignIntent(map, date, period, value);
      });
    });
  });

  const entriesMap = entriesToAvailabilityMap(
    (availabilityPayload.entries || []).filter(entry => String(entry?.member_id) === memberKey),
  );

  return {
    map: { ...map, ...entriesMap },
    hasData: Object.keys(map).length > 0 || Object.keys(entriesMap).length > 0,
    source: availabilityPayload.seed_filtered ? 'member-compat-filtered' : 'bootstrap',
  };
}
