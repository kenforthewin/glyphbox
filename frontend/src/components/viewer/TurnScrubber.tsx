import type { TurnRecord } from "../../types/api";

interface TurnScrubberProps {
  currentIndex: number;
  totalTurns: number;
  isLive: boolean;
  currentTurn: TurnRecord | null;
  onGoFirst: () => void;
  onGoPrev: () => void;
  onGoNext: () => void;
  onGoLast: () => void;
  onGoToTurn: (index: number) => void;
  onJumpToLive: () => void;
  showLiveButton: boolean;
}

const btnClass =
  "px-2 py-1 text-xs font-mono text-text-secondary hover:text-text-primary hover:bg-bg-tertiary rounded disabled:opacity-30 disabled:cursor-default";

export function TurnScrubber({
  currentIndex,
  totalTurns,
  isLive,
  currentTurn,
  onGoFirst,
  onGoPrev,
  onGoNext,
  onGoLast,
  onGoToTurn,
  onJumpToLive,
  showLiveButton,
}: TurnScrubberProps) {
  return (
    <div className="flex items-center gap-3 rounded border border-border-dim bg-bg-secondary px-3 py-2">
      <div className="flex items-center gap-1">
        <button
          className={btnClass}
          onClick={onGoFirst}
          disabled={currentIndex <= 0}
        >
          |&larr;
        </button>
        <button
          className={btnClass}
          onClick={onGoPrev}
          disabled={currentIndex <= 0}
        >
          &larr;
        </button>
        <button
          className={btnClass}
          onClick={onGoNext}
          disabled={isLive || currentIndex >= totalTurns - 1}
        >
          &rarr;
        </button>
        <button className={btnClass} onClick={onGoLast}>
          &rarr;|
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(0, totalTurns - 1)}
        value={currentIndex}
        onChange={(e) => onGoToTurn(Number(e.target.value))}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-border-dim accent-accent-cyan"
      />

      <div className="flex items-center gap-3 font-mono text-xs text-text-muted">
        <span>
          Turn{" "}
          <span className="text-text-primary">{currentIndex + 1}</span>/
          {totalTurns}
        </span>
        {currentTurn && (
          <span>
            GT{" "}
            <span className="text-text-secondary">
              {currentTurn.game_turn}
            </span>
          </span>
        )}
      </div>

      {showLiveButton && (
        <button
          onClick={onJumpToLive}
          className={`rounded px-2 py-1 text-xs font-medium ${
            isLive
              ? "bg-accent-red/15 text-accent-red"
              : "bg-bg-tertiary text-text-secondary hover:text-accent-red"
          }`}
        >
          LIVE
        </button>
      )}
    </div>
  );
}
