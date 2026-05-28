import { useEffect, useState } from "react";
import {
  BrowserRouter, Navigate, Route, Routes, useLocation,
} from "react-router-dom";
import { ApiError, api } from "./api";
import { Header } from "./components/Header";
import { ToastProvider } from "./components/Toast";
import { ConversationsPage } from "./pages/ConversationsPage";
import { Dashboard } from "./pages/Dashboard";
import { KeysPage } from "./pages/KeysPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import type { CurrentUser } from "./types";

type AuthState =
  | { kind: "loading" }
  | { kind: "anon" }
  | { kind: "user"; user: CurrentUser };

function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ kind: "loading" });
  useEffect(() => {
    api.me()
      .then(user => setState({ kind: "user", user }))
      .catch(e => {
        if (e instanceof ApiError && e.status === 401) {
          setState({ kind: "anon" });
        } else {
          setState({ kind: "anon" });
        }
      });
  }, []);
  return state;
}

function AuthedShell({ user }: { user: CurrentUser }) {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="app">
        <Header user={user} />
        <main className="main" id="main">
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/keys" element={<KeysPage />} />
            <Route path="/conversations" element={<ConversationsPage />} />
            <Route path="/models" element={<ModelsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </>
  );
}

function Root() {
  const auth = useAuth();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const error = params.get("error") ?? undefined;

  if (auth.kind === "loading") {
    return (
      <div className="container" style={{ paddingTop: 120, textAlign: "center", color: "var(--text-3)" }}>
        Loading…
      </div>
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
