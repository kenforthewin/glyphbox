import { useEffect } from "react";

interface AboutModalProps {
  onClose: () => void;
}

export function AboutModal({ onClose }: AboutModalProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="panel mx-4 max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-header flex items-center justify-between">
          <span>About Glyphbox</span>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary"
          >
            &times;
          </button>
        </div>
        <div className="panel-body space-y-3 text-sm text-text-secondary">
          <p>
            Glyphbox is a self-programming NetHack agent. An LLM writes and
            executes Python code each turn to play the game through a high-level
            API.
          </p>
          <p>
            Watch runs live as they happen, or replay past games turn by turn.
            Each turn shows the game screen, the LLM's reasoning, and the code
            it wrote.
          </p>
          <div className="border-t border-border-dim pt-3 text-xs text-text-muted">
            <a
              href="https://github.com/kenforthewin/glyphbox"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text-secondary"
            >
              GitHub &rarr;
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
