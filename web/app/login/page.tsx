"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (res.ok) {
      router.push("/");
      router.refresh();
    } else {
      setError("Wrong password");
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-black text-green-400 font-mono flex items-center justify-center">
      <div className="border border-green-900 rounded p-8 w-80">
        <h1 className="text-xl font-bold text-green-300 mb-1">POLYMARKET BOT</h1>
        <p className="text-xs text-green-700 mb-6">Enter password to access dashboard</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            autoFocus
            autoComplete="username"
            className="w-full bg-black border border-green-800 rounded px-3 py-2 text-green-300 placeholder-green-900 focus:outline-none focus:border-green-600"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
            className="w-full bg-black border border-green-800 rounded px-3 py-2 text-green-300 placeholder-green-900 focus:outline-none focus:border-green-600"
          />
          {error && <p className="text-red-500 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={loading || !password || !username}
            className="w-full border border-green-700 py-2 rounded hover:bg-green-900/30 disabled:opacity-40 text-green-300"
          >
            {loading ? "…" : "ENTER"}
          </button>
        </form>
      </div>
    </main>
  );
}
