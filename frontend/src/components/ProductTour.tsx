import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const ONBOARDING_KEY_PREFIX = "tyf_onboarding_v5";
const ONBOARDING_DONE_VALUE = "1";
const ACCOUNTS_ROUTE = "/accounts";
const TRANSACTIONS_ROUTE = "/transactions";
const PROFILE_ROUTE = "/household";
const PAD_PX = 8;
const MEASURE_INTERVAL_MS = 120;
const SPOTLIGHT_RADIUS_PX = 12;

type TourStep = {
  id: string;
  title: string;
  body: string;
  target?: string;
  route?: string;
  interactive?: boolean;
};

const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome to TrackYourFinances",
    body: "Two ways to connect banks: upload a file, or sync automatically. We will walk the app left to right, starting with the Dashboard.",
  },
  {
    id: "dashboard",
    title: "Dashboard",
    body: "Household wealth, spending, and location-aware category benchmarks in one overview.",
    target: "nav-dashboard",
    route: "/",
  },
  {
    id: "transactions",
    title: "Transactions",
    body: "After data is in, review the ledger: classify spending, split shared bills, and grow rules from one-click assigns.",
    target: "nav-transactions",
    route: TRANSACTIONS_ROUTE,
  },
  {
    id: "money-flow",
    title: "Money flow",
    body: "At the top of Transactions, see how income moves through your accounts into expenses for the month you pick.",
    target: "money-flow",
    route: TRANSACTIONS_ROUTE,
  },
  {
    id: "accounts",
    title: "Accounts File Connection",
    body: "Create an account and import a bank CSV or Excel export — no live bank login required.",
    target: "nav-accounts",
    route: ACCOUNTS_ROUTE,
  },
  {
    id: "import",
    title: "Import bank CSV/Excel",
    body: "Name the account (or pick an existing one), choose your export file, then import. Rows load first; categories are assigned next.",
    target: "csv-import",
    route: ACCOUNTS_ROUTE,
  },
  {
    id: "banks",
    title: "Bank Auto Connection",
    body: "Prefer automatic updates? Link a bank with Open Banking here. File imports stay under Accounts File Connection.",
    target: "nav-banks",
    route: "/banks",
  },
  {
    id: "profile",
    title: "Profile",
    body: "Your household details live here. You can also invite a partner with the invite code.",
    target: "nav-profile",
    route: PROFILE_ROUTE,
  },
  {
    id: "location",
    title: "Where you live",
    body: "Type your city and country (for example Barcelona, Spain), then Save profile. We rebuild Spend-by-category typicals for that place and your income — it can take a few seconds.",
    target: "profile-location",
    route: PROFILE_ROUTE,
    interactive: true,
  },
];

const LAST_STEP_INDEX = TOUR_STEPS.length - 1;
const NEXT_LABEL = "Next";
const FINISH_LABEL = "Finish";
const SKIP_LABEL = "Skip tour";
const STEP_LABEL_PREFIX = "Step";
const LOCATION_FOCUS_DELAY_MS = 280;

export function onboardingStorageKey(userId: number) {
  return `${ONBOARDING_KEY_PREFIX}:${userId}`;
}

export function isOnboardingComplete(userId: number) {
  return localStorage.getItem(onboardingStorageKey(userId)) === ONBOARDING_DONE_VALUE;
}

export function markOnboardingComplete(userId: number) {
  localStorage.setItem(onboardingStorageKey(userId), ONBOARDING_DONE_VALUE);
}

type SpotlightRect = { top: number; left: number; width: number; height: number };

function readTargetRect(target: string | undefined): SpotlightRect | null {
  if (!target) return null;
  const el = document.querySelector(`[data-tour="${target}"]`);
  if (!el) return null;
  const box = el.getBoundingClientRect();
  return { top: box.top - PAD_PX, left: box.left - PAD_PX, width: box.width + PAD_PX * 2, height: box.height + PAD_PX * 2 };
}

function scrollTourTarget(target: string | undefined) {
  if (!target) return;
  document.querySelector(`[data-tour="${target}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function focusTourTargetInput(target: string | undefined) {
  if (!target) return;
  const root = document.querySelector(`[data-tour="${target}"]`);
  const input = root?.querySelector("input, select, textarea") ?? (root instanceof HTMLInputElement ? root : null);
  if (input instanceof HTMLElement) input.focus();
}

export function ProductTour() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<SpotlightRect | null>(null);

  useEffect(() => {
    if (!user) return;
    if (!isOnboardingComplete(user.id)) setActive(true);
  }, [user]);

  const step = TOUR_STEPS[stepIndex];

  useEffect(() => {
    if (!active || !step?.route) return;
    const [pathname, search = ""] = step.route.split("?");
    const wantSearch = search ? `?${search}` : "";
    if (location.pathname !== pathname || location.search !== wantSearch) navigate(step.route);
  }, [active, stepIndex, step?.route, location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!active) return;
    scrollTourTarget(TOUR_STEPS[stepIndex]?.target);
    const measure = () => setRect(readTargetRect(TOUR_STEPS[stepIndex]?.target));
    measure();
    const timerId = window.setInterval(measure, MEASURE_INTERVAL_MS);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearInterval(timerId);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [active, stepIndex, location.pathname, location.search]);

  useEffect(() => {
    if (!active || !step?.interactive || !step.target) return;
    const timerId = window.setTimeout(() => focusTourTargetInput(step.target), LOCATION_FOCUS_DELAY_MS);
    return () => window.clearTimeout(timerId);
  }, [active, stepIndex, step?.interactive, step?.target, location.pathname]);

  if (!user || !active || !step) return null;

  function finish() {
    markOnboardingComplete(user!.id);
    setActive(false);
  }

  function goNext() {
    if (stepIndex >= LAST_STEP_INDEX) {
      finish();
      return;
    }
    setStepIndex((current) => current + 1);
  }

  const cardStyle = rect
    ? { top: Math.min(rect.top + rect.height + 12, window.innerHeight - 220), left: Math.max(16, Math.min(rect.left, window.innerWidth - 360)) }
    : undefined;

  return (
    <div className="product-tour" role="dialog" aria-modal="true" aria-labelledby="product-tour-title">
      {rect && !step.interactive && <div className="product-tour-catcher" />}
      {!rect && <div className="product-tour-backdrop" />}
      {rect && (
        <div
          className="product-tour-spotlight"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height, borderRadius: SPOTLIGHT_RADIUS_PX }}
        />
      )}
      <div className={`product-tour-card${rect ? " is-anchored" : " is-centered"}`} style={cardStyle}>
        <p className="product-tour-progress muted">{STEP_LABEL_PREFIX} {stepIndex + 1} / {TOUR_STEPS.length}</p>
        <h2 id="product-tour-title">{step.title}</h2>
        <p className="product-tour-body">{step.body}</p>
        <div className="product-tour-actions">
          <button type="button" className="secondary" onClick={finish}>{SKIP_LABEL}</button>
          <button type="button" onClick={goNext}>{stepIndex >= LAST_STEP_INDEX ? FINISH_LABEL : NEXT_LABEL}</button>
        </div>
      </div>
    </div>
  );
}
