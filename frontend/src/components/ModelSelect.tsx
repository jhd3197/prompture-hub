import { useEffect, useId, useState, type KeyboardEventHandler } from "react";
import { api } from "../api";

interface BaseProps {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  /**
   * When set, restricts the dropdown to models from this provider
   * (e.g. ``"openai"``). Useful for the agent "model override" field
   * where a Codex CLI run only accepts OpenAI models.
   */
  providerFilter?: string;
  /**
   * When true, the dropdown shows bare model ids (``gpt-4o``). When false,
   * it shows full provider/model routes (``openai/gpt-4o``). Defaults to
   * provider/model so the same picker works for hub keys.
   */
  bareModelIds?: boolean;
  className?: string;
  id?: string;
  autoFocus?: boolean;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
}

interface DiscoveredModel {
  route: string;     // openai/gpt-4o
  bare: string;      // gpt-4o
  provider: string;  // openai
}

let _modelCache: Promise<DiscoveredModel[]> | null = null;

function loadModels(): Promise<DiscoveredModel[]> {
  if (_modelCache) return _modelCache;
  _modelCache = api.models()
    .then(d => {
      const out: DiscoveredModel[] = [];
      for (const g of d.groups) {
        for (const m of g.models) {
          out.push({
            route: `${g.provider}/${m}`,
            bare: m,
            provider: g.provider,
          });
        }
      }
      return out;
    })
    .catch(() => []);
  return _modelCache;
}

/** Reset the in-memory cache. Call after the operator refreshes /api/models. */
export function resetModelSelectCache() {
  _modelCache = null;
}

/**
 * Native combobox: a normal `<input>` backed by a `<datalist>`. Browsers
 * render the dropdown + autocomplete for free; the user can still type
 * any string the agent's CLI accepts (CLI-specific model ids that
 * Prompture's discovery doesn't surface).
 */
export function ModelSelect({
  value, onChange, placeholder, providerFilter,
  bareModelIds = false, className = "input mono", id, autoFocus, onKeyDown,
}: BaseProps) {
  const generatedId = useId();
  const listId = `${id || generatedId}-models`;
  const [models, setModels] = useState<DiscoveredModel[]>([]);

  useEffect(() => {
    let alive = true;
    loadModels().then(m => { if (alive) setModels(m); });
    return () => { alive = false; };
  }, []);

  const options = models
    .filter(m => !providerFilter || m.provider === providerFilter)
    .map(m => (bareModelIds ? m.bare : m.route));

  // Dedupe (some providers expose the same model id via aliases).
  const unique = Array.from(new Set(options)).sort();

  return (
    <>
      <input
        id={id}
        list={listId}
        className={className}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete="off"
        spellCheck={false}
        onKeyDown={onKeyDown}
      />
      <datalist id={listId}>
        {unique.map(o => <option key={o} value={o} />)}
      </datalist>
    </>
  );
}
