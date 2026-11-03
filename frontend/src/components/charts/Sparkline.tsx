/** A tiny trace for a readout tile. Decorative shape, honest label: the summary sentence is the accessible name. */
export function Sparkline({
  values, label, tone,
}: {
  values: number[];
  label: string;
  tone?: "bad";
}) {
  const W = 200;
  const H = 36;
  const n = values.length;
  const max = Math.max(...values, 0);
  const x = (i: number) => (n <= 1 ? W / 2 : (i / (n - 1)) * W);
  const y = (v: number) => (max <= 0 ? H - 2 : H - 3 - (v / max) * (H - 8));
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = n > 1 ? `${line} L${W},${H} L0,${H} Z` : "";
  const last = values[n - 1] ?? 0;
  const summary = `${label}: ${n} points, highest ${max.toLocaleString(undefined, { maximumFractionDigits: 4 })}, latest ${last.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
  return (
    <svg className={`spark${tone ? ` ${tone}` : ""}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={summary}>
      <line className="spark-base" x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} />
      <g className="spark-draw">
        {area && <path className="spark-area" d={area} />}
        {max > 0 && <path className="spark-line" d={line} />}
      </g>
    </svg>
  );
}
