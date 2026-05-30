import { SCHEDULE_SOURCES, seedMeta } from "./data.js";

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
