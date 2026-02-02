interface LiveBadgeProps {
  connected: boolean;
}

export function LiveBadge({ connected }: LiveBadgeProps) {
  if (!connected) return null;

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-red/15 px-2 py-0.5 text-xs font-medium text-accent-red">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-red" />
      LIVE
    </span>
  );
}
