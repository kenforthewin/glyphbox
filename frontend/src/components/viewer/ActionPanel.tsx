import { useState } from "react";
import { Highlight, themes } from "prism-react-renderer";
import type { TurnRecord } from "../../types/api";
import { GameMessageList } from "./GameMessageList";
import { ApiCallList } from "./ApiCallList";

type Tab = "action" | "results" | "inventory" | "dungeon" | "llm";

interface ActionPanelProps {
  turn: TurnRecord | null;
}

const TAB_LABELS: { key: Tab; label: string }[] = [
  { key: "action", label: "Action" },
  { key: "results", label: "Results" },
  { key: "inventory", label: "Inventory" },
  { key: "dungeon", label: "Dungeon" },
  { key: "llm", label: "LLM" },
];

export function ActionPanel({ turn }: ActionPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("action");
  const success = turn?.execution_success ?? true;

  const msgCount = turn?.game_messages.length ?? 0;
  const callCount = turn?.api_calls.length ?? 0;

  return (
    <div className="panel flex min-h-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border-dim">
        <div className="flex">
          {TAB_LABELS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-3 py-1.5 text-xs font-medium tracking-wide transition-colors ${
                activeTab === key
                  ? "border-b-2 border-accent-cyan text-text-primary"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {label}
              {key === "results" && (msgCount > 0 || callCount > 0) && (
                <span className="ml-1 text-text-muted">
                  {msgCount + callCount}
                </span>
              )}
            </button>
          ))}
        </div>
        {activeTab === "action" && turn?.code && (
          <span
            className={`pr-3 text-xs ${success ? "text-accent-green" : "text-accent-red"}`}
          >
            {success ? "OK" : "FAIL"}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "action" && <ActionTab turn={turn} />}
        {activeTab === "results" && <ResultsTab turn={turn} />}
        {activeTab === "inventory" && <InventoryTab turn={turn} />}
        {activeTab === "dungeon" && <DungeonTab turn={turn} />}
        {activeTab === "llm" && <LlmTab turn={turn} />}
      </div>
    </div>
  );
}

function ActionTab({ turn }: { turn: TurnRecord | null }) {
  const success = turn?.execution_success ?? true;

  return (
    <>
      {turn?.llm_reasoning && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
            Reasoning
          </div>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-text-primary">
            {turn.llm_reasoning}
          </pre>
        </div>
      )}

      {turn?.llm_reasoning && turn?.code && (
        <hr className="my-3 border-border-dim" />
      )}

      {turn?.code ? (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
            Code
          </div>
          <Highlight
            theme={themes.nightOwl}
            code={turn.code}
            language="python"
          >
            {({ tokens, getLineProps, getTokenProps }) => (
              <pre className="font-mono text-xs leading-relaxed">
                {tokens.map((line, i) => (
                  <div key={i} {...getLineProps({ line })}>
                    <span className="mr-4 inline-block w-6 text-right text-text-muted select-none">
                      {i + 1}
                    </span>
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </div>
                ))}
              </pre>
            )}
          </Highlight>
          {!success && turn.execution_error && (
            <div className="mt-2 rounded border border-accent-red/30 bg-accent-red/10 px-2 py-1 font-mono text-xs text-accent-red">
              {turn.execution_error}
            </div>
          )}
        </div>
      ) : (
        !turn?.llm_reasoning && (
          <span className="text-sm text-text-muted">No data</span>
        )
      )}
    </>
  );
}

function ResultsTab({ turn }: { turn: TurnRecord | null }) {
  if (!turn) {
    return <span className="text-sm text-text-muted">No data</span>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
          Game Messages
        </div>
        <GameMessageList messages={turn.game_messages} />
      </div>
      <div>
        <div className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
          API Calls
        </div>
        <ApiCallList calls={turn.api_calls} />
      </div>
    </div>
  );
}

function InventoryTab({ turn }: { turn: TurnRecord | null }) {
  const items = turn?.inventory;

  if (!items || items.length === 0) {
    return <span className="text-sm text-text-muted">No inventory data</span>;
  }

  return (
    <ul className="space-y-0.5">
      {items.map((item, i) => (
        <li key={i} className="font-mono text-xs">
          <span className="text-text-muted">{item.slot}:</span>{" "}
          <span className="text-text-primary">
            {item.quantity > 1 ? `${item.quantity} ${item.name}` : item.name}
          </span>
        </li>
      ))}
    </ul>
  );
}

function DungeonTab({ turn }: { turn: TurnRecord | null }) {
  if (!turn?.dungeon_overview) {
    return (
      <span className="text-sm text-text-muted">No dungeon overview data</span>
    );
  }

  return (
    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-text-primary">
      {turn.dungeon_overview}
    </pre>
  );
}

function LlmTab({ turn }: { turn: TurnRecord | null }) {
  if (!turn) {
    return <span className="text-sm text-text-muted">No data</span>;
  }

  const rows: { label: string; value: string; warn?: boolean }[] = [
    { label: "Model", value: turn.llm_model || "—" },
    {
      label: "Finish Reason",
      value: turn.llm_finish_reason || "—",
      warn:
        !!turn.llm_finish_reason &&
        turn.llm_finish_reason !== "stop" &&
        turn.llm_finish_reason !== "tool_calls" &&
        turn.llm_finish_reason !== "end_turn",
    },
    {
      label: "Prompt Tokens",
      value: turn.llm_prompt_tokens?.toLocaleString() ?? "—",
    },
    {
      label: "Completion Tokens",
      value: turn.llm_completion_tokens?.toLocaleString() ?? "—",
    },
    {
      label: "Total Tokens",
      value: turn.llm_total_tokens?.toLocaleString() ?? "—",
    },
  ];

  if (turn.execution_error) {
    rows.push({
      label: "Execution Error",
      value: turn.execution_error,
      warn: true,
    });
  }

  return (
    <dl className="space-y-2">
      {rows.map(({ label, value, warn }) => (
        <div key={label}>
          <dt className="text-xs font-medium uppercase tracking-wider text-text-muted">
            {label}
          </dt>
          <dd
            className={`mt-0.5 font-mono text-xs ${warn ? "text-accent-red" : "text-text-primary"}`}
          >
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
