"use client";

import { useState, useEffect } from "react";

const RAILWAY = "https://polymarket-bot-production-ae2d.up.railway.app";

export default function LiveStatus() {
  const [status, setStatus] = useState<{ last_poll: string | null; execution_mode: string; whale_count: number } | null>(null);

  useEffect(() => {
    const fetch_status = () =>
      fetch(`${RAILWAY}/api/actions/status`)
        .then(r => r.json())
        .then(setStatus)
        .catch(() => {});

    fetch_status();
    const interval = setInterval(fetch_status, 15000); // refresh every 15s
    return () => clearInterval(interval);
  }, []);

  if (!status) return <span className="text-green-800">connecting…</span>;

  const lastPoll = status.last_poll
    ? new Date(status.last_poll).toLocaleTimeString(undefined, { hour12: false })
    : "never";

  return (
    <span>
      {status.execution_mode === "execute" ? "● LIVE" : "● DRY-RUN"} &nbsp;·&nbsp;
      {status.whale_count} whales tracked &nbsp;·&nbsp;
      last poll: {lastPoll}
    </span>
  );
}
