import type { TurnRecord } from "../../types/api";

interface StatsBarProps {
  turn: TurnRecord | null;
}

function hpColor(hp: number, maxHp: number): string {
  const ratio = maxHp > 0 ? hp / maxHp : 0;
  if (ratio > 0.5) return "text-accent-green";
  if (ratio > 0.25) return "text-accent-yellow";
  return "text-accent-red";
}

export function StatsBar({ turn }: StatsBarProps) {
  if (!turn) {
    return (
      <div className="flex gap-6 rounded border border-border-dim bg-bg-secondary px-3 py-2 font-mono text-xs text-text-muted">
        No data
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 rounded border border-border-dim bg-bg-secondary px-3 py-2 font-mono text-xs">
      <span>
        HP:{" "}
        <span className={hpColor(turn.hp, turn.max_hp)}>
          {turn.hp}/{turn.max_hp}
        </span>
      </span>
      <span>
        GT: <span className="text-text-primary">{turn.game_turn}</span>
      </span>
      <span>
        DL: <span className="text-text-primary">{turn.dungeon_level}</span>
      </span>
      <span>
        XL: <span className="text-text-primary">{turn.xp_level}</span>
      </span>
      <span>
        Score: <span className="text-accent-cyan">{turn.score}</span>
      </span>
      <span>
        Hunger:{" "}
        <span className="text-text-secondary">{turn.hunger || "—"}</span>
      </span>
    </div>
  );
}
