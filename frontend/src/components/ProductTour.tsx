import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const ONBOARDING_KEY_PREFIX = "tyf_onboarding_v1";
const ONBOARDING_DONE_VALUE = "1";
const SETUP_ROUTE = "/transactions?setup=1";
const PAD_PX = 8;
const MEASURE_INTERVAL_MS = 120;
const SPOTLIGHT_RADIUS_PX = 12;

type TourStep = {
  id: string;
  title: string;
  body: string;
  target?: string;
  route?: string;
};

const TOUR_STEPS: TourStep[] = [
  { id: "welcome", title: "Welcome to TrackYourFinances", body: "A quick tour of the main areas, then we will help you import your first bank CSV." },
  { id: "dashboard", title: "Dashboard", body: "See spending, savings, and household overview at a glance.", target: "nav-dashboard", route: "/" },
  { id: "transactions", title: "Transactions", body: "Classify spending, split shared bills, and import bank CSV or Excel files.", target: "nav-transactions", route: "/transactions" },
  { id: "accounts", title: "Accounts", body: "Track balances and manage checking, savings, and investment accounts.", target: "nav-accounts", route: "/accounts" },
  { id: "banks", title: "Banks", body: "Connect banks with Open Banking when you want automatic sync.", target: "nav-banks", route: "/banks" },
  { id: "profile", title: "Profile", body: "Update your household name, location, and invite partners.", target: "nav-profile", route: "/household" },
  { id: "setup", title: "Set up with CSV", body: "Name the account yourself, then upload a bank export. Rows import first; categories are assigned next.", target: "csv-import", route: SETUP_ROUTE },
];

const LAST_STEP_INDEX = TOUR_STEPS.length - 1;
const NEXT_LABEL = "Next";
const FINISH_LABEL = "Start setup";
const SKIP_LABEL = "Skip tour";
const STEP_LABEL_PREFIX = "Step";

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
      {rect ? <div className="product-tour-catcher" /> : <div className="product-tour-backdrop" />}
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
