interface GameMessageListProps {
  messages: string[];
}

export function GameMessageList({ messages }: GameMessageListProps) {
  if (messages.length === 0) {
    return <span className="text-xs text-text-muted">No game messages</span>;
  }

  return (
    <ul className="space-y-0.5">
      {messages.map((msg, i) => (
        <li key={i} className="font-mono text-xs text-text-secondary">
          {msg}
        </li>
      ))}
    </ul>
  );
}
