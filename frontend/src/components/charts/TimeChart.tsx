import { useEffect, useId, useMemo, useRef, useState } from "react";

export interface Series {
  name: string;
  values: number[];
  tone?: "alt" | "bad";
}

function niceMax(v: number): { max: number; step: number } {
  if (v <= 0) return { max: 1, step: 0.25 };
  const raw = v / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) ?? raw;
  return { max: step * Math.ceil(v / step), step };
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/**
 * Time series drawn by hand. `lines` fills under the first series; `bars` draws the first series as columns and any
 * second series as a narrower overlay (errors against requests). Pointer and arrow keys move a crosshair, the
 * tooltip and a polite live region; "Table" swaps in the same numbers as a real table.
 */
export function TimeChart({
  title, labels, tickLabels, series, kind, format, valueNames,
}: {
  title: string;
  labels: string[];
  tickLabels: string[];
  series: Series[];
  kind: "lines" | "bars";
  format: (v: number, seriesIndex: number) => string;
  valueNames?: string[];
}) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const [view, setView] = useState<"chart" | "table">("chart");
  const [hover, setHover] = useState<number | null>(null);
  const uid = useId();
  const n = labels.length;
  const W = Math.max(width, 280);
  const H = W < 520 ? 190 : 230;
  const m = { l: W < 520 ? 40 : 48, r: 12, t: 12, b: 26 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;
  const peak = Math.max(...series.flatMap(s => s.values), 0);
  const { max, step } = niceMax(peak);
  const band = pw / Math.max(n, 1);
  const x = (i: number) => (kind === "bars" ? m.l + band * (i + 0.5) : m.l + (n <= 1 ? pw / 2 : (i / (n - 1)) * pw));
  const y = (v: number) => m.t + ph - (v / max) * ph;
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(pw / 74))));
  const names = valueNames ?? series.map(s => s.name);

  const paths = useMemo(() => series.map(s => s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [series, W, H, max]);

  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = kind === "bars" ? Math.floor((px - m.l) / band) : Math.round(((px - m.l) / pw) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  };
  const key = (e: React.KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    setHover(h => {
      const cur = h ?? (e.key === "ArrowLeft" ? n : -1);
      if (e.key === "Home") return 0;
      if (e.key === "End") return n - 1;
      return Math.max(0, Math.min(n - 1, cur + (e.key === "ArrowRight" ? 1 : -1)));
    });
  };

  const tipLeft = hover != null ? x(hover) : 0;
  const flip = hover != null && tipLeft > W * 0.58;
  const announce = hover != null ? `${labels[hover]}: ${series.map((s, k) => `${names[k]} ${format(s.values[hover], k)}`).join(", ")}` : "";

  return (
    <div>
      <div className="row between view-toggle" style={{ padding: "10px 16px 0" }}>
        <span className="caption">{title}</span>
        <div className="seg" role="group" aria-label={`${title} view`}>
          <button type="button" className={view === "chart" ? "on" : ""} aria-pressed={view === "chart"} onClick={() => setView("chart")}>Chart</button>
          <button type="button" className={view === "table" ? "on" : ""} aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
        </div>
      </div>

      {view === "table" ? (
        <div className="table-wrap" style={{ maxHeight: 280, overflow: "auto", margin: "10px 0 0" }}>
          <table className="tbl">
            <caption className="sr-only">{title}</caption>
            <thead><tr><th scope="col">Day</th>{series.map((s, k) => <th scope="col" className="num" key={s.name}>{names[k]}</th>)}</tr></thead>
            <tbody>
              {labels.map((l, i) => (
                <tr key={l}><td className="cell-id">{l}</td>{series.map((s, k) => <td className="num cell-id" key={s.name}>{format(s.values[i], k)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart" ref={wrap}>
          <div
            className="chart-focus" tabIndex={0} role="group" onKeyDown={key} onBlur={() => setHover(null)} onFocus={() => hover == null && setHover(n - 1)}
            aria-label={`${title}. ${n} days. Use left and right arrow keys to read each day, or switch to the table view.`}
          >
            <svg className="chart-svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`} onPointerMove={move} onPointerLeave={() => setHover(null)} aria-hidden="true">
              {ticks.map(t => (
                <g key={t}>
                  <line className={t === 0 ? "ch-axis" : "ch-grid"} x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} />
                  <text className="ch-label" x={m.l - 8} y={y(t) + 3.5} textAnchor="end">{format(t, 0).replace(/\.0+$/, "")}</text>
                </g>
              ))}
              {labels.map((_, i) => i % every === 0 && (
                <text className="ch-label" key={i} x={x(i)} y={H - 7} textAnchor={i === 0 && kind === "lines" ? "start" : "middle"}>{tickLabels[i]}</text>
              ))}
              {kind === "bars" ? (
                <g>
                  {series[0].values.map((v, i) => (
                    <g key={i}>
                      <rect className={`ch-bar${hover != null && hover !== i ? " dim" : ""}`} style={{ ["--i" as string]: i }} x={x(i) - band * 0.31} width={band * 0.62} y={y(v)} height={Math.max(v > 0 ? 2 : 0, m.t + ph - y(v))} rx={1.5} />
                      {series[1] && series[1].values[i] > 0 && (
                        <rect className="ch-bar bad" style={{ ["--i" as string]: i }} x={x(i) - band * 0.2} width={band * 0.4} y={y(series[1].values[i])} height={Math.max(2, m.t + ph - y(series[1].values[i]))} rx={1} />
                      )}
                    </g>
                  ))}
                </g>
              ) : (
                <g className="ch-draw">
                  {n > 1 && <path className="ch-area" d={`${paths[0]} L${x(n - 1)},${m.t + ph} L${x(0)},${m.t + ph} Z`} />}
                  {series.map((s, k) => <path key={s.name} className={`ch-line${s.tone ? ` ${s.tone}` : ""}`} d={paths[k]} />)}
                </g>
              )}
              {hover != null && (
                <g>
                  <line className="ch-cross" x1={x(hover)} x2={x(hover)} y1={m.t} y2={m.t + ph} />
                  {kind === "lines" && series.map(s => <circle key={s.name} className={`ch-dot${s.tone ? ` ${s.tone}` : ""}`} cx={x(hover)} cy={y(s.values[hover])} r={4} />)}
                </g>
              )}
            </svg>
          </div>
          {hover != null && (
            <div className="ch-tip" style={{ transform: `translate(${flip ? tipLeft - 140 : tipLeft + 22}px, ${m.t + 6}px)` }} aria-hidden="true">
              <div className="t-date">{labels[hover]}</div>
              {series.map((s, k) => (
                <div className="t-row" key={s.name}><span><i className={`sw${s.tone ? ` ${s.tone}` : ""}`} />{names[k]}</span><b>{format(s.values[hover], k)}</b></div>
              ))}
            </div>
          )}
          <div className="sr-only" role="status" aria-live="polite" id={`${uid}-live`}>{announce}</div>
          {series.length > 1 && (
            <div className="chart-foot" style={{ padding: "6px 0 0" }}>
              {series.map((s, k) => <span className="lg" key={s.name}><i className={s.tone ?? ""} />{names[k]}</span>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
