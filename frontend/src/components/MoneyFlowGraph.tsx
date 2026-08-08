import { useEffect, useMemo, useState, type FormEvent, type MouseEvent } from "react";
import type { AccountFlow, FlowEdge, FlowNode } from "../api";
import { euro } from "../format";

const SVG_WIDTH = 960;
const SVG_HEIGHT = 480;
const COL_INCOME_X = 120;
const COL_ACCOUNT_X = 480;
const COL_EXPENSES_X = 840;
const NODE_W = 176;
const NODE_H = 64;
const ACCOUNT_NODE_H = 118;
const MIN_STROKE = 2;
const MAX_STROKE = 10;
const KIND_INCOME = "income";
const KIND_ACCOUNT = "account";
const KIND_EXPENSES = "expenses";
const EDGE_TRANSFER = "transfer";
const EDGE_SPEND = "spend";
const EDGE_INVEST = "invest";
const COLOR_INCOME = "#4ade80";
const COLOR_SPEND = "#fb7185";
const COLOR_TRANSFER = "#67e8f9";
const COLOR_INVEST = "#86efac";
const IBAN_TAIL_LEN = 4;
const DEFAULT_ACCOUNT_TYPE = "checking";

type Point = { x: number; y: number };
type LaidOutNode = FlowNode & Point;
type TooltipState = { x: number; y: number; text: string } | null;
export type QuickAccountInput = { name: string; iban: string | null; account_type: string };

function maskIban(iban: string | null | undefined): string {
  const cleaned = (iban ?? "").replace(/\s+/g, "");
  if (!cleaned) return "";
  if (cleaned.length <= IBAN_TAIL_LEN) return cleaned;
  return `…${cleaned.slice(-IBAN_TAIL_LEN)}`;
}

function layoutNodes(nodes: FlowNode[]): LaidOutNode[] {
  const accounts = nodes.filter((n) => n.kind === KIND_ACCOUNT);
  const income = nodes.find((n) => n.kind === KIND_INCOME);
  const expenses = nodes.find((n) => n.kind === KIND_EXPENSES);
  const accountCount = Math.max(accounts.length, 1);
  const gap = Math.min(124, (SVG_HEIGHT - 110) / accountCount);
  const startY = (SVG_HEIGHT - gap * (accountCount - 1)) / 2;
  const laid: LaidOutNode[] = [];
  if (income) laid.push({ ...income, x: COL_INCOME_X, y: SVG_HEIGHT / 2 });
  accounts.forEach((node, index) => laid.push({ ...node, x: COL_ACCOUNT_X, y: startY + index * gap }));
  if (expenses) laid.push({ ...expenses, x: COL_EXPENSES_X, y: SVG_HEIGHT / 2 });
  return laid;
}

function edgePath(from: Point, to: Point): string {
  const startX = from.x + NODE_W / 2;
  const endX = to.x - NODE_W / 2;
  const dx = endX - startX;
  const c1 = startX + dx * 0.45;
  const c2 = endX - dx * 0.45;
  return `M ${startX} ${from.y} C ${c1} ${from.y}, ${c2} ${to.y}, ${endX} ${to.y}`;
}

function strokeForAmount(amount: number, maxAmount: number): number {
  if (maxAmount <= 0) return MIN_STROKE;
  return MIN_STROKE + (MAX_STROKE - MIN_STROKE) * Math.min(1, amount / maxAmount);
}

function edgeColor(kind: string): string {
  if (kind === EDGE_TRANSFER) return COLOR_TRANSFER;
  if (kind === EDGE_INVEST) return COLOR_INVEST;
  if (kind === EDGE_SPEND) return COLOR_SPEND;
  return COLOR_INCOME;
}

function nodeClass(kind: string): string {
  if (kind === KIND_INCOME) return "flow-node flow-node-income";
  if (kind === KIND_EXPENSES) return "flow-node flow-node-expenses";
  return "flow-node flow-node-account";
}

function hubColor(kind: string): string {
  if (kind === KIND_INCOME) return COLOR_INCOME;
  if (kind === KIND_EXPENSES) return COLOR_SPEND;
  return COLOR_TRANSFER;
}

type Props = {
  flow: AccountFlow | null;
  loading?: boolean;
  onSaveIban?: (accountId: number, iban: string | null) => Promise<void>;
  onAddAccount?: (input: QuickAccountInput) => Promise<void>;
  onRemoveAccount?: (accountId: number, label: string) => Promise<void>;
};

export function MoneyFlowGraph({ flow, loading, onSaveIban, onAddAccount, onRemoveAccount }: Props) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const [ibanDrafts, setIbanDrafts] = useState<Record<number, string>>({});
  const [editingIbanId, setEditingIbanId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newIban, setNewIban] = useState("");
  const [newType, setNewType] = useState(DEFAULT_ACCOUNT_TYPE);
  const [adding, setAdding] = useState(false);
  const laid = useMemo(() => layoutNodes(flow?.nodes ?? []), [flow]);
  const byId = useMemo(() => new Map(laid.map((n) => [n.id, n])), [laid]);
  const maxAmount = useMemo(() => Math.max(0, ...(flow?.edges.map((e) => e.amount) ?? [0])), [flow]);
  const edges = flow?.edges ?? [];
  const accountNodes = laid.filter((n) => n.kind === KIND_ACCOUNT);

  useEffect(() => {
    const next: Record<number, string> = {};
    for (const node of flow?.nodes ?? []) {
      if (node.account_id != null) next[node.account_id] = node.iban ?? "";
    }
    setIbanDrafts(next);
    setEditingIbanId(null);
  }, [flow]);

  if (loading) return <p className="muted">Loading money flow…</p>;

  function showEdgeTip(edge: FlowEdge, event: MouseEvent<SVGPathElement>) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    const label = `${source?.label ?? edge.source} → ${target?.label ?? edge.target}: ${euro.format(edge.amount)}`;
    const rect = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top - 12, text: label });
  }

  async function saveIban(event: FormEvent, accountId: number) {
    event.preventDefault();
    if (!onSaveIban) return;
    setSavingId(accountId);
    await onSaveIban(accountId, ibanDrafts[accountId]?.trim() ? ibanDrafts[accountId].trim() : null);
    setSavingId(null);
    setEditingIbanId(null);
  }

  async function submitAdd(event: FormEvent) {
    event.preventDefault();
    if (!onAddAccount || !newName.trim()) return;
    setAdding(true);
    await onAddAccount({ name: newName.trim(), iban: newIban.trim() || null, account_type: newType });
    setNewName("");
    setNewIban("");
    setNewType(DEFAULT_ACCOUNT_TYPE);
    setShowAdd(false);
    setAdding(false);
  }

  async function removeAccount(accountId: number, label: string) {
    if (!onRemoveAccount) return;
    setRemovingId(accountId);
    await onRemoveAccount(accountId, label);
    setRemovingId(null);
  }

  return (
    <div className="flow-graph">
      <div className="flow-toolbar">
        <div className="flow-zones" aria-hidden>
          <span>Income</span>
          <span>Accounts</span>
          <span>Expenses</span>
        </div>
        {onAddAccount && (
          <button type="button" className="secondary flow-add-toggle" onClick={() => setShowAdd((open) => !open)}>
            {showAdd ? "Cancel" : "+ Account"}
          </button>
        )}
      </div>
      {showAdd && onAddAccount && (
        <form className="flow-quick-add" onSubmit={(e) => submitAdd(e).catch(() => setAdding(false))}>
          <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Account name" required />
          <input value={newIban} onChange={(e) => setNewIban(e.target.value)} placeholder="IBAN (optional)" />
          <select value={newType} onChange={(e) => setNewType(e.target.value)}>
            <option value="checking">checking</option>
            <option value="savings">savings</option>
            <option value="investment">investment</option>
            <option value="other">other</option>
          </select>
          <button type="submit" disabled={adding || !newName.trim()}>{adding ? "Adding…" : "Add"}</button>
        </form>
      )}
      {(!flow || accountNodes.length === 0) && !loading ? (
        <p className="muted">No accounts yet. Use <strong>+ Account</strong> to add one.</p>
      ) : (
        <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className="flow-svg" role="img" aria-label="Money flow between income, accounts, and expenses">
          <defs>
            <linearGradient id="flowGradIncome" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={COLOR_INCOME} stopOpacity="0.15" />
              <stop offset="50%" stopColor={COLOR_INCOME} stopOpacity="0.85" />
              <stop offset="100%" stopColor={COLOR_INCOME} stopOpacity="0.35" />
            </linearGradient>
            <linearGradient id="flowGradSpend" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={COLOR_SPEND} stopOpacity="0.35" />
              <stop offset="50%" stopColor={COLOR_SPEND} stopOpacity="0.85" />
              <stop offset="100%" stopColor={COLOR_SPEND} stopOpacity="0.15" />
            </linearGradient>
            <linearGradient id="flowGradTransfer" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={COLOR_TRANSFER} stopOpacity="0.25" />
              <stop offset="50%" stopColor={COLOR_TRANSFER} stopOpacity="0.9" />
              <stop offset="100%" stopColor={COLOR_TRANSFER} stopOpacity="0.25" />
            </linearGradient>
            <linearGradient id="flowGradInvest" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={COLOR_INVEST} stopOpacity="0.25" />
              <stop offset="50%" stopColor={COLOR_INVEST} stopOpacity="0.9" />
              <stop offset="100%" stopColor={COLOR_INVEST} stopOpacity="0.25" />
            </linearGradient>
            <filter id="flowSoftGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <g className="flow-edges">
            {edges.map((edge) => {
              const source = byId.get(edge.source);
              const target = byId.get(edge.target);
              if (!source || !target) return null;
              const width = strokeForAmount(edge.amount, maxAmount);
              const color = edgeColor(edge.kind);
              const gradient =
                edge.kind === EDGE_SPEND
                  ? "url(#flowGradSpend)"
                  : edge.kind === EDGE_TRANSFER
                    ? "url(#flowGradTransfer)"
                    : edge.kind === EDGE_INVEST
                      ? "url(#flowGradInvest)"
                      : "url(#flowGradIncome)";
              const path = edgePath(source, target);
              return (
                <g key={`${edge.source}-${edge.target}-${edge.kind}`} className="flow-link">
                  <path d={path} fill="none" stroke={color} strokeWidth={width * 2.4} strokeLinecap="round" strokeOpacity={0.18} />
                  <path
                    d={path}
                    fill="none"
                    stroke={gradient}
                    strokeWidth={width}
                    strokeLinecap="round"
                    strokeDasharray={edge.kind === EDGE_TRANSFER ? "5 7" : undefined}
                    filter="url(#flowSoftGlow)"
                    className="flow-edge"
                    onMouseEnter={(e) => showEdgeTip(edge, e)}
                    onMouseMove={(e) => showEdgeTip(edge, e)}
                    onMouseLeave={() => setTooltip(null)}
                  />
                </g>
              );
            })}
          </g>
          {laid.map((node) => {
            const height = node.kind === KIND_ACCOUNT ? ACCOUNT_NODE_H : NODE_H;
            const x = node.x - NODE_W / 2;
            const y = node.y - height / 2;
            const hub = hubColor(node.kind);
            if (node.kind === KIND_ACCOUNT && node.account_id != null) {
              const accountId = node.account_id;
              const draft = ibanDrafts[accountId] ?? "";
              const masked = maskIban(draft || node.iban);
              const isEditing = editingIbanId === accountId;
              return (
                <g key={node.id}>
                  <circle cx={node.x - NODE_W / 2} cy={node.y} r="4" fill={hub} className="flow-hub" />
                  <circle cx={node.x + NODE_W / 2} cy={node.y} r="4" fill={hub} className="flow-hub" />
                  <foreignObject x={x} y={y} width={NODE_W} height={height} className="flow-foreign">
                    <div className={nodeClass(node.kind)}>
                      <div className="flow-node-head">
                        <div className="flow-node-title">{node.label}</div>
                        {onRemoveAccount && (
                          <button
                            type="button"
                            className="flow-remove"
                            title={`Remove ${node.label}`}
                            disabled={removingId === accountId}
                            onClick={() => removeAccount(accountId, node.label).catch(() => setRemovingId(null))}
                          >
                            ×
                          </button>
                        )}
                      </div>
                      <div className="flow-node-amount">{euro.format(node.amount)} <span className="muted">net</span></div>
                      {isEditing ? (
                        <form className="flow-iban-form" onSubmit={(e) => saveIban(e, accountId).catch(() => setSavingId(null))}>
                          <input
                            value={draft}
                            onChange={(e) => setIbanDrafts((prev) => ({ ...prev, [accountId]: e.target.value }))}
                            placeholder="ES00…4591"
                            aria-label={`IBAN for ${node.label}`}
                            autoFocus
                          />
                          <button type="submit" disabled={savingId === accountId}>{savingId === accountId ? "…" : "Save"}</button>
                        </form>
                      ) : (
                        <button type="button" className="flow-iban-chip" onClick={() => setEditingIbanId(accountId)}>
                          {masked || "Add IBAN"}
                        </button>
                      )}
                    </div>
                  </foreignObject>
                </g>
              );
            }
            return (
              <g key={node.id} className={nodeClass(node.kind)}>
                <circle cx={node.kind === KIND_INCOME ? node.x + NODE_W / 2 : node.x - NODE_W / 2} cy={node.y} r="4" fill={hub} className="flow-hub" />
                <rect x={x} y={y} width={NODE_W} height={NODE_H} rx="14" />
                <text x={node.x} y={node.y - 6} textAnchor="middle" className="flow-node-label">{node.label}</text>
                <text x={node.x} y={node.y + 14} textAnchor="middle" className="flow-node-amount">{euro.format(node.amount)}</text>
              </g>
            );
          })}
        </svg>
      )}
      {tooltip && (
        <div className="flow-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          {tooltip.text}
        </div>
      )}
      {flow && edges.length === 0 && accountNodes.length > 0 && (
        <p className="muted flow-empty-edges">No weighted links this month — income and spend edges appear once categorized.</p>
      )}
    </div>
  );
}
