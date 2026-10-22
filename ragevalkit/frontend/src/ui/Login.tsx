import { useState, type FormEvent } from "react";
import { useAuth } from "../AuthContext";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[420px] flex-col justify-center px-6 pb-16">
      <h1 className="font-serif text-[40px] font-medium leading-none tracking-tight">
        RAG <span className="hl">Evaluator</span>
      </h1>
      <p className="mt-3 text-sm text-muted">Sign in to see evaluation runs and start new ones.</p>

      <form onSubmit={submit} className="card mt-8 p-6">
        <label className="label block" htmlFor="u">Username</label>
        <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus
          className="mt-1.5 w-full rounded border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25" />
        <label className="label mt-4 block" htmlFor="p">Password</label>
        <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
          className="mt-1.5 w-full rounded border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25" />
        {error && <div className="mt-4 border border-bad p-3 text-xs text-bad">{error}</div>}
        <button type="submit" disabled={busy || !username || !password}
          className="mt-6 w-full rounded bg-brand px-5 py-2.5 text-sm font-semibold text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
