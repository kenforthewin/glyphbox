import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Header } from "../components/layout/Header";
import { useModels } from "../hooks/useModels";
import { useAuth } from "../hooks/useAuth";
import { ModelSelect } from "../components/ModelSelect";
import { api } from "../api/client";

const CHARACTERS = [
  { value: "random", label: "Random" },
  { value: "val-hum-fem-law", label: "Valkyrie (Human/Female/Lawful)" },
  { value: "wiz-elf-cha-mal", label: "Wizard (Elf/Chaotic/Male)" },
  { value: "sam-hum-mal-law", label: "Samurai (Human/Male/Lawful)" },
  { value: "bar-hum-mal-cha", label: "Barbarian (Human/Male/Chaotic)" },
  { value: "pri-hum-fem-neu", label: "Priestess (Human/Female/Neutral)" },
  { value: "rog-hum-mal-cha", label: "Rogue (Human/Male/Chaotic)" },
  { value: "ran-elf-fem-cha", label: "Ranger (Elf/Female/Chaotic)" },
  { value: "mon-hum-mal-neu", label: "Monk (Human/Male/Neutral)" },
];

const REASONING_LEVELS = [
  { value: "none", label: "None" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

export function NewRunPage() {
  const navigate = useNavigate();
  const { isAuthenticated, login } = useAuth();
  const { models, loading: modelsLoading, error: modelsError } = useModels();

  const [model, setModel] = useState("");
  const [character, setCharacter] = useState("random");
  const [temperature, setTemperature] = useState(0.1);
  const [reasoning, setReasoning] = useState("none");
  const [maxTurns, setMaxTurns] = useState(10000);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-select first model once loaded
  if (models.length > 0 && model === "") {
    setModel(models[0].id);
  }

  if (!isAuthenticated) {
    return (
      <PageShell>
        <Header />
        <div className="py-12 text-center text-text-muted">
          <p className="mb-3">You must be logged in to start a run.</p>
          <button
            onClick={login}
            className="rounded border border-border-dim px-3 py-1.5 text-sm text-text-secondary hover:border-text-secondary hover:text-text-primary"
          >
            Login with OpenRouter
          </button>
        </div>
      </PageShell>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!model) return;

    setSubmitting(true);
    setError(null);

    try {
      const res = await api.startRun({
        model,
        character,
        temperature,
        reasoning,
        max_turns: maxTurns,
      });
      navigate(`/runs/${res.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <PageShell>
      <Header />

      <div className="mx-auto max-w-lg">
        <h2 className="mb-4 font-mono text-sm font-medium text-text-primary">
          New Run
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Model */}
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Model
            </label>
            {modelsLoading ? (
              <div className="text-xs text-text-muted">Loading models...</div>
            ) : modelsError ? (
              <div className="text-xs text-accent-red">
                Failed to load models: {modelsError.message}
              </div>
            ) : (
              <ModelSelect
                models={models}
                value={model}
                onChange={setModel}
              />
            )}
          </div>

          {/* Character */}
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Character
            </label>
            <select
              value={character}
              onChange={(e) => setCharacter(e.target.value)}
              className="w-full rounded border border-border-dim bg-bg-secondary px-2 py-1.5 font-mono text-xs text-text-primary focus:border-text-secondary focus:outline-none"
            >
              {CHARACTERS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Temperature */}
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Temperature:{" "}
              <span className="font-mono text-text-primary">
                {temperature.toFixed(1)}
              </span>
            </label>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="w-full accent-accent-cyan"
            />
            <div className="flex justify-between text-[10px] text-text-muted">
              <span>0.0</span>
              <span>1.0</span>
              <span>2.0</span>
            </div>
          </div>

          {/* Reasoning */}
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Reasoning
            </label>
            <select
              value={reasoning}
              onChange={(e) => setReasoning(e.target.value)}
              className="w-full rounded border border-border-dim bg-bg-secondary px-2 py-1.5 font-mono text-xs text-text-primary focus:border-text-secondary focus:outline-none"
            >
              {REASONING_LEVELS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {/* Max Turns */}
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Max Turns
            </label>
            <input
              type="number"
              min="1"
              max="100000"
              value={maxTurns}
              onChange={(e) =>
                setMaxTurns(Math.max(1, parseInt(e.target.value) || 1))
              }
              className="w-full rounded border border-border-dim bg-bg-secondary px-2 py-1.5 font-mono text-xs text-text-primary focus:border-text-secondary focus:outline-none"
            />
          </div>

          {/* Error display */}
          {error && (
            <div className="rounded border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-xs text-accent-red">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting || !model || modelsLoading}
            className="w-full rounded bg-accent-green px-3 py-2 text-sm font-medium text-bg-primary hover:bg-accent-green/80 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Starting..." : "Start Run"}
          </button>
        </form>
      </div>
    </PageShell>
  );
}
