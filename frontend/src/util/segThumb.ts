/** Gives every `.seg` a sliding thumb: measure the selected button and publish its box as CSS variables. */
export function startSegThumbs(): () => void {
  const place = (seg: HTMLElement) => {
    if (!seg.querySelector(":scope > .seg-thumb")) { // a real element: a pseudo-element over the labels would hide them from contrast checks
      const t = document.createElement("i");
      t.className = "seg-thumb"; t.setAttribute("aria-hidden", "true");
      seg.prepend(t);
    }
    const on = seg.querySelector<HTMLElement>('button.on, button[aria-checked="true"]');
    if (!on) { seg.style.setProperty("--thumb-w", "0px"); return; }
    seg.style.setProperty("--thumb-x", `${on.offsetLeft}px`);
    seg.style.setProperty("--thumb-y", `${on.offsetTop}px`);
    seg.style.setProperty("--thumb-w", `${on.offsetWidth}px`);
    seg.style.setProperty("--thumb-h", `${on.offsetHeight}px`);
    if (!seg.dataset.thumb) { // first placement snaps; later ones slide
      seg.dataset.thumb = "on";
      requestAnimationFrame(() => requestAnimationFrame(() => { seg.dataset.thumb = "live"; }));
    }
  };
  const all = () => document.querySelectorAll<HTMLElement>(".seg").forEach(place);
  const mo = new MutationObserver(() => requestAnimationFrame(all));
  mo.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-checked"] });
  window.addEventListener("resize", all);
  document.fonts?.ready.then(all);
  all();
  return () => { mo.disconnect(); window.removeEventListener("resize", all); };
}
