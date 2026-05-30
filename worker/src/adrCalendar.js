import { SCHEDULE_SOURCES, schedulePayload, seedMeta } from "./data.js";

const ADR_CALENDAR_EMBED_URL =
  "https://calendar.google.com/calendar/embed?src=2fbc3612e56a0a2ce28fe826443e20a88c500e1c5b3c56b126cb4afb88fd233e%40group.calendar.google.com&ctz=America%2FNew_York";

const ADR_CALENDAR_SOURCE = "adr_google_calendar";
const CACHE_TTL_MS = 5 * 60 * 1000;

let previewCache = null;

export function adrCalendarFeedUrlFromEmbed(embedUrl = ADR_CALENDAR_EMBED_URL) {
  const url = new URL(embedUrl);
  const calendarId = url.searchParams.get("src");
  if (!calendarId) {
    throw new Error("Google Calendar embed URL is missing src");
  }
  return `https://calendar.google.com/calendar/ical/${encodeURIComponent(calendarId)}/public/basic.ics`;
}

function unfoldIcsLines(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const unfolded = [];

  for (const line of lines) {
    if (/^[ \t]/.test(line) && unfolded.length) {
      unfolded[unfolded.length - 1] += line.slice(1);
    } else {
      unfolded.push(line);
    }
  }

  return unfolded;
}

function parseIcsProperty(line) {
  const separatorIndex = line.indexOf(":");
  if (separatorIndex < 0) return null;

  const rawName = line.slice(0, separatorIndex);
  const value = line.slice(separatorIndex + 1);
  const [name, ...parameterParts] = rawName.split(";");
  const parameters = {};

  for (const part of parameterParts) {
    const [key, ...rest] = part.split("=");
    if (!key) continue;
    parameters[key.toUpperCase()] = rest.join("=");
  }

  return {
    name: name.toUpperCase(),
    parameters,
    value: decodeIcsText(value),
  };
}

function decodeIcsText(value) {
  return String(value || "")
    .replace(/\\n/gi, "\n")
    .replace(/\\,/g, ",")
    .replace(/\\;/g, ";")
    .replace(/\\\\/g, "\\");
}

function formatIcsDate(value, parameters = {}) {
  const raw = String(value || "").trim();
  if (!raw) return null;

  if (parameters.VALUE === "DATE" || /^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  }

  const match = raw.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$/);
  if (!match) return raw;

  const [, year, month, day, hour, minute, second, zulu] = match;
  return `${year}-${month}-${day}T${hour}:${minute}:${second}${zulu ? "Z" : ""}`;
}

function eventToCanonicalScheduleObject(event) {
  const start = event.DTSTART ? formatIcsDate(event.DTSTART.value, event.DTSTART.parameters) : null;
  const end = event.DTEND ? formatIcsDate(event.DTEND.value, event.DTEND.parameters) : null;

  return {
    source: ADR_CALENDAR_SOURCE,
    schedule_source: SCHEDULE_SOURCES.CANONICAL,
    calendar_event_id: event.UID?.value || null,
    calendar_updated_at: event.LAST_MODIFIED?.value
      ? formatIcsDate(event.LAST_MODIFIED.value, event.LAST_MODIFIED.parameters)
      : event.DTSTAMP?.value
        ? formatIcsDate(event.DTSTAMP.value, event.DTSTAMP.parameters)
        : null,
    summary: event.SUMMARY?.value || "",
    description: event.DESCRIPTION?.value || "",
    location: event.LOCATION?.value || "",
    start,
    end,
    all_day: Boolean(event.DTSTART?.parameters?.VALUE === "DATE"),
    raw: {
      uid: event.UID?.value || null,
      dtstart: event.DTSTART?.value || null,
      dtend: event.DTEND?.value || null,
      dtstamp: event.DTSTAMP?.value || null,
      last_modified: event.LAST_MODIFIED?.value || null,
    },
  };
}

export function parseAdrCalendarIcs(icsText) {
  const lines = unfoldIcsLines(icsText);
  const events = [];
  let current = null;

  for (const line of lines) {
    if (line === "BEGIN:VEVENT") {
      current = {};
      continue;
    }

    if (line === "END:VEVENT") {
      if (current) events.push(eventToCanonicalScheduleObject(current));
      current = null;
      continue;
    }

    if (!current) continue;
    const property = parseIcsProperty(line);
    if (!property) continue;
    current[property.name] = property;
  }

  return events;
}

export async function adrCalendarPreviewPayload(env, fetchImpl = fetch) {
  const now = Date.now();
  if (previewCache && now - previewCache.cachedAt < CACHE_TTL_MS) {
    return {
      ...seedMeta(env),
      ...previewCache.payload,
      cache: {
        hit: true,
        cached_at: new Date(previewCache.cachedAt).toISOString(),
        ttl_seconds: CACHE_TTL_MS / 1000,
      },
    };
  }

  const feedUrl = adrCalendarFeedUrlFromEmbed();

  try {
    const response = await fetchImpl(feedUrl, {
      method: "GET",
      headers: {
        Accept: "text/calendar,text/plain;q=0.9,*/*;q=0.8",
      },
    });

    if (!response.ok) {
      return {
        ...seedMeta(env),
        ok: false,
        source: ADR_CALENDAR_SOURCE,
        schedule_source: SCHEDULE_SOURCES.CANONICAL,
        calendar_embed_url: ADR_CALENDAR_EMBED_URL,
        calendar_feed_url: feedUrl,
        available: false,
        error: `Calendar fetch failed with HTTP ${response.status}`,
        status: response.status,
        events: [],
        event_count: 0,
      };
    }

    const icsText = await response.text();
    const events = parseAdrCalendarIcs(icsText);
    const payload = {
      source: ADR_CALENDAR_SOURCE,
      schedule_source: SCHEDULE_SOURCES.CANONICAL,
      calendar_embed_url: ADR_CALENDAR_EMBED_URL,
      calendar_feed_url: feedUrl,
      available: true,
      read_only: true,
      applied_to_active_schedule: false,
      event_count: events.length,
      events,
      fetched_at: new Date().toISOString(),
    };

    previewCache = { cachedAt: now, payload };

    return {
      ...seedMeta(env),
      ...payload,
      cache: {
        hit: false,
        ttl_seconds: CACHE_TTL_MS / 1000,
      },
    };
  } catch (error) {
    return {
      ...seedMeta(env),
      ok: false,
      source: ADR_CALENDAR_SOURCE,
      schedule_source: SCHEDULE_SOURCES.CANONICAL,
      calendar_embed_url: ADR_CALENDAR_EMBED_URL,
      calendar_feed_url: feedUrl,
      available: false,
      error: error?.message || String(error),
      events: [],
      event_count: 0,
    };
  }
}

function dateFromValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  return raw.slice(0, 10);
}

function minutesFromValue(value) {
  const raw = String(value || "").trim();
  const match = raw.match(/T(\d{2}):?(\d{2})/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function periodFromEvent(event) {
  const text = `${event?.summary || ""} ${event?.description || ""}`.toLowerCase();
  if (/\b(am|day|0600|0700|0800|morning)\b/.test(text)) return "AM";
  if (/\b(pm|night|1800|1900|2000|evening)\b/.test(text)) return "PM";

  const startMinutes = minutesFromValue(event?.start);
  if (startMinutes === null) return null;
  return startMinutes >= 12 * 60 ? "PM" : "AM";
}

function roleHintsFromText(text) {
  const normalized = String(text || "").toLowerCase();
  const roles = new Set();
  if (/\b(driver|chauffeur|drive|emt night|emt day)\b/.test(normalized)) roles.add("DRIVER");
  if (/\b(attendant|als|aemt|paramedic|medic|care|emt)\b/.test(normalized)) roles.add("ATTENDANT");
  return Array.from(roles);
}

function normalizeNameText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function eventMemberTokens(event) {
  const text = normalizeNameText(`${event?.summary || ""} ${event?.description || ""}`);
  return text.split(" ").filter((token) => token.length >= 3 && !["emt", "day", "night", "driver", "attendant"].includes(token));
}

function seatAssignedName(seat) {
  return seat?.assigned_name || seat?.name || seat?.assigned || null;
}

function flattenShiftCommanderSeats(shifts) {
  const rows = [];
  for (const shift of shifts || []) {
    for (const seat of shift?.seats || []) {
      rows.push({
        shift_id: shift.id || `${shift.date}:${shift.label || shift.period || ""}`,
        date: shift.date || null,
        period: shift.label || shift.period || null,
        unit: shift.unit || null,
        seat_id: seat.seat_id || null,
        role: seat.role || null,
        assigned_member_id: seat.assigned || null,
        assigned_name: seatAssignedName(seat),
        assignment_status: seat.assignment_status || null,
        locked: Boolean(seat.locked),
      });
    }
  }
  return rows;
}

function scoreCalendarSeatMatch(event, seat) {
  const eventDate = dateFromValue(event.start);
  if (!eventDate || eventDate !== seat.date) return null;

  const eventPeriod = periodFromEvent(event);
  const text = `${event.summary || ""} ${event.description || ""}`;
  const roleHints = roleHintsFromText(text);
  const memberTokens = eventMemberTokens(event);
  const assignedText = normalizeNameText(seat.assigned_name || "");

  let score = 4;
  const reasons = ["date"];

  if (eventPeriod && seat.period && eventPeriod === seat.period) {
    score += 3;
    reasons.push("period");
  } else if (eventPeriod && seat.period && eventPeriod !== seat.period) {
    score -= 2;
    reasons.push("period_mismatch");
  }

  if (roleHints.includes(String(seat.role || "").toUpperCase())) {
    score += 2;
    reasons.push("role_hint");
  }

  const tokenHits = memberTokens.filter((token) => assignedText.includes(token));
  if (tokenHits.length) {
    score += Math.min(3, tokenHits.length);
    reasons.push("member_name_hint");
  }

  return {
    score,
    reasons,
    event_period: eventPeriod,
    role_hints: roleHints,
  };
}

export function compareAdrCalendarToShiftCommander(calendarEvents, shifts) {
  const seats = flattenShiftCommanderSeats(shifts);
  const matches = [];
  const possibleConflicts = [];
  const matchedEventIds = new Set();
  const matchedSeatIds = new Set();

  for (const event of calendarEvents || []) {
    const candidates = seats
      .map((seat) => {
        const scored = scoreCalendarSeatMatch(event, seat);
        return scored ? { seat, ...scored } : null;
      })
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);

    const strong = candidates.filter((candidate) => candidate.score >= 7);
    const eventId = event.calendar_event_id || `${event.start}:${event.summary}`;

    if (strong.length === 1) {
      const match = strong[0];
      matches.push({
        calendar_event_id: event.calendar_event_id,
        calendar_summary: event.summary,
        date: dateFromValue(event.start),
        calendar_start: event.start,
        shift_id: match.seat.shift_id,
        seat_id: match.seat.seat_id,
        role: match.seat.role,
        assigned_name: match.seat.assigned_name,
        score: match.score,
        reasons: match.reasons,
      });
      matchedEventIds.add(eventId);
      if (match.seat.seat_id) matchedSeatIds.add(match.seat.seat_id);
    } else if (strong.length > 1 || candidates.some((candidate) => candidate.score >= 5)) {
      possibleConflicts.push({
        calendar_event_id: event.calendar_event_id,
        calendar_summary: event.summary,
        date: dateFromValue(event.start),
        calendar_start: event.start,
        reason: strong.length > 1 ? "multiple_strong_candidates" : "weak_or_ambiguous_candidates",
        candidates: candidates.slice(0, 5).map((candidate) => ({
          shift_id: candidate.seat.shift_id,
          seat_id: candidate.seat.seat_id,
          role: candidate.seat.role,
          assigned_name: candidate.seat.assigned_name,
          score: candidate.score,
          reasons: candidate.reasons,
        })),
      });
    }
  }

  const unmatchedCalendarEvents = (calendarEvents || [])
    .filter((event) => !matchedEventIds.has(event.calendar_event_id || `${event.start}:${event.summary}`))
    .map((event) => ({
      calendar_event_id: event.calendar_event_id,
      summary: event.summary,
      start: event.start,
      end: event.end,
      date: dateFromValue(event.start),
      period_hint: periodFromEvent(event),
      role_hints: roleHintsFromText(`${event.summary || ""} ${event.description || ""}`),
    }));

  const unmatchedShiftCommanderShifts = seats
    .filter((seat) => !matchedSeatIds.has(seat.seat_id))
    .map((seat) => ({
      shift_id: seat.shift_id,
      seat_id: seat.seat_id,
      date: seat.date,
      period: seat.period,
      role: seat.role,
      assigned_name: seat.assigned_name,
      assignment_status: seat.assignment_status,
    }));

  return {
    calendar_event_count: (calendarEvents || []).length,
    shiftcommander_shift_count: seats.length,
    matched_count: matches.length,
    unmatched_calendar_events: unmatchedCalendarEvents,
    unmatched_shiftcommander_shifts: unmatchedShiftCommanderShifts,
    possible_conflicts: possibleConflicts,
    sample_matches: matches.slice(0, 20),
  };
}

export async function adrCalendarComparisonPreviewPayload(env, fetchImpl = fetch) {
  const calendarPreview = await adrCalendarPreviewPayload(env, fetchImpl);
  const schedule = await schedulePayload(env);
  const comparison = compareAdrCalendarToShiftCommander(calendarPreview.events || [], schedule.shifts || []);

  return {
    ...seedMeta(env),
    source: ADR_CALENDAR_SOURCE,
    schedule_source: SCHEDULE_SOURCES.CANONICAL,
    read_only: true,
    applied_to_active_schedule: false,
    calendar_available: calendarPreview.available === true,
    calendar_error: calendarPreview.error || null,
    ...comparison,
  };
}
