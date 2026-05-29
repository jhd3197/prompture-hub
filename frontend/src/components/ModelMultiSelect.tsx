import { useState, type KeyboardEvent } from "react";
import { IconX } from "../icons";
import { ModelSelect } from "./ModelSelect";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}

/**
 * Multi-pick combobox: typed value gets added as a chip on Enter / comma,
 * each chip has an inline remove button. Backed by ``ModelSelect``'s
 * cached `/api/models` dropdown so the user sees the same provider/model
 * routes the hub knows about.
 *
 * The selected chips are exactly the array the API expects — the parent
 * doesn't need to parse anything.
 */
export function ModelMultiSelect({
  value, onChange, placeholder = "openai/gpt-4o",
}: Props) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const next = draft.trim().replace(/,$/, "");
    if (!next) return;
    if (value.includes(next)) {
      setDraft("");
      return;
    }
    onChange([...value, next]);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && value.length > 0) {
      // Pop the last chip when the input is empty.
      onChange(value.slice(0, -1));
    }
  };

  const remove = (m: string) => onChange(value.filter(v => v !== m));

  return (
    <div
      style={{
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--r-sm)",
        background: "var(--surface)",
        padding: 6,
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
        alignItems: "center",
      }}
    >
      {value.map(m => (
        <span
          key={m}
          className="cap"
          style={{ fontFamily: "var(--font-mono)", padding: "3px 4px 3px 8px" }}
        >
          {m}
          <button
            type="button"
            onClick={() => remove(m)}
            aria-label={`Remove ${m}`}
            style={{
              marginLeft: 4,
              border: "none",
              background: "transparent",
              color: "inherit",
              cursor: "pointer",
              padding: "1px 3px",
              borderRadius: 3,
              display: "inline-flex",
              alignItems: "center",
            }}
          >
            <IconX style={{ width: 10, height: 10 }} />
          </button>
        </span>
      ))}
      <div
        style={{ flex: 1, minWidth: 160 }}
        // Override the bare ModelSelect input so it blends into the chip
        // container: no border, transparent background, normal padding.
        className="model-multi-input"
      >
        <ModelSelect
          value={draft}
          onChange={setDraft}
          onKeyDown={onKeyDown}
          placeholder={value.length === 0 ? placeholder : "+ add another…"}
          className="mono"
        />
        <style>{`
          .model-multi-input input {
            width: 100%;
            border: none;
            outline: none;
            background: transparent;
            color: var(--text);
            font-size: 13px;
            padding: 4px 4px;
          }
          .model-multi-input input::placeholder {
            color: var(--text-faint);
          }
        `}</style>
      </div>
      {draft && (
        <button
          type="button"
          onClick={commit}
          className="btn btn-sm"
          style={{ padding: "4px 8px" }}
        >
          Add
        </button>
      )}
    </div>
  );
}
