import type { CSSProperties } from "react";

export function Skel({ w, h = 12, className = "", style }: { w?: number | string; h?: number | string; className?: string; style?: CSSProperties }) {
  return <span className={`skel ${className}`} style={{ width: w, height: h, ...style }} aria-hidden="true" />;
}

/** Table-shaped placeholder that holds the height of a real table to avoid layout shift. */
export function SkelRows({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skel-rows" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skel-row" key={i} style={{ minHeight: "var(--row-h)" }}>
          <Skel w={10} h={10} />
          <Skel w={`${28 + ((i * 17) % 22)}%`} />
          <span style={{ flex: 1 }} />
          <Skel w={56} />
          <Skel w={72} />
        </div>
      ))}
    </div>
  );
}

export function SkelReadouts({ n = 3 }: { n?: number }) {
  return (
    <div className="readouts" style={{ ["--cols" as string]: `repeat(${n}, minmax(0, 1fr))` }} role="status" aria-label="Loading figures">
      {Array.from({ length: n }, (_, i) => (
        <div className="readout" key={i}>
          <Skel w={96} h={10} />
          <Skel w="62%" h={34} style={{ marginTop: 6 }} />
          <Skel w="44%" h={10} />
          <Skel h={32} style={{ marginTop: 6 }} />
        </div>
      ))}
    </div>
  );
}

export function SkelChart({ height = 220 }: { height?: number }) {
  return (
    <div className="chart-skeleton" role="status" aria-label="Loading chart">
      <Skel h={height} />
    </div>
  );
}
