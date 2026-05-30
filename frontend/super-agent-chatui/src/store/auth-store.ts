import { create } from "zustand";
import { setAccessToken } from "@/services/api-client";

const TOKEN_KEY = "bx_access_token";
const USERNAME_KEY = "bx_username";

interface AuthState {
  token: string;
  username: string;
  isAuthenticated: boolean;
  login: (token: string, username: string) => void;
  logout: () => void;
}

function loadFromStorage(): { token: string; username: string } {
  try {
    const token = localStorage.getItem(TOKEN_KEY) || "";
    const username = localStorage.getItem(USERNAME_KEY) || "";
    return { token, username };
  } catch {
    return { token: "", username: "" };
  }
}

const { token: storedToken, username: storedUsername } = loadFromStorage();
if (storedToken) setAccessToken(storedToken);

export const useAuthStore = create<AuthState>((set) => ({
  token: storedToken,
  username: storedUsername,
  isAuthenticated: !!storedToken,

  login(token: string, username: string) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
    setAccessToken(token);
    set({ token, username, isAuthenticated: true });
  },

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    setAccessToken("");
    set({ token: "", username: "", isAuthenticated: false });
  },
}));
