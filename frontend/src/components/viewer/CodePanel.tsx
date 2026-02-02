import { Highlight, themes } from "prism-react-renderer";
import type { TurnRecord } from "../../types/api";

interface CodePanelProps {
  turn: TurnRecord | null;
}

export function CodePanel({ turn }: CodePanelProps) {
  const success = turn?.execution_success ?? true;

  return (
    <div className="panel flex flex-col overflow-hidden">
      <div className="panel-header flex items-center justify-between">
        <span>Code</span>
        {turn && (
          <span
            className={`text-xs ${success ? "text-accent-green" : "text-accent-red"}`}
          >
            {success ? "OK" : "FAIL"}
          </span>
        )}
      </div>
      <div className="panel-body flex-1 overflow-y-auto">
        {turn?.code ? (
          <>
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
          </>
        ) : (
          <span className="text-sm text-text-muted">No code executed</span>
        )}
      </div>
    </div>
  );
}
