import { useParams } from "react-router-dom";
import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { Header } from "../components/layout/Header";
import { StatusBadge } from "../components/runs/StatusBadge";
import { LiveBadge } from "../components/viewer/LiveBadge";
import { StatsBar } from "../components/viewer/StatsBar";
import { GameScreen } from "../components/viewer/GameScreen";
import { ActionPanel } from "../components/viewer/ActionPanel";
import { TurnScrubber } from "../components/viewer/TurnScrubber";
import { useRun } from "../hooks/useRun";
import { useTurns } from "../hooks/useTurns";
import { useLiveStream } from "../hooks/useLiveStream";
import { useTurnNavigation } from "../hooks/useTurnNavigation";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

export function RunViewerPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, loading: runLoading, error: runError, setRun } = useRun(runId!);

  const isRunning = run?.status === "running" || run?.status === "starting";

  // Replay mode: batch-fetch all turns for finished runs
  const {
    turns: replayTurns,
    loading: turnsLoading,
    error: turnsError,
  } = useTurns(runId!);

  // Live mode: WebSocket for running runs
  const {
    turns: liveTurns,
    connected,
    runEnded,
  } = useLiveStream(runId!, isRunning);

  // Update run status when WebSocket reports run ended
  if (runEnded && isRunning) {
    setRun(runEnded);
  }

  // Pick turn source: keep live turns if we have them (even after run ends),
  // only fall back to replay turns for fresh page loads of finished runs.
  const turns = liveTurns.length > 0 ? liveTurns : replayTurns;

  const nav = useTurnNavigation(turns);

  // Auto-play: advance one turn every 3s (replay mode only).
  // For non-live runs, start from turn 0 with auto-play on by default.
  const [autoPlay, setAutoPlay] = useState(false);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    if (!run || nav.totalTurns === 0) return;
    const live = run.status === "running" || run.status === "starting";
    if (!live) {
      nav.goFirst();
      setAutoPlay(true);
    }
    initializedRef.current = true;
  }, [run, nav.totalTurns, nav.goFirst]);

  const toggleAutoPlay = useCallback(() => setAutoPlay((v) => !v), []);

  useEffect(() => {
    if (!autoPlay) return;
    if (nav.currentIndex >= nav.totalTurns - 1) {
      setAutoPlay(false);
      return;
    }
    const id = setInterval(() => {
      nav.goNext();
    }, 3000);
    return () => clearInterval(id);
  }, [autoPlay, nav.currentIndex, nav.totalTurns, nav.goNext]);

  // Stop auto-play when entering live mode
  useEffect(() => {
    if (nav.isLive) setAutoPlay(false);
  }, [nav.isLive]);

  const keyMap = useMemo(
    () => ({
      ArrowLeft: nav.goPrev,
      ArrowRight: nav.goNext,
      Home: nav.goFirst,
      End: nav.goLast,
    }),
    [nav.goPrev, nav.goNext, nav.goFirst, nav.goLast],
  );
  useKeyboardShortcuts(keyMap);

  if (runLoading) {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-4 font-sans">
        <div className="mx-auto max-w-[1600px]">
          <Header />
          <div className="py-12 text-center text-text-muted">Loading run...</div>
        </div>
      </div>
    );
  }

  if (runError || !run) {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-4 font-sans">
        <div className="mx-auto max-w-[1600px]">
          <Header />
          <div className="py-12 text-center text-accent-red">
            {runError?.message ?? "Run not found"}
          </div>
        </div>
      </div>
    );
  }

  const loading = liveTurns.length > 0 ? false : isRunning ? false : turnsLoading;
  const error = liveTurns.length > 0 ? null : isRunning ? null : turnsError;

  return (
    <div className="flex h-screen flex-col bg-bg-primary font-sans">
      <div className="mx-auto w-full max-w-[1600px] flex-1 overflow-hidden px-4 pt-4">
        <div className="flex h-full flex-col">
          <Header>
            <span className="font-mono text-xs text-text-secondary">
              {run.run_id}
            </span>
            <StatusBadge status={run.status} />
            {isRunning && <LiveBadge connected={connected} />}
          </Header>

          {error && (
            <div className="mb-2 text-sm text-accent-red">{error.message}</div>
          )}

          {loading ? (
            <div className="py-12 text-center text-text-muted">
              Loading turns...
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto pb-2">
              <StatsBar turn={nav.currentTurn} />

              <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-[minmax(680px,auto)_1fr]">
                <GameScreen turn={nav.currentTurn} />
                <ActionPanel turn={nav.currentTurn} />
              </div>
            </div>
          )}
        </div>
      </div>

      {!loading && (
        <div className="sticky bottom-0 border-t border-border-dim bg-bg-primary px-4 py-2">
          <div className="mx-auto max-w-[1600px]">
            <TurnScrubber
              currentIndex={nav.currentIndex}
              totalTurns={nav.totalTurns}
              isLive={nav.isLive}
              currentTurn={nav.currentTurn}
              onGoFirst={nav.goFirst}
              onGoPrev={nav.goPrev}
              onGoNext={nav.goNext}
              onGoLast={nav.goLast}
              onGoToTurn={nav.goToTurn}
              onJumpToLive={nav.jumpToLive}
              showLiveButton={isRunning}
              autoPlay={autoPlay}
              onToggleAutoPlay={toggleAutoPlay}
            />
          </div>
        </div>
      )}
    </div>
  );
}
