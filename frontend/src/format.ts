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
const NON_SPEND_KINDS = new Set(["transfer", "investment"]);
const INCOME_KIND = "income";
const EXPENSE_KIND = "expense";

export type AmountTone = "income" | "expense" | "neutral";

export function portionKind(split: { category_kind?: string | null }, tx: { category_kind?: string | null }): string | null {
  return split.category_kind ?? tx.category_kind ?? null;
}

export function splitSpendTotal(tx: { amount: number; category_kind?: string | null; splits?: { amount: number; category_kind?: string | null }[] }): number {
  if (!tx.splits?.length) return tx.amount;
  let total = 0;
  for (const split of tx.splits) {
    const kind = portionKind(split, tx);
    if (split.amount < 0 && (kind == null || !NON_SPEND_KINDS.has(kind))) total += split.amount;
  }
  return Math.round(total * 100) / 100;
}

export function ledgerDisplayAmount(tx: { amount: number; category_kind?: string | null; splits?: { amount: number; category_kind?: string | null }[] }): number {
  return tx.splits?.length ? splitSpendTotal(tx) : tx.amount;
}

export function amountTone(amount: number, kind: string | null | undefined): AmountTone {
  if (amount === 0) return "neutral";
  if (amount > 0) return kind === INCOME_KIND ? "income" : "neutral";
  if (kind === EXPENSE_KIND || kind == null) return "expense";
  return "neutral";
}

export function ledgerAmountTone(tx: { amount: number; category_kind?: string | null; splits?: { amount: number; category_kind?: string | null }[] }): AmountTone {
  const display = ledgerDisplayAmount(tx);
  if (tx.splits?.length) return display < 0 ? "expense" : "neutral";
  return amountTone(display, tx.category_kind);
}

export function amountClass(tone: AmountTone): string {
  if (tone === "income") return "amount-pos";
  if (tone === "expense") return "amount-neg";
  return "amount-neutral";
}

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
