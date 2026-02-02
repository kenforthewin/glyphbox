import type { ApiCall } from "../../types/api";

interface ApiCallListProps {
  calls: ApiCall[];
}

export function ApiCallList({ calls }: ApiCallListProps) {
  if (calls.length === 0) {
    return <span className="text-xs text-text-muted">No API calls</span>;
  }

  return (
    <ul className="space-y-0.5">
      {calls.map((call, i) => (
        <li key={i} className="font-mono text-xs">
          <span className={call.success ? "text-accent-green" : "text-accent-red"}>
            {call.success ? "+" : "x"}
          </span>{" "}
          <span className="text-text-primary">{call.method}</span>
          <span className="text-text-muted">
            ({Array.isArray(call.args) ? call.args.map((a) => JSON.stringify(a)).join(", ") : String(call.args ?? "")})
          </span>
          {call.error && (
            <span className="text-accent-red"> — {call.error}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
