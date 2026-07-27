export const euro = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function axisMoney(value: number) {
  return whole.format(Math.round(value));
}

export function signedEuro(value: number) {
  const formatted = euro.format(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
}

const EMPLOYER_SPLIT = /[,;\n]+/;

export function parseEmployerNames(raw: string): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const part of raw.split(EMPLOYER_SPLIT)) {
    const name = part.trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    names.push(name);
  }
  return names;
}
