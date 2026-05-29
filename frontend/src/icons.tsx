import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement>;

const I = (paths: React.ReactNode, sw = 1.7) =>
  function Icon(props: Props) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true" {...props}>{paths}</svg>
    );
  };

export const IconHome = I(<><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/><path d="M9.5 20v-6h5v6"/></>);
export const IconKey = I(<><circle cx="8" cy="14" r="4.5"/><path d="M11.2 11 21 3"/><path d="M17 5l2.5 2.5"/><path d="M14 8l2.5 2.5"/></>);
export const IconGrid = I(<><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/></>);
export const IconDocs = I(<><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6"/><path d="M9 16h6"/></>);
export const IconExternal = I(<><path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 13v6H5V6h6"/></>, 1.6);
export const IconSun = I(<><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>);
export const IconMoon = I(<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>);
export const IconLock = I(<><rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/><circle cx="12" cy="15.5" r="1.3" fill="currentColor" stroke="none"/></>);
export const IconShield = I(<><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></>);
export const IconArrowRight = I(<><path d="M4 12h15"/><path d="M13 6l6 6-6 6"/></>);
export const IconChevronRight = I(<path d="M9 5l7 7-7 7"/>);
export const IconChevronDown = I(<path d="M5 9l7 7 7-7"/>);
export const IconPlus = I(<><path d="M12 5v14"/><path d="M5 12h14"/></>);
export const IconSearch = I(<><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></>);
export const IconCopy = I(<><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></>);
export const IconCheck = I(<path d="M5 12.5l4.5 4.5L19 7"/>, 2);
export const IconX = I(<><path d="M6 6l12 12"/><path d="M18 6L6 18"/></>);
export const IconAlert = I(<><path d="M12 3l9 16H3z"/><path d="M12 9v5"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/></>);
export const IconBolt = I(<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>);
export const IconActivity = I(<path d="M3 12h4l3 8 4-16 3 8h4"/>);
export const IconDollar = I(<><path d="M12 2v20"/><path d="M16.5 6.5c-1-1.2-2.7-1.8-4.5-1.8-2.5 0-4.5 1.2-4.5 3.2 0 4.6 9 2.4 9 7 0 2.1-2 3.4-4.5 3.4-1.9 0-3.7-.7-4.7-2"/></>);
export const IconTrash = I(<><path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v5M14 11v5"/></>);
export const IconGauge = I(<><path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 14l4-3.5"/></>);
export const IconClock = I(<><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></>);
export const IconLayers = I(<><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/></>);
export const IconBook = I(<><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M19 19H6a2 2 0 0 0-2 2"/></>);
export const IconRefresh = I(<><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></>);
export const IconRoute = I(<><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 17.5H14a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h1"/></>);
export const IconMessages = I(<><path d="M4 5h12v9H9l-5 4z"/><path d="M8 17h11l1 3v-9a2 2 0 0 0-2-2h-2"/></>);
export const IconTerminal = I(<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/></>);
export const IconUser = I(<><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>);
export const IconBot = I(<><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M9 13h.01M15 13h.01M9 17h6"/></>);
export const IconCog = I(<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></>);

export function IconGoogle(props: Props) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" {...props}>
      <path fill="#4285F4" d="M21.6 12.2c0-.6-.05-1.2-.16-1.8H12v3.4h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.1z"/>
      <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 .95-3.4.95-2.6 0-4.8-1.75-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22z"/>
      <path fill="#FBBC05" d="M6.4 13.95a6 6 0 0 1 0-3.9V7.45H3.1a10 10 0 0 0 0 9.1z"/>
      <path fill="#EA4335" d="M12 5.95c1.45 0 2.75.5 3.78 1.48l2.82-2.82A10 10 0 0 0 3.1 7.45l3.3 2.6C7.2 7.7 9.4 5.95 12 5.95z"/>
    </svg>
  );
}

export function IconGitHub(props: Props) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M12 1.5A10.5 10.5 0 0 0 8.7 22c.52.1.71-.23.71-.5v-1.8c-2.9.64-3.52-1.25-3.52-1.25-.48-1.2-1.16-1.53-1.16-1.53-.95-.65.07-.64.07-.64 1.05.07 1.6 1.08 1.6 1.08.93 1.6 2.45 1.14 3.05.87.1-.68.36-1.14.66-1.4-2.32-.27-4.76-1.16-4.76-5.16 0-1.14.4-2.07 1.07-2.8-.1-.27-.46-1.33.1-2.78 0 0 .88-.28 2.88 1.07a9.9 9.9 0 0 1 5.24 0c2-1.35 2.87-1.07 2.87-1.07.57 1.45.21 2.51.1 2.78.67.73 1.07 1.66 1.07 2.8 0 4.01-2.45 4.89-4.78 5.15.38.32.71.95.71 1.92v2.85c0 .28.19.61.72.5A10.5 10.5 0 0 0 12 1.5z"/>
    </svg>
  );
}
