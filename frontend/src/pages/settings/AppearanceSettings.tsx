import { IconCheck, IconMoon, IconSun } from "../../icons";
import { ACCENT_PRESETS, useAccent, useTheme } from "../../theme";

export function AppearanceSettings() {
  const [theme, toggleTheme] = useTheme();
  const [hue, setHue] = useAccent();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="card card-pad">
        <h2 className="section-title" style={{ marginBottom: 14 }}>Theme</h2>
        <div className="row" style={{ gap: 14 }}>
          <button
            type="button"
            className={`btn ${theme === "light" ? "btn-primary" : ""}`}
            onClick={() => theme !== "light" && toggleTheme()}
            aria-pressed={theme === "light"}
          >
            <IconSun /> Light
          </button>
          <button
            type="button"
            className={`btn ${theme === "dark" ? "btn-primary" : ""}`}
            onClick={() => theme !== "dark" && toggleTheme()}
            aria-pressed={theme === "dark"}
          >
            <IconMoon /> Dark
          </button>
          <span className="faint" style={{ fontSize: 12.5 }}>
            First load follows your OS preference; choice persists per browser.
          </span>
        </div>
      </div>

      <div className="card card-pad">
        <div className="row between" style={{ marginBottom: 14 }}>
          <h2 className="section-title">Accent colour</h2>
          <span className="faint mono" style={{ fontSize: 11.5 }}>oklch hue {Math.round(hue)}</span>
        </div>

        <p className="muted" style={{ marginTop: 0, marginBottom: 14, fontSize: 13 }}>
          Sets the dashboard's primary highlight. Everything derived from
          <code className="mono" style={{ marginLeft: 4, marginRight: 4 }}>--accent</code>
          (buttons, badges, focus rings, charts) follows.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
            gap: 10,
            marginBottom: 18,
          }}
        >
          {ACCENT_PRESETS.map(preset => {
            const on = Math.round(hue) === preset.hue;
            const swatch = `oklch(0.62 0.14 ${preset.hue})`;
            return (
              <button
                key={preset.name}
                type="button"
                onClick={() => setHue(preset.hue)}
                aria-pressed={on}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 6,
                  padding: 10,
                  border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
                  borderRadius: "var(--r-md)",
                  background: on ? "var(--accent-softer)" : "var(--surface)",
                  cursor: "pointer",
                  transition: "border-color .12s, background .12s",
                }}
              >
                <div
                  style={{
                    width: 28, height: 28, borderRadius: "50%",
                    background: swatch,
                    boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)",
                    position: "relative",
                  }}
                >
                  {on && (
                    <IconCheck
                      style={{
                        width: 16, height: 16,
                        color: "white",
                        position: "absolute", top: 6, left: 6,
                      }}
                    />
                  )}
                </div>
                <span style={{ fontSize: 12, fontWeight: 600 }}>{preset.name}</span>
              </button>
            );
          })}
        </div>

        <div className="field">
          <label htmlFor="accent-slider" style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Custom hue</span>
            <span className="faint mono">{Math.round(hue)}°</span>
          </label>
          <input
            id="accent-slider"
            type="range"
            min="0"
            max="360"
            step="1"
            value={hue}
            onChange={e => setHue(Number(e.target.value))}
            style={{
              width: "100%",
              accentColor: "var(--accent)",
            }}
          />
          <span className="hint">Drag for any colour the OKLCH gamut can hit.</span>
        </div>
      </div>
    </div>
  );
}
