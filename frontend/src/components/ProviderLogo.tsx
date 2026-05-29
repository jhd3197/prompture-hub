import { useState } from "react";

interface Props {
  iconUrl: string | null;
  brandColor: string | null;
  fallback: string;
  size?: number;
}

/**
 * Brand logo with graceful fallback.
 *
 * - When ``iconUrl`` is set we render the simple-icons CDN SVG against a
 *   tinted brand-color background.
 * - If the image fails to load (CDN down, slug typo, network), we swap to
 *   the initials block — identical to the no-brand path.
 * - When ``iconUrl`` is null we go straight to initials.
 */
export function ProviderLogo({
  iconUrl, brandColor, fallback, size = 34,
}: Props) {
  const [broken, setBroken] = useState(false);

  const tint = brandColor ? `#${brandColor}` : "var(--surface-2)";
  const bg = brandColor ? `${tint}1A` : "var(--surface-2)"; // ~10% alpha hex
  const borderColor = brandColor ? `${tint}33` : "var(--border)";

  if (!iconUrl || broken) {
    return (
      <span
        className="provider-logo"
        style={{
          width: size,
          height: size,
          background: bg,
          borderColor,
          color: brandColor ? `#${brandColor}` : "var(--text)",
        }}
      >
        {fallback}
      </span>
    );
  }

  return (
    <span
      className="provider-logo"
      style={{
        width: size,
        height: size,
        background: bg,
        borderColor,
        padding: 6,
      }}
    >
      <img
        src={iconUrl}
        alt=""
        aria-hidden="true"
        loading="lazy"
        width={size - 12}
        height={size - 12}
        style={{ display: "block" }}
        onError={() => setBroken(true)}
      />
    </span>
  );
}
