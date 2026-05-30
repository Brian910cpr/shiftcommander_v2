import { SCHEDULE_SOURCES, schedulePayload, seedMembersList, seedMeta } from "./data.js";

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
  const normalized = normalizeNameText(text);
  const roles = new Set();
  if (/\b(driver|chauffeur|drive)\b/.test(normalized)) roles.add("DRIVER");
  if (/\b(emt|attendant|als|aemt|paramedic|medic|care)\b/.test(normalized)) roles.add("ATTENDANT");
  if (/\b(medic|als|paramedic|aemt)\b/.test(normalized)) roles.add("ALS");
  if (/\b(ems supervisor|supervisor|112)\b/.test(normalized)) roles.add("EMS_SUPERVISOR");
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
  return text
    .split(" ")
    .filter((token) => token.length >= 3 && ![
      "emt",
      "ems",
      "day",
      "night",
      "driver",
      "attendant",
      "medic",
      "supervisor",
      "company",
      "volunteer",
      "career",
      "fire",
      "duty",
    ].includes(token));
}

function parsedCalendarTitle(event, memberIndex = null) {
  const title = normalizeNameText(event?.summary || "");
  const period = /\b(day|0600|0700|0800)\b/.test(title)
    ? "AM"
    : /\b(night|1800|1900|2000)\b/.test(title)
      ? "PM"
      : null;
  const roleHints = roleHintsFromText(title);
  const memberTokens = eventMemberTokens(event);
  const memberMatches = memberIndex ? resolveMemberHints(memberTokens, memberIndex) : [];

  return {
    period,
    role_hints: roleHints,
    member_tokens: memberTokens,
    member_matches: memberMatches,
  };
}

function buildMemberHintIndex(members = []) {
  const tokenMap = new Map();
  for (const member of members || []) {
    const id = String(member?.member_id || member?.id || "");
    const name = String(member?.name || "").trim();
    if (!id || !name) continue;

    const first = normalizeNameText(member.first_name || name.split(/\s+/)[0]);
    const full = normalizeNameText(name);
    const tokens = new Set([first, ...full.split(" ").filter((token) => token.length >= 3)]);

    for (const token of tokens) {
      if (!token) continue;
      if (!tokenMap.has(token)) tokenMap.set(token, []);
      tokenMap.get(token).push({ member_id: id, name });
    }
  }

  return tokenMap;
}

function resolveMemberHints(tokens, memberIndex) {
  const matches = [];
  for (const token of tokens || []) {
    const exact = memberIndex.get(token) || [];
    let candidates = exact;

    if (!candidates.length) {
      candidates = Array.from(memberIndex.entries())
        .filter(([knownToken]) => knownToken.startsWith(token) || token.startsWith(knownToken))
        .flatMap(([, rows]) => rows);
    }

    const uniqueById = new Map(candidates.map((member) => [member.member_id, member]));
    matches.push({
      token,
      status: uniqueById.size === 1 ? "unique" : uniqueById.size > 1 ? "ambiguous" : "unmatched",
      candidates: Array.from(uniqueById.values()).slice(0, 5),
    });
  }
  return matches;
}

function uniqueMemberMatch(memberMatches) {
  const unique = (memberMatches || []).filter((match) => match.status === "unique");
  if (unique.length !== 1) return null;
  return unique[0].candidates[0] || null;
}

function eventDiagnostics(event, memberIndex = null) {
  const text = `${event?.summary || ""} ${event?.description || ""}`;
  const parsed = parsedCalendarTitle(event, memberIndex);
  return {
    calendar_event_id: event?.calendar_event_id || null,
    calendar_title: event?.summary || "",
    calendar_start: event?.start || null,
    calendar_end: event?.end || null,
    date: dateFromValue(event?.start),
    period_hint: parsed.period || periodFromEvent(event),
    parsed_role_hints: Array.from(new Set([...parsed.role_hints, ...roleHintsFromText(text)])),
    parsed_member_hints: parsed.member_tokens,
    parsed_member_matches: parsed.member_matches,
  };
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

function scoreCalendarSeatMatch(event, seat, memberIndex = null) {
  const eventDate = dateFromValue(event.start);
  if (!eventDate || eventDate !== seat.date) return null;

  const parsed = parsedCalendarTitle(event, memberIndex);
  const eventPeriod = parsed.period || periodFromEvent(event);
  const text = `${event.summary || ""} ${event.description || ""}`;
  const roleHints = Array.from(new Set([...parsed.role_hints, ...roleHintsFromText(text)]));
  const memberTokens = parsed.member_tokens;
  const memberMatches = parsed.member_matches;
  const uniqueMember = uniqueMemberMatch(memberMatches);
  const assignedText = normalizeNameText(seat.assigned_name || "");
  const seatRole = String(seat.role || "").toUpperCase();

  let score = 4;
  const reasons = ["date"];
  const mismatchReasons = [];

  if (eventPeriod && seat.period && eventPeriod === seat.period) {
    score += 3;
    reasons.push("period");
  } else if (eventPeriod && seat.period && eventPeriod !== seat.period) {
    score -= 2;
    mismatchReasons.push("period_mismatch");
  } else {
    mismatchReasons.push("missing_period_hint");
  }

  if (
    roleHints.includes(seatRole) ||
    (seatRole === "ATTENDANT" && (roleHints.includes("ALS") || roleHints.includes("EMS_SUPERVISOR")))
  ) {
    score += 2;
    reasons.push("role_hint");
    if (roleHints.includes("ALS")) reasons.push("als_or_medic_hint");
    if (roleHints.includes("EMS_SUPERVISOR")) reasons.push("ems_supervisor_hint");
  } else if (roleHints.length) {
    mismatchReasons.push("role_mismatch");
  } else {
    mismatchReasons.push("missing_seat_hint");
  }

  const tokenHits = memberTokens.filter((token) => assignedText.includes(token));
  if (uniqueMember && String(seat.assigned_member_id || "") === String(uniqueMember.member_id)) {
    score += 5;
    reasons.push("member_name_hint");
    reasons.push("known_member_id_match");
  } else if (tokenHits.length) {
    score += Math.min(3, tokenHits.length);
    reasons.push("member_name_hint");
  } else if ((memberMatches || []).some((match) => match.status === "ambiguous")) {
    mismatchReasons.push("ambiguous_member_hint");
  } else if (uniqueMember && String(seat.assigned_member_id || "") !== String(uniqueMember.member_id)) {
    mismatchReasons.push("member_mismatch");
  } else if (memberTokens.length && assignedText) {
    mismatchReasons.push("member_mismatch");
  } else {
    mismatchReasons.push("missing_member_hint");
  }

  return {
    score,
    confidence_score: score,
    reasons,
    mismatch_reasons: mismatchReasons,
    event_period: eventPeriod,
    role_hints: roleHints,
    member_hints: memberTokens,
    member_matches: memberMatches,
  };
}

function candidateDiagnostics(candidate) {
  return {
    candidate_shift_id: candidate.seat.shift_id,
    candidate_seat_id: candidate.seat.seat_id,
    candidate_shift_date: candidate.seat.date,
    candidate_shift_period: candidate.seat.period,
    candidate_shift_unit: candidate.seat.unit,
    candidate_seat_role: candidate.seat.role,
    candidate_assigned_member_id: candidate.seat.assigned_member_id,
    candidate_assigned_member: candidate.seat.assigned_name,
    assignment_status: candidate.seat.assignment_status,
    confidence_score: candidate.confidence_score,
    match_reasons: candidate.reasons,
    mismatch_reasons: candidate.mismatch_reasons,
  };
}

function conflictReason(candidateCount, strongCount, bestCandidate) {
  if (strongCount > 1) return "ambiguous_multiple_candidates";
  if (!bestCandidate) return "date_match_only";
  const reasons = new Set(bestCandidate.reasons || []);
  const mismatches = new Set(bestCandidate.mismatch_reasons || []);
  if (reasons.has("date") && reasons.has("period") && bestCandidate.score >= 5) return "date_plus_ampm_match";
  if (mismatches.has("role_mismatch")) return "role_mismatch";
  if (mismatches.has("member_mismatch")) return "member_mismatch";
  if (mismatches.has("missing_member_hint")) return "missing_member_hint";
  if (mismatches.has("missing_seat_hint")) return "missing_seat_hint";
  if (candidateCount > 1) return "ambiguous_multiple_candidates";
  return "date_match_only";
}

function incrementSummary(summary, key) {
  summary[key] = (summary[key] || 0) + 1;
}

function comparisonSamples(possibleConflicts) {
  const allCandidates = [];
  for (const conflict of possibleConflicts) {
    for (const candidate of conflict.candidates || []) {
      allCandidates.push({
        calendar_event_id: conflict.calendar_event_id,
        calendar_title: conflict.calendar_title,
        calendar_start: conflict.calendar_start,
        calendar_end: conflict.calendar_end,
        conflict_reason: conflict.reason,
        ...candidate,
      });
    }
  }

  return {
    top_10_highest_confidence_candidates: [...allCandidates]
      .sort((left, right) => right.confidence_score - left.confidence_score)
      .slice(0, 10),
    top_10_lowest_confidence_candidates: [...allCandidates]
      .sort((left, right) => left.confidence_score - right.confidence_score)
      .slice(0, 10),
    top_10_ambiguous_candidates: possibleConflicts
      .filter((conflict) => (conflict.candidates || []).length > 1 || conflict.reason === "ambiguous_multiple_candidates")
      .sort((left, right) => (right.candidates?.[0]?.confidence_score || 0) - (left.candidates?.[0]?.confidence_score || 0))
      .slice(0, 10),
  };
}

export function compareAdrCalendarToShiftCommander(calendarEvents, shifts, members = []) {
  const seats = flattenShiftCommanderSeats(shifts);
  const memberIndex = buildMemberHintIndex(members);
  const matches = [];
  const possibleConflicts = [];
  const conflictSummary = {
    date_match_only: 0,
    date_plus_ampm_match: 0,
    role_mismatch: 0,
    member_mismatch: 0,
    missing_member_hint: 0,
    missing_seat_hint: 0,
    ambiguous_multiple_candidates: 0,
  };
  const matchedEventIds = new Set();
  const matchedSeatIds = new Set();

  for (const event of calendarEvents || []) {
    const candidates = seats
      .map((seat) => {
        const scored = scoreCalendarSeatMatch(event, seat, memberIndex);
        return scored ? { seat, ...scored } : null;
      })
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);

    const strong = candidates.filter((candidate) => candidate.score >= 7);
    const topCandidate = candidates[0] || null;
    const secondCandidate = candidates[1] || null;
    const uniqueHighConfidence =
      topCandidate &&
      topCandidate.score >= 9 &&
      (!secondCandidate || topCandidate.score > secondCandidate.score);
    const eventId = event.calendar_event_id || `${event.start}:${event.summary}`;

    if (strong.length === 1 || uniqueHighConfidence) {
      const match = uniqueHighConfidence ? topCandidate : strong[0];
      matches.push({
        ...eventDiagnostics(event, memberIndex),
        ...candidateDiagnostics(match),
      });
      matchedEventIds.add(eventId);
      if (match.seat.seat_id) matchedSeatIds.add(match.seat.seat_id);
    } else if (strong.length > 1 || candidates.some((candidate) => candidate.score >= 5)) {
      const reason = conflictReason(candidates.length, strong.length, candidates[0]);
      incrementSummary(conflictSummary, reason);
      possibleConflicts.push({
        ...eventDiagnostics(event, memberIndex),
        reason,
        candidates: candidates.slice(0, 5).map((candidate) => candidateDiagnostics(candidate)),
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
      member_hints: eventMemberTokens(event),
      member_matches: parsedCalendarTitle(event, memberIndex).member_matches,
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
    possible_conflicts_summary: conflictSummary,
    samples: comparisonSamples(possibleConflicts),
    sample_matches: matches.slice(0, 20),
  };
}

export async function adrCalendarComparisonPreviewPayload(env, fetchImpl = fetch) {
  const calendarPreview = await adrCalendarPreviewPayload(env, fetchImpl);
  const schedule = await schedulePayload(env);
  const comparison = compareAdrCalendarToShiftCommander(calendarPreview.events || [], schedule.shifts || [], seedMembersList());

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
