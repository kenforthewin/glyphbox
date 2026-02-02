import { useState } from "react";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../api/client";
import { AboutModal } from "./AboutModal";

interface HeaderProps {
  children?: ReactNode;
}

export function Header({ children }: HeaderProps) {
  const { user, isLoading, authEnabled, login, logout, setUser } = useAuth();
  const [showAbout, setShowAbout] = useState(false);
  const [editing, setEditing] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  const startEditing = () => {
    setNameInput(user?.display_name ?? "");
    setEditError("");
    setEditing(true);
  };

  const saveName = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed || trimmed === user?.display_name) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setEditError("");
    try {
      const updated = await api.updateProfile({ display_name: trimmed });
      setUser(updated);
      setEditing(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to update";
      if (msg.includes("409")) {
        setEditError("Username taken");
      } else if (msg.includes("400")) {
        setEditError("3-30 chars, a-z/0-9/-/_");
      } else {
        setEditError("Error saving");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className="mb-4 flex items-center gap-3 border-b border-border-dim pb-3">
      <h1 className="font-mono text-sm font-medium text-text-primary">
        <Link to="/" className="hover:text-text-secondary">
          Glyphbox
        </Link>
      </h1>

      <Link
        to="/leaderboard"
        className="text-xs text-text-secondary hover:text-text-primary"
      >
        Leaderboard
      </Link>

      <div className="ml-auto flex items-center gap-3">
        {children}

        {authEnabled && !isLoading && (
          <>
            {user ? (
              <div className="flex items-center gap-2">
                {editing ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      value={nameInput}
                      onChange={(e) => setNameInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveName();
                        if (e.key === "Escape") setEditing(false);
                      }}
                      className="w-28 rounded border border-border-dim bg-bg-secondary px-1.5 py-0.5 text-xs text-text-primary"
                      autoFocus
                      disabled={saving}
                    />
                    <button
                      onClick={saveName}
                      disabled={saving}
                      className="text-xs text-accent-green hover:text-accent-green/80 disabled:opacity-50"
                    >
                      {saving ? "..." : "Save"}
                    </button>
                    <button
                      onClick={() => setEditing(false)}
                      className="text-xs text-text-muted hover:text-text-primary"
                    >
                      Cancel
                    </button>
                    {editError && (
                      <span className="text-[10px] text-accent-red">
                        {editError}
                      </span>
                    )}
                  </div>
                ) : (
                  <>
                    <Link
                      to={`/users/${user.id}`}
                      className="text-xs text-text-secondary hover:text-text-primary"
                    >
                      {user.display_name}
                    </Link>
                    <button
                      onClick={startEditing}
                      className="text-[10px] text-text-muted hover:text-text-secondary"
                      title="Edit username"
                    >
                      edit
                    </button>
                  </>
                )}
                <button
                  onClick={logout}
                  className="text-xs text-text-secondary hover:text-text-primary"
                >
                  Logout
                </button>
              </div>
            ) : (
              <button
                onClick={login}
                className="rounded border border-border-dim px-2 py-1 text-xs text-text-secondary hover:text-text-primary hover:border-text-secondary"
              >
                Login with OpenRouter
              </button>
            )}
          </>
        )}

        <button
          onClick={() => setShowAbout(true)}
          className="flex h-5 w-5 items-center justify-center rounded-full border border-border-dim text-xs text-text-muted hover:border-text-secondary hover:text-text-secondary"
          title="About Glyphbox"
        >
          ?
        </button>
      </div>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}
    </header>
  );
}
