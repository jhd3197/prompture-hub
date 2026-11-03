import { useCallback, useEffect, useRef, useState } from "react";
import {
  BrowserRouter, Link, Navigate, Route, Routes, useLocation,
} from "react-router-dom";
import { ApiError, api } from "./api";
import { Brand } from "./components/Brand";
import { ErrorState } from "./components/ErrorState";
import { CommandProvider } from "./components/Palette";
import { TabBar, TopBar } from "./components/Shell";
import { SkelReadouts, SkelRows } from "./components/Skeleton";
import { ToastProvider } from "./components/Toast";
import { PageHead } from "./components/PageHead";
import { IconHome, IconSearch } from "./icons";
import { errText } from "./lib/format";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BillingPage } from "./pages/BillingPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { CreateKeyPage } from "./pages/CreateKeyPage";
import { Dashboard } from "./pages/Dashboard";
import { KeysPage } from "./pages/KeysPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import { PairPage } from "./pages/PairPage";
import { SettingsPage } from "./pages/SettingsPage";
import { AppearanceSettings } from "./pages/settings/AppearanceSettings";
import { AlertsSettings } from "./pages/settings/AlertsSettings";
import { ApiSettings } from "./pages/settings/ApiSettings";
import { DevicesSettings } from "./pages/settings/DevicesSettings";
import { EndpointsSettings } from "./pages/settings/EndpointsSettings";
import { NetworkSettings } from "./pages/settings/NetworkSettings";
import { useCommands } from "./components/Palette";
import type { CurrentUser } from "./types";

type AuthState =
  | { kind: "loading" }
  | { kind: "anon" }
  | { kind: "failed"; message: string }
  | { kind: "user"; user: CurrentUser };

function useAuth(): [AuthState, () => void] {
  const [state, setState] = useState<AuthState>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    setState({ kind: "loading" });
    api.me()
      .then(user => setState({ kind: "user", user }))
      .catch(e => {
        if (e instanceof ApiError && e.status === 401) setState({ kind: "anon" });
        else setState({ kind: "failed", message: errText(e) });
      });
  }, [tick]);
  return [state, useCallback(() => setTick(t => t + 1), [])];
}

function NotFound() {
  const loc = useLocation();
  const { openPalette } = useCommands();
  return (
    <div className="container">
      <PageHead title="Page not found" docTitle="Not found" sub={<>Nothing lives at <code className="mono">{loc.pathname}</code>. The needle is off the scale.</>}>
        <Link to="/" className="btn btn-primary"><IconHome />Back to Home</Link>
        <button type="button" className="btn" onClick={openPalette}><IconSearch />Search the hub</button>
      </PageHead>
    </div>
  );
}

function AuthedShell({ user }: { user: CurrentUser }) {
  const loc = useLocation();
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);
  const [announce, setAnnounce] = useState("");

  // Route changes: back to the top, focus the content region, tell screen readers where they are.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
    setAnnounce(document.title);
  }, [loc.pathname]);

  const routeKey = loc.pathname.startsWith("/settings") ? "/settings" : loc.pathname;

  return (
    <CommandProvider>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="app">
        <TopBar user={user} />
        <main className="main" id="main" tabIndex={-1} ref={main}>
          <div className="route" key={routeKey}>
            <Routes location={loc}>
              <Route path="/" element={<Dashboard user={user} />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/billing" element={<BillingPage />} />
              <Route path="/keys" element={<KeysPage />} />
              <Route path="/keys/new" element={<CreateKeyPage />} />
              <Route path="/conversations" element={<ConversationsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/pair" element={<PairPage />} />
              <Route path="/settings" element={<SettingsPage />}>
                <Route index element={<Navigate to="appearance" replace />} />
                <Route path="appearance" element={<AppearanceSettings />} />
                <Route path="network" element={<NetworkSettings />} />
                <Route path="api" element={<ApiSettings />} />
                <Route path="devices" element={<DevicesSettings />} />
                <Route path="alerts" element={<AlertsSettings />} />
                <Route path="endpoints" element={<EndpointsSettings />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </main>
        <TabBar />
        <div className="sr-only" role="status" aria-live="polite">{announce}</div>
      </div>
    </CommandProvider>
  );
}

function Splash({ children }: { children?: React.ReactNode }) {
  return (
    <div className="app">
      <header className="bar"><div className="bar-in"><Brand as="static" /></div></header>
      <main className="main" id="main">
        <div className="container">{children}</div>
      </main>
    </div>
  );
}

function Root() {
  const [auth, retry] = useAuth();
  const location = useLocation();
  const error = new URLSearchParams(location.search).get("error") ?? undefined;

  if (auth.kind === "loading") {
    return (
      <Splash>
        <div className="stack" aria-busy="true">
          <SkelReadouts n={3} />
          <div className="panel"><SkelRows rows={5} label="Loading the hub" /></div>
        </div>
      </Splash>
    );
  }
  if (auth.kind === "failed") {
    return (
      <Splash>
        <div className="panel"><ErrorState title="Can't reach the hub" error={auth.message} onRetry={retry} /></div>
      </Splash>
    );
  }
  if (auth.kind === "anon") return <LoginPage error={error} />;
  return <AuthedShell user={auth.user} />;
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <ToastProvider>
        <Root />
      </ToastProvider>
    </BrowserRouter>
  );
}
