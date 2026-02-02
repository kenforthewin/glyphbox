import { useParams } from "react-router-dom";
import { useMemo } from "react";
import { PageShell } from "../components/layout/PageShell";
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
      <PageShell>
        <Header />
        <div className="py-12 text-center text-text-muted">Loading run...</div>
      </PageShell>
    );
  }

  if (runError || !run) {
    return (
      <PageShell>
        <Header />
        <div className="py-12 text-center text-accent-red">
          {runError?.message ?? "Run not found"}
        </div>
      </PageShell>
    );
  }

  const loading = liveTurns.length > 0 ? false : isRunning ? false : turnsLoading;
  const error = liveTurns.length > 0 ? null : isRunning ? null : turnsError;

  return (
    <PageShell>
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
        <>
          <StatsBar turn={nav.currentTurn} />

          <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-[minmax(680px,auto)_1fr]">
            <GameScreen turn={nav.currentTurn} />
            <ActionPanel turn={nav.currentTurn} />
          </div>

          <div className="mt-2">
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
            />
          </div>
        </>
      )}
    </PageShell>
  );
}
