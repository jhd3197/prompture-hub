import { Link } from "react-router-dom";
import { IconLayers } from "../icons";

export function Brand({ as = "link" }: { as?: "link" | "static" }) {
  const inner = (
    <>
      <span className="brand-mark"><IconLayers style={{ width: 16, height: 16 }} /></span>
      <span className="brand-name"><b>Prompture</b> <span>Hub</span></span>
    </>
  );
  if (as === "static") return <div className="brand">{inner}</div>;
  return <Link to="/" className="brand" aria-label="Prompture Hub home">{inner}</Link>;
}
