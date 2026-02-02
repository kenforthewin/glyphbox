import { useState, useRef, useEffect, useMemo } from "react";
import type { ModelInfo } from "../types/api";

interface ModelSelectProps {
  models: ModelInfo[];
  value: string;
  onChange: (modelId: string) => void;
}

function fuzzyMatch(query: string, text: string): boolean {
  const lower = text.toLowerCase();
  let qi = 0;
  for (let i = 0; i < lower.length && qi < query.length; i++) {
    if (lower[i] === query[qi]) qi++;
  }
  return qi === query.length;
}

export function ModelSelect({ models, value, onChange }: ModelSelectProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedModel = models.find((m) => m.id === value);

  const filtered = useMemo(() => {
    if (!query) return models;
    const q = query.toLowerCase();
    return models.filter(
      (m) => fuzzyMatch(q, m.id) || fuzzyMatch(q, m.name),
    );
  }, [models, query]);

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightIndex(0);
  }, [filtered.length]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (!open || !listRef.current) return;
    const item = listRef.current.children[highlightIndex] as HTMLElement;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, open]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selectModel = (modelId: string) => {
    onChange(modelId);
    setQuery("");
    setOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (filtered[highlightIndex]) {
          selectModel(filtered[highlightIndex].id);
        }
        break;
      case "Escape":
        e.preventDefault();
        setOpen(false);
        setQuery("");
        break;
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={inputRef}
        type="text"
        value={open ? query : selectedModel?.name ?? ""}
        placeholder="Search models..."
        onChange={(e) => {
          setQuery(e.target.value);
          if (!open) setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onKeyDown={handleKeyDown}
        className="w-full rounded border border-border-dim bg-bg-secondary px-2 py-1.5 font-mono text-xs text-text-primary focus:border-text-secondary focus:outline-none"
      />
      {open && (
        <div
          ref={listRef}
          className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded border border-border-dim bg-bg-secondary shadow-lg"
        >
          {filtered.length === 0 ? (
            <div className="px-2 py-2 text-xs text-text-muted">
              No models match
            </div>
          ) : (
            filtered.map((m, i) => (
              <button
                key={m.id}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectModel(m.id);
                }}
                onMouseEnter={() => setHighlightIndex(i)}
                className={`flex w-full flex-col px-2 py-1.5 text-left ${
                  i === highlightIndex
                    ? "bg-bg-tertiary text-text-primary"
                    : "text-text-secondary hover:bg-bg-tertiary"
                } ${m.id === value ? "border-l-2 border-accent-cyan" : ""}`}
              >
                <span className="font-mono text-xs">{m.name}</span>
                <span className="text-[10px] text-text-muted">
                  {m.id} &middot; {m.context_length.toLocaleString()} ctx
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
