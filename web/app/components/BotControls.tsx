"use client";

import { useState } from "react";
import { triggerAction } from "../lib/api";

export default function BotControls() {
  const [loading, setLoading] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function trigger(action: string, execute = false) {
    setLoading(action);
    setMsg("");
    try {
      await triggerAction(action, execute);
      setMsg(`${action} triggered`);
    } catch {
      setMsg(`Failed: ${action}`);
    } finally {
      setLoading(null);
      setTimeout(() => setMsg(""), 3000);
    }
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      {msg && <span className="text-green-500">{msg}</span>}
      <button
        onClick={() => trigger("monitor")}
        disabled={loading !== null}
        className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
      >
        {loading === "monitor" ? "…" : "POLL"}
      </button>
      <button
        onClick={() => trigger("quick-bets")}
        disabled={loading !== null}
        className="border border-cyan-700 px-2 py-1 rounded hover:bg-cyan-900/40 disabled:opacity-40 text-cyan-400"
      >
        {loading === "quick-bets" ? "…" : "QUICK BET"}
      </button>
      <button
        onClick={() => trigger("position-manager")}
        disabled={loading !== null}
        className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
      >
        {loading === "position-manager" ? "…" : "CHECK EXITS"}
      </button>
      <button
        onClick={() => trigger("refresh-whales")}
        disabled={loading !== null}
        className="border border-yellow-700 px-2 py-1 rounded hover:bg-yellow-900/40 disabled:opacity-40 text-yellow-400"
      >
        {loading === "refresh-whales" ? "…" : "REFRESH WHALES"}
      </button>
    </div>
  );
}
