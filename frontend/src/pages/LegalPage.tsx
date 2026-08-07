import { Link } from "react-router-dom";

type LegalKind = "privacy" | "terms";

const COPY: Record<LegalKind, { title: string; sections: { heading: string; body: string }[] }> = {
  privacy: {
    title: "Privacy policy",
    sections: [
      {
        heading: "Who we are",
        body: "TrackYourFinances is a private household finance tracker. It helps you sync and review balances and transactions for personal use.",
      },
      {
        heading: "What we collect",
        body: "With your consent, we retrieve account balances and transaction history from your bank through Enable Banking. We also store the account details you enter manually (for example name, IBAN, and balances) and data you import from CSV files.",
      },
      {
        heading: "How data is stored",
        body: "Bank and household data is stored locally in your TrackYourFinances instance for the household that connected the account. It is not sold, rented, or shared with advertisers.",
      },
      {
        heading: "Bank access",
        body: "Bank connections use Open Banking consent via Enable Banking. You can revoke access at any time through your bank or by disconnecting the link in TrackYourFinances.",
      },
      {
        heading: "Contact",
        body: "For data-protection questions related to this application, use the email address registered with the Enable Banking application that provides the bank connection.",
      },
    ],
  },
  terms: {
    title: "Terms of service",
    sections: [
      {
        heading: "Personal use",
        body: "TrackYourFinances is offered for personal, non-commercial household use. You may only connect bank accounts you are authorized to access.",
      },
      {
        heading: "Bank consent",
        body: "Connecting a bank means you authorize Enable Banking and TrackYourFinances to retrieve account information according to the consent you grant at your bank. Consent can be revoked at the bank at any time.",
      },
      {
        heading: "Accuracy",
        body: "Balances and transactions depend on data provided by your bank and Open Banking providers. The app does not provide financial, tax, or investment advice.",
      },
      {
        heading: "Availability",
        body: "The service may be interrupted for maintenance, provider outages, or expired bank consent. You remain responsible for keeping backups of any data you need.",
      },
    ],
  },
};

export function LegalPage({ kind }: { kind: LegalKind }) {
  const page = COPY[kind];
  const other = kind === "privacy" ? { to: "/terms", label: "Terms" } : { to: "/privacy", label: "Privacy" };
  return (
    <div className="legal-page">
      <header className="legal-head">
        <Link to="/auth" className="brand">TrackYourFinances</Link>
        <nav className="legal-nav">
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/auth">Sign in</Link>
        </nav>
      </header>
      <article className="legal-body">
        <h1>{page.title}</h1>
        <p className="muted">Last updated: 3 August 2026</p>
        {page.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            <p>{section.body}</p>
          </section>
        ))}
        <p className="muted">Also see <Link to={other.to}>{other.label}</Link>.</p>
      </article>
    </div>
  );
}
