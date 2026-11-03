import { Link } from "react-router-dom";
import { IconMark } from "../icons";

export function Brand({ as = "link" }: { as?: "link" | "static" }) {
  const inner = (
    <>
      <IconMark className="brand-mark" />
      <span className="brand-name"><b>Prompture</b>{" "}<span>Hub</span></span>
    </>
  );
  if (as === "static") return <div className="brand">{inner}</div>;
  return <Link to="/" className="brand" title="Prompture Hub home">{inner}</Link>;
}
