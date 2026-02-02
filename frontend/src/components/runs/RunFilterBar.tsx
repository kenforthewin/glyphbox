import { useState, useEffect } from "react";
import { api } from "../../api/client";

interface RunFilterBarProps {
  sortBy: "recent" | "score" | "depth";
  model: string;
  onSortChange: (sort: "recent" | "score" | "depth") => void;
  onModelChange: (model: string) => void;
}

export function RunFilterBar({
  sortBy,
  model,
  onSortChange,
  onModelChange,
}: RunFilterBarProps) {
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    api.getRunModels().then(setModels).catch(() => {});
  }, []);

  return (
    <div className="mb-3 flex items-center gap-3">
      <label className="flex items-center gap-1.5 text-xs text-text-muted">
        Model
        <select
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          className="rounded border border-border-dim bg-bg-secondary px-2 py-1 text-xs text-text-primary"
        >
          <option value="">All</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-1.5 text-xs text-text-muted">
        Sort
        <select
          value={sortBy}
          onChange={(e) =>
            onSortChange(e.target.value as "recent" | "score" | "depth")
          }
          className="rounded border border-border-dim bg-bg-secondary px-2 py-1 text-xs text-text-primary"
        >
          <option value="recent">Recent</option>
          <option value="score">Highest Score</option>
          <option value="depth">Deepest</option>
        </select>
      </label>
    </div>
  );
}
