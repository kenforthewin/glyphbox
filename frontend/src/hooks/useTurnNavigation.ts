import { useState, useCallback, useMemo } from "react";
import type { TurnRecord } from "../types/api";

export function useTurnNavigation(turns: TurnRecord[]) {
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const [isLive, setIsLive] = useState(true);

  const totalTurns = turns.length;

  const effectiveIndex = useMemo(() => {
    if (isLive || currentIndex < 0) return Math.max(0, totalTurns - 1);
    return Math.min(currentIndex, totalTurns - 1);
  }, [currentIndex, isLive, totalTurns]);

  const currentTurn = turns[effectiveIndex] ?? null;

  const goToTurn = useCallback((index: number) => {
    setCurrentIndex(index);
    setIsLive(false);
  }, []);

  const goNext = useCallback(() => {
    if (effectiveIndex >= totalTurns - 1) {
      setIsLive(true);
      setCurrentIndex(-1);
    } else {
      setCurrentIndex(effectiveIndex + 1);
      setIsLive(false);
    }
  }, [effectiveIndex, totalTurns]);

  const goPrev = useCallback(() => {
    if (effectiveIndex > 0) {
      setCurrentIndex(effectiveIndex - 1);
      setIsLive(false);
    }
  }, [effectiveIndex]);

  const goFirst = useCallback(() => {
    setCurrentIndex(0);
    setIsLive(false);
  }, []);

  const goLast = useCallback(() => {
    setIsLive(true);
    setCurrentIndex(-1);
  }, []);

  const jumpToLive = useCallback(() => {
    setIsLive(true);
    setCurrentIndex(-1);
  }, []);

  return {
    currentTurn,
    currentIndex: effectiveIndex,
    totalTurns,
    isLive,
    goToTurn,
    goNext,
    goPrev,
    goFirst,
    goLast,
    jumpToLive,
  };
}
