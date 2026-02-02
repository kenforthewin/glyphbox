import { useState } from "react";
import type { TurnRecord } from "../../types/api";
import { GameMessageList } from "./GameMessageList";
import { ApiCallList } from "./ApiCallList";

interface ExecutionDetailsProps {
  turn: TurnRecord | null;
}

export function ExecutionDetails({ turn }: ExecutionDetailsProps) {
  const [open, setOpen] = useState(false);

  const msgCount = turn?.game_messages.length ?? 0;
  const callCount = turn?.api_calls.length ?? 0;

  return (
    <div className="panel">
      <button
        onClick={() => setOpen(!open)}
        className="panel-header flex w-full cursor-pointer items-center justify-between text-left"
      >
        <span>
          Execution Details
          <span className="ml-2 text-text-muted">
            {msgCount} msgs / {callCount} calls
          </span>
        </span>
        <span className="text-text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && turn && (
        <div className="panel-body grid grid-cols-2 gap-4">
          <div>
            <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
              Game Messages
            </h4>
            <GameMessageList messages={turn.game_messages} />
          </div>
          <div>
            <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
              API Calls
            </h4>
            <ApiCallList calls={turn.api_calls} />
          </div>
        </div>
      )}
    </div>
  );
}
