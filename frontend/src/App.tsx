import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AccountsPage } from "./pages/AccountsPage";
import { AuthPage } from "./pages/AuthPage";
import { BanksPage } from "./pages/BanksPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HouseholdPage } from "./pages/HouseholdPage";
import { LegalPage } from "./pages/LegalPage";
import { TransactionsPage } from "./pages/TransactionsPage";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (!user) return <Navigate to="/auth" replace />;
  return <Layout />;
}

function AuthGate() {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (user) return <Navigate to="/" replace />;
  return <AuthPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/privacy" element={<LegalPage kind="privacy" />} />
        <Route path="/terms" element={<LegalPage kind="terms" />} />
        <Route path="/auth" element={<AuthGate />} />
        <Route element={<Protected />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/banks" element={<BanksPage />} />
          <Route path="/household" element={<HouseholdPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
