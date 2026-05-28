export function EndpointTag({ endpoint }: { endpoint: string }) {
  const native = endpoint.includes("extract") || endpoint.includes("conversations");
  return (
    <span
      className="mono"
      style={{
        fontSize: 11.5,
        padding: "2px 7px",
        borderRadius: 5,
        background: native ? "var(--accent-softer)" : "var(--surface-2)",
        color: native ? "var(--accent-strong)" : "var(--text-2)",
        border: "1px solid var(--border)",
        whiteSpace: "nowrap",
      }}
    >
      {endpoint}
    </span>
  );
}
