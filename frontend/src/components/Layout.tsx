import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { ProductTour } from "./ProductTour";

export function Layout() {
  const { user, household, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="brand" data-tour="brand">TrackYourFinances</div>
        <nav className="nav-links">
          <NavLink to="/" end data-tour="nav-dashboard" className={({ isActive }) => (isActive ? "active" : undefined)}>Dashboard</NavLink>
          <NavLink to="/transactions" data-tour="nav-transactions" className={({ isActive }) => (isActive ? "active" : undefined)}>Transactions</NavLink>
          <NavLink to="/accounts" data-tour="nav-accounts" className={({ isActive }) => (isActive ? "active" : undefined)}>Accounts</NavLink>
          <NavLink to="/banks" data-tour="nav-banks" className={({ isActive }) => (isActive ? "active" : undefined)}>Banks</NavLink>
          <NavLink to="/household" data-tour="nav-profile" className={({ isActive }) => (isActive ? "active" : undefined)}>Profile</NavLink>
          <span className="muted">{user?.display_name} · {household?.name}</span>
          <button className="secondary" type="button" onClick={logout}>Log out</button>
        </nav>
      </header>
      <main className="page"><Outlet /></main>
      <ProductTour />
    </div>
  );
}
