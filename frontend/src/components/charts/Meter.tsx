import { usd } from "../../util/format";

export type MeterTone = "ok" | "warn" | "bad" | "none";

export const toneFor = (fraction: number): MeterTone => (fraction >= 0.9 ? "bad" : fraction >= 0.7 ? "warn" : "ok");

/**
 * A cap meter: used against the cap, alarm notches at 70% and 90%, an optional dotted marker for where the
 * current pace would land by the reset. The fill is a scaled bar, so it settles to the reading.
 */
export function Meter({
  used, cap, projected, label, size, hideText,
}: {
  used: number;
  cap: number;
  projected?: number | null;
  label: string;
  size?: "sm";
  hideText?: boolean;
}) {
  const hasCap = cap > 0;
  const f = hasCap ? Math.max(0, used) / cap : 0;
  const tone: MeterTone = hasCap ? toneFor(f) : "none";
  const shown = Math.min(1, f);
  const proj = hasCap && projected != null ? Math.min(1, projected / cap) : null;
  const pctText = hasCap ? `${Math.round(f * 100)}%` : "no cap";
  const text = hasCap ? `${usd(used)} of ${usd(cap, 2)}, ${pctText} used` : `${usd(used)} used, no cap`;
  return (
    <div className="meter-wrap">
      <div
        className={`meter${size ? ` ${size}` : ""}`} data-tone={tone} role="meter" aria-label={label}
        aria-valuemin={0} aria-valuemax={hasCap ? cap : Math.max(used, 1)} aria-valuenow={Math.min(used, hasCap ? cap : used)} aria-valuetext={text}
      >
        <div className="meter-track">
          <div className="meter-fill" style={{ ["--p" as string]: shown }} />
        </div>
        {hasCap && <i className="meter-notch" style={{ ["--at" as string]: "70%" }} />}
        {hasCap && <i className="meter-notch hot" style={{ ["--at" as string]: "90%" }} />}
        {proj != null && proj > shown && <i className="meter-proj" style={{ ["--at" as string]: `${proj * 100}%` }} title={`On pace for ${usd(projected!, 2)}`} />}
      </div>
      {!hideText && (
        <div className="meter-text">
          <span>{usd(used)}<span className="faint"> / {hasCap ? usd(cap, 2) : "no cap"}</span></span>
          <span className="pct" data-tone={tone}>{pctText}</span>
        </div>
      )}
    </div>
  );
}
