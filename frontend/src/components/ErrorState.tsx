import { IconAlert, IconRefresh } from "../icons";

/** A failed load: what failed, the server's reason, and a retry that re-runs the request. */
export function ErrorState({
  title, error, onRetry,
}: {
  title: string;
  error: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state bad" role="alert">
      <div className="state-ico"><IconAlert /></div>
      <h3>{title}</h3>
      <p>The hub did not answer as expected. Nothing was changed.</p>
      <p className="state-detail">{error}</p>
      {onRetry && (
        <div className="state-actions">
          <button type="button" className="btn" onClick={onRetry}><IconRefresh />Try again</button>
        </div>
      )}
    </div>
  );
}
