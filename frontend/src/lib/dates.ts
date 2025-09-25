const TZ = (import.meta as any).env?.VITE_TZ || 'America/Santiago';

// Parse backend timestamps. If no timezone, assume UTC (add Z).
export function parseTs(input: string | number | Date): Date {
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);
  let s = String(input || '').trim();
  if (!s) return new Date(NaN);
  if (s.includes(' ') && !s.includes('T')) s = s.replace(' ', 'T');
  const hasTZ = /([zZ]|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(hasTZ ? s : s + 'Z');
}

export function toLocaleStringSafe(input: string | number | Date) {
  const d = parseTs(input);
  if (isNaN(d.getTime())) return String(input ?? '');
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: TZ,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

export function toLocaleTimeStringSafe(input: string | number | Date) {
  const d = parseTs(input);
  if (isNaN(d.getTime())) return String(input ?? '');
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: TZ,
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    }).format(d);
  } catch {
    return d.toLocaleTimeString();
  }
}

export const TARGET_TIMEZONE = TZ;

// Compute offset of a timezone for a given date in minutes.
export function tzOffsetMinutes(date: Date, timeZone = TZ): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false
  });
  const parts = dtf.formatToParts(date);
  const map: any = {};
  for (const p of parts) map[p.type] = p.value;
  const y = Number(map.year);
  const m = Number(map.month) - 1;
  const d = Number(map.day);
  const hh = Number(map.hour);
  const mm = Number(map.minute);
  const ss = Number(map.second);
  // This constructs the same wall time in UTC, difference yields offset
  const utcMs = Date.UTC(y, m, d, hh, mm, ss);
  return (utcMs - date.getTime()) / 60000;
}
