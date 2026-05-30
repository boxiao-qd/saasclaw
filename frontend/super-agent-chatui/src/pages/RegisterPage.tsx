import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authPost } from "@/services/api-client";
import { useAuthStore } from "@/store/auth-store";

interface TokenResponse {
  access_token: string;
  username: string;
}

export function RegisterPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      const data = await authPost<TokenResponse>("/register", { username, password });
      login(data.access_token, data.username);
      navigate("/chat/new", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="w-full max-w-sm px-6">
        <h1 className="text-2xl font-mono font-bold text-[var(--color-text-primary)] mb-8 text-center tracking-widest uppercase">
          注册账号
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">
              用户名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              placeholder="3-32 字符，字母数字下划线"
              className="w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text-primary)] font-mono focus:outline-none focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-tertiary)]"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="至少 6 位"
              className="w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text-primary)] font-mono focus:outline-none focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-tertiary)]"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">
              确认密码
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className="w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text-primary)] font-mono focus:outline-none focus:border-[var(--color-primary)] transition-colors"
            />
          </div>
          {error && (
            <p className="text-xs text-[var(--color-error)] font-mono">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-[var(--color-primary)] text-black font-mono font-bold text-sm rounded hover:opacity-90 disabled:opacity-50 transition-opacity uppercase tracking-wider"
          >
            {loading ? "注册中..." : "创建账号"}
          </button>
        </form>
        <p className="mt-6 text-center text-xs text-[var(--color-text-tertiary)] font-mono">
          已有账号？{" "}
          <Link to="/login" className="text-[var(--color-primary)] hover:underline">
            登录
          </Link>
        </p>
      </div>
    </div>
  );
}
