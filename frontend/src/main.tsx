import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/legacy.css";
import "./styles/shell.css";
import "./styles/controls.css";
import "./styles/data.css";
import "./styles/pages.css";
import "./styles/home.css";
import "./styles/sessions.css";
import "./styles/login.css";
import "./styles/settings.css";
import "./styles/fixes.css";
import "./styles/round2.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
