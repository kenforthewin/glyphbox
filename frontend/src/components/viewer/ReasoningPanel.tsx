import type { TurnRecord } from "../../types/api";

interface ReasoningPanelProps {
  turn: TurnRecord | null;
}

export function ReasoningPanel({ turn }: ReasoningPanelProps) {
  return (
    <div className="panel flex flex-col overflow-hidden">
      <div className="panel-header">Reasoning</div>
      <div className="panel-body flex-1 overflow-y-auto">
        {turn?.llm_reasoning ? (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-text-primary">
            {turn.llm_reasoning}
          </pre>
        ) : (
          <span className="text-sm text-text-muted">No reasoning data</span>
        )}
      </div>
    </div>
  );
}
