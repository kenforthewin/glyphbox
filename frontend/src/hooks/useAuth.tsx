import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { UserRecord } from "../types/api";

interface AuthState {
  user: UserRecord | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  /** True when the server has auth configured (not 501) */
  authEnabled: boolean;
  login: () => void;
  logout: () => Promise<void>;
  setUser: (user: UserRecord) => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  authEnabled: false,
  login: () => {},
  logout: async () => {},
  setUser: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);

  useEffect(() => {
    api
      .getMe()
      .then((u) => {
        setUser(u);
        setAuthEnabled(true);
      })
      .catch((err: Error) => {
        if (err.message.startsWith("501")) {
          // Auth not configured on server
          setAuthEnabled(false);
        } else {
          // 401 or other -- auth is configured but user not logged in
          setAuthEnabled(true);
        }
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = () => {
    window.location.href = "/api/auth/login";
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // ignore
    }
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        authEnabled,
        login,
        logout,
        setUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
