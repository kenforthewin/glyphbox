import { Highlight, themes } from "prism-react-renderer";
import type { TurnRecord } from "../../types/api";

interface ReasoningCodePanelProps {
  turn: TurnRecord | null;
}

export function ReasoningCodePanel({ turn }: ReasoningCodePanelProps) {
  const success = turn?.execution_success ?? true;

  return (
    <div className="panel flex min-h-0 flex-col overflow-hidden">
      {turn?.code && (
        <div className="panel-header flex items-center justify-end">
          <span
            className={`text-xs ${success ? "text-accent-green" : "text-accent-red"}`}
          >
            {success ? "OK" : "FAIL"}
          </span>
        </div>
      )}
      <div className="panel-body flex-1 overflow-y-auto">
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
            {turn.execution_error && (
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
      </div>
    </div>
  );
}
