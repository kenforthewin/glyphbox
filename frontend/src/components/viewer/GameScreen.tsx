import { useMemo } from "react";
import type { TurnRecord } from "../../types/api";
import {
  decodeColors,
  buildColorRuns,
  getColorStyle,
} from "../../utils/nethackColors";

interface GameScreenProps {
  turn: TurnRecord | null;
}

export function GameScreen({ turn }: GameScreenProps) {
  const coloredLines = useMemo(() => {
    if (!turn?.game_screen) return null;
    if (!turn.game_screen_colors) return null;

    const colorData = decodeColors(turn.game_screen_colors);
    if (!colorData) return null;

    const lines = turn.game_screen.split("\n");
    return lines.map((line, rowIdx) => {
      const colorRow = colorData.subarray(rowIdx * 80, (rowIdx + 1) * 80);
      // Pad line to match color data width
      const paddedLine = line.padEnd(80);
      const runs = buildColorRuns(paddedLine, colorRow);
      return { runs, key: rowIdx };
    });
  }, [turn?.game_screen, turn?.game_screen_colors]);

  return (
    <div className="panel">
      <div className="panel-header">Game Screen</div>
      <div className="panel-body">
        <div className="game-screen text-text-primary">
          {!turn?.game_screen ? (
            "Waiting for game data..."
          ) : coloredLines ? (
            coloredLines.map(({ runs, key }) => (
              <div key={key}>
                {runs.map((run, i) => {
                  const style = getColorStyle(run.colorIndex);
                  return Object.keys(style).length > 0 ? (
                    <span key={i} style={style}>
                      {run.text}
                    </span>
                  ) : (
                    <span key={i}>{run.text}</span>
                  );
                })}
              </div>
            ))
          ) : (
            turn.game_screen
          )}
        </div>
      </div>
    </div>
  );
}
