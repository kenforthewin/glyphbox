import type { TurnRecord } from "../../types/api";

interface GameScreenProps {
  turn: TurnRecord | null;
}

export function GameScreen({ turn }: GameScreenProps) {
  return (
    <div className="panel">
      <div className="panel-header">Game Screen</div>
      <div className="panel-body">
        <div className="game-screen text-text-primary">
          {turn?.game_screen ?? "Waiting for game data..."}
        </div>
      </div>
    </div>
  );
}
