import { useEffect, useId, useState } from "react";
import { api } from "../api";

interface Props {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  id?: string;
  className?: string;
}

interface DirCache {
  workspace: string;
  dirs: string[];
  truncated: boolean;
}

let _cache: Promise<DirCache> | null = null;

function loadDirs(force = false): Promise<DirCache> {
  if (!_cache || force) {
    _cache = api.workspaceDirs()
      .then(d => ({
        workspace: d.workspace,
        dirs: d.dirs,
        truncated: d.truncated,
      }))
      .catch(() => ({ workspace: "", dirs: [], truncated: false }));
  }
  return _cache;
}

export function resetFolderPickerCache() {
  _cache = null;
}

/**
 * Subpath combobox: existing subdirs under ``HUB_AGENT_WORKSPACE`` get
 * autocompleted via `<datalist>`, but the user can still type any
 * relative path — the backend creates it on demand inside the workspace
 * (and refuses anything that escapes the tree).
 */
export function FolderPicker({
  value, onChange, placeholder, id, className = "input mono",
}: Props) {
  const generatedId = useId();
  const listId = `${id || generatedId}-folders`;
  const [data, setData] = useState<DirCache>({ workspace: "", dirs: [], truncated: false });

  useEffect(() => {
    let alive = true;
    loadDirs().then(d => { if (alive) setData(d); });
    return () => { alive = false; };
  }, []);

  return (
    <>
      <input
        id={id}
        list={listId}
        className={className}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
      />
      <datalist id={listId}>
        {data.dirs.map(d => <option key={d} value={d} />)}
      </datalist>
    </>
  );
}
