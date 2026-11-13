/** Date-only helpers. Engagements run on whole days, so everything is UTC midnight and yyyy-mm-dd strings. */

const DAY = 86_400_000;

export const parse = (s: string): number => {
  const [y, m, d] = s.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
};
export const fmt = (t: number): string => new Date(t).toISOString().slice(0, 10);
export const add = (s: string, n: number): string => fmt(parse(s) + n * DAY);
export const diff = (a: string, b: string): number => Math.round((parse(a) - parse(b)) / DAY);
export const today = (): string => {
  const d = new Date();
  return fmt(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
};

/** Monday of the week that holds the date. */
export const weekStart = (s: string): string => add(s, -((new Date(parse(s)).getUTCDay() + 6) % 7));

export const monthStart = (s: string): string => `${s.slice(0, 8)}01`;
export const addMonths = (s: string, n: number): string => {
  const [y, m] = s.split("-").map(Number);
  return fmt(Date.UTC(y, m - 1 + n, 1));
};

/** Visible range of a month grid: whole weeks, Monday to Sunday. */
export function monthRange(anchor: string): { start: string; end: string } {
  const first = monthStart(anchor);
  const last = add(addMonths(first, 1), -1);
  return { start: weekStart(first), end: add(weekStart(last), 6) };
}

export const weekRange = (anchor: string) => ({ start: weekStart(anchor), end: add(weekStart(anchor), 6) });

const f = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { timeZone: "UTC", ...opts });
export const monthTitle = (s: string) => f({ month: "long", year: "numeric" }).format(parse(s));
export const dayShort = (s: string) => f({ day: "numeric", month: "short" }).format(parse(s));
export const dayLong = (s: string) => f({ dateStyle: "medium" }).format(parse(s));
export const weekdayShort = (s: string) => f({ weekday: "short" }).format(parse(s));
export const rangeTitle = (a: string, b: string) => `${f({ day: "numeric", month: "short" }).format(parse(a))} to ${f({ day: "numeric", month: "short", year: "numeric" }).format(parse(b))}`;
