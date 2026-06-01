export const SCHEDULE_SOURCES = Object.freeze({
  BOOTSTRAP: 'bootstrap',
  RESOLVER: 'resolver',
  SUPERVISOR: 'supervisor',
  CANONICAL: 'canonical',
});

export function canonicalScheduleProvider(bootstrap) {
  const schedule = bootstrap?.schedule || { shifts: bootstrap?.shifts || [] };
  const wallboardDisplay = bootstrap?.wallboard_display || bootstrap?.wallboard || null;

  return {
    source: SCHEDULE_SOURCES.BOOTSTRAP,
    priority: [
      SCHEDULE_SOURCES.CANONICAL,
      SCHEDULE_SOURCES.SUPERVISOR,
      SCHEDULE_SOURCES.RESOLVER,
      SCHEDULE_SOURCES.BOOTSTRAP,
    ],
    schedule,
    shifts: schedule?.shifts || bootstrap?.shifts || [],
    wallboardDisplay,
  };
}
