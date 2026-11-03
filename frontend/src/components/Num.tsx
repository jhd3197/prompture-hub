import { useCountUp } from "../util/hooks";

/** A figure that counts up to its value. A hidden copy of the final text holds the width, so nothing shifts. */
export function Num({ value, format = String }: { value: number; format?: (v: number) => string }) {
  const shown = useCountUp(value);
  const final = format(value);
  return (
    <span className="countup">
      <span className="countup-ghost" aria-hidden="true">{final}</span>
      <span aria-hidden="true">{format(shown)}</span>
      <span className="sr-only">{final}</span>
    </span>
  );
}
