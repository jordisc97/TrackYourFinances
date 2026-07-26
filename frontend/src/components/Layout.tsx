import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

export function Layout() {
  const { user, household, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="brand">TrackYourFinances</div>
        <nav className="nav-links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : undefined)}>Dashboard</NavLink>
          <NavLink to="/transactions" className={({ isActive }) => (isActive ? "active" : undefined)}>Transactions</NavLink>
          <NavLink to="/accounts" className={({ isActive }) => (isActive ? "active" : undefined)}>Accounts</NavLink>
          <NavLink to="/banks" className={({ isActive }) => (isActive ? "active" : undefined)}>Banks</NavLink>
          <NavLink to="/household" className={({ isActive }) => (isActive ? "active" : undefined)}>Household</NavLink>
          <span className="muted">{user?.display_name} · {household?.name}</span>
          <button className="secondary" type="button" onClick={logout}>Log out</button>
        </nav>
      </header>
      <main className="page"><Outlet /></main>
    </div>
  );
}
