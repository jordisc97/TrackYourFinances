import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AccountsPage } from "./pages/AccountsPage";
import { AuthPage } from "./pages/AuthPage";
import { BanksPage } from "./pages/BanksPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HouseholdPage } from "./pages/HouseholdPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { TransactionsPage } from "./pages/TransactionsPage";

export const ONBOARDING_KEY = "tyf_needs_onboarding";
export const ONBOARDING_SKIPPED_KEY = "tyf_onboarding_skipped";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (!user) return <Navigate to="/auth" replace />;
  return <Layout />;
}

function HomeEntry() {
  const [checking, setChecking] = useState(true);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  useEffect(() => {
    const forced = sessionStorage.getItem(ONBOARDING_KEY) === "1";
    const skipped = sessionStorage.getItem(ONBOARDING_SKIPPED_KEY) === "1";
    Promise.all([api.connections(), api.accounts()])
      .then(([conns, accounts]) => {
        const hasActive = conns.some((c) => c.status === "active");
        const hasAccounts = accounts.length > 0;
        if (hasActive || hasAccounts) {
          sessionStorage.removeItem(ONBOARDING_KEY);
          sessionStorage.removeItem(ONBOARDING_SKIPPED_KEY);
          setNeedsOnboarding(false);
          return;
        }
        setNeedsOnboarding(forced || (!skipped && !hasActive));
      })
      .catch(() => setNeedsOnboarding(!skipped))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <p className="muted">Loading…</p>;
  if (needsOnboarding) return <Navigate to="/onboarding" replace />;
  return <DashboardPage />;
}

function AuthGate() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading || !user) return;
    const justRegistered = sessionStorage.getItem(ONBOARDING_KEY) === "1";
    const skipped = sessionStorage.getItem(ONBOARDING_SKIPPED_KEY) === "1";
    Promise.all([api.connections(), api.accounts()])
      .then(([conns, accounts]) => {
        const hasActive = conns.some((c) => c.status === "active");
        const hasAccounts = accounts.length > 0;
        if (hasActive || hasAccounts) {
          sessionStorage.removeItem(ONBOARDING_KEY);
          sessionStorage.removeItem(ONBOARDING_SKIPPED_KEY);
          navigate("/", { replace: true });
          return;
        }
        navigate(justRegistered || !skipped ? "/onboarding" : "/", { replace: true });
      })
      .catch(() => navigate("/onboarding", { replace: true }));
  }, [user, loading, navigate]);

  if (loading) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (user) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  return <AuthPage onRegistered={() => { sessionStorage.setItem(ONBOARDING_KEY, "1"); sessionStorage.removeItem(ONBOARDING_SKIPPED_KEY); }} />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/auth" element={<AuthGate />} />
        <Route element={<Protected />}>
          <Route path="/" element={<HomeEntry />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/banks" element={<BanksPage />} />
          <Route path="/household" element={<HouseholdPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
