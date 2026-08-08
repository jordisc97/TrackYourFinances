import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { BrandLogo } from "./BrandLogo";
import { ProductTour } from "./ProductTour";

export function Layout() {
  const { user, household, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="brand" data-tour="brand"><BrandLogo size="sm" /></div>
        <nav className="nav-bar" aria-label="Primary">
          <div className="nav-links">
            <NavLink to="/" end data-tour="nav-dashboard" className={({ isActive }) => (isActive ? "active" : undefined)}>Dashboard</NavLink>
            <NavLink to="/transactions" data-tour="nav-transactions" className={({ isActive }) => (isActive ? "active" : undefined)}>Transactions</NavLink>
            <NavLink to="/accounts" data-tour="nav-accounts" className={({ isActive }) => (isActive ? "active" : undefined)}>Accounts File Connection</NavLink>
            <NavLink to="/banks" data-tour="nav-banks" className={({ isActive }) => (isActive ? "active" : undefined)}>Bank Auto Connection</NavLink>
            <NavLink to="/household" data-tour="nav-profile" className={({ isActive }) => (isActive ? "active" : undefined)}>Profile</NavLink>
          </div>
          <div className="nav-meta">
            <span className="nav-identity">{user?.display_name}<span className="nav-identity-sep" aria-hidden="true"> · </span>{household?.name}</span>
            <button className="secondary nav-logout" type="button" onClick={logout}>Log out</button>
          </div>
        </nav>
      </header>
      <main className="page page-enter"><Outlet /></main>
      <ProductTour />
    </div>
  );
}
