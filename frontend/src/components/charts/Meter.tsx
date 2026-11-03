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
  const pctText = hasCap ? (f > 0 && f < 0.01 ? "<1%" : `${Math.round(f * 100)}%`) : "no cap";
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

/**
 * A graduated gauge for a reading that is not a spend cap: error rate against its redline, latency against
 * the median, fallbacks against the whole. Notches are real thresholds the caller names; `max` is the scale end.
 */
export function Gauge({
  value, max, notches = [], tone = "ok", label, valueText, ends,
}: {
  value: number;
  max: number;
  notches?: { at: number; hot?: boolean }[];
  tone?: MeterTone;
  label: string;
  valueText: string;
  ends: [string, string];
}) {
  const at = (v: number) => Math.max(0, Math.min(1, v / max));
  return (
    <div className="meter-wrap gauge">
      <div
        className="meter sm" data-tone={tone} role="meter" aria-label={label}
        aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.min(value, max)} aria-valuetext={valueText}
      >
        <div className="meter-track"><div className="meter-fill" style={{ ["--p" as string]: at(value) }} /></div>
        {notches.map(n => <i key={n.at} className={`meter-notch${n.hot ? " hot" : ""}`} style={{ ["--at" as string]: `${at(n.at) * 100}%` }} />)}
      </div>
      <div className="meter-scale" aria-hidden="true"><span>{ends[0]}</span><span>{ends[1]}</span></div>
    </div>
  );
}
