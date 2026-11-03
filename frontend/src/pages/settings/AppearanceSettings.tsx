import { IconCheck, IconMoon, IconSun } from "../../icons";
import { usePageTitle } from "../../util/hooks";
import { ACCENT_PRESETS, useAccent, useDensity, useTheme } from "../../theme";

export function AppearanceSettings() {
  usePageTitle("Appearance settings");
  const [theme, toggleTheme] = useTheme();
  const [hue, setHue] = useAccent();
  const [density, setDensity] = useDensity();

  return (
    <>
      <section className="panel panel-pad rise" aria-labelledby="ap-theme">
        <h2 className="caption" id="ap-theme" style={{ marginBottom: 14 }}>Theme</h2>
        <div className="row wrap" style={{ gap: 12 }}>
          <div className="seg" role="group" aria-label="Theme">
            <button type="button" className={theme === "light" ? "on" : ""} onClick={() => theme !== "light" && toggleTheme()} aria-pressed={theme === "light"}><IconSun />Light</button>
            <button type="button" className={theme === "dark" ? "on" : ""} onClick={() => theme !== "dark" && toggleTheme()} aria-pressed={theme === "dark"}><IconMoon />Dark</button>
          </div>
          <span className="faint" style={{ fontSize: "var(--t-xs)" }}>The first load follows your OS preference. Your choice is saved in this browser.</span>
        </div>
      </section>

      <section className="panel panel-pad rise" style={{ ["--i" as string]: 1 }} aria-labelledby="ap-accent">
        <div className="row between" style={{ marginBottom: 6 }}>
          <h2 className="caption" id="ap-accent">Accent colour</h2>
          <span className="faint mono" style={{ fontSize: 11.5 }}>oklch hue {Math.round(hue)}</span>
        </div>
        <p className="muted" style={{ margin: "0 0 14px", fontSize: "var(--t-sm)" }}>
          The accent is the needle: nav marker, meter fills, focus rings, primary buttons and chart lines. Amber and red stay fixed because they mean caution and stop.
        </p>
        <div className="swatches" style={{ marginBottom: 18 }}>
          {ACCENT_PRESETS.map(preset => {
            const on = Math.round(hue) === preset.hue;
            return (
              <button key={preset.name} type="button" className="swatch" onClick={() => setHue(preset.hue)} aria-pressed={on}>
                <i style={{ background: `oklch(0.58 0.15 ${preset.hue})` }}>{on && <IconCheck />}</i>
                {preset.name}
              </button>
            );
          })}
        </div>
        <div className="field">
          <label htmlFor="accent-slider" style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Custom hue</span><span className="faint mono">{Math.round(hue)}°</span>
          </label>
          <input id="accent-slider" type="range" min="0" max="360" step="1" value={hue} onChange={e => setHue(Number(e.target.value))} style={{ width: "100%", minHeight: 24 }} />
          <span className="hint">Drag for any colour the OKLCH gamut can reach.</span>
        </div>
      </section>

      <section className="panel panel-pad rise" style={{ ["--i" as string]: 2 }} aria-labelledby="ap-density">
        <h2 className="caption" id="ap-density" style={{ marginBottom: 14 }}>Table density</h2>
        <div className="row wrap" style={{ gap: 12 }}>
          <div className="seg" role="radiogroup" aria-label="Table density">
            {(["comfortable", "compact"] as const).map(d => (
              <button key={d} type="button" role="radio" aria-checked={density === d} className={density === d ? "on" : ""} onClick={() => setDensity(d)}>{d}</button>
            ))}
          </div>
          <span className="faint" style={{ fontSize: "var(--t-xs)" }}>Compact trims row height from 44 to 34 px in every table.</span>
        </div>
      </section>
    </>
  );
}
