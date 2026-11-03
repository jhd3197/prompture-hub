import { useCountUp } from "../util/hooks";

/** A figure that counts up to its value. A hidden copy of the final text holds the width, so nothing shifts. */
/** Mono gives "." a full cell, so a figure reads "29 . 22"; narrow the punctuation so it reads as one number. */
const tight = (t: string) => t.split(/([.,:])/).map((c, i) => (i % 2 ? <span key={i} className="pn">{c}</span> : c));

export function Num({ value, format = String }: { value: number; format?: (v: number) => string }) {
  const shown = useCountUp(value);
  const final = format(value);
  return (
    <span className="countup">
      <span className="countup-ghost" aria-hidden="true">{tight(final)}</span>
      <span aria-hidden="true">{tight(format(shown))}</span>
      <span className="sr-only">{final}</span>
    </span>
  );
}
