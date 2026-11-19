import { useEffect, useState } from "react";

import { useAuth } from "../api/auth";
import * as client from "../api/client";
import { Button } from "../design/ui";

const WARN_SECONDS = 120;

/** Warns two minutes before the server ends an idle session. Any request restarts the server's clock. */
export function IdleWarning() {
  const { me, refresh } = useAuth();
  const limit = me?.session_idle_seconds ?? 0;
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (!limit) return;
    const tick = () => {
      const remaining = limit - Math.floor((Date.now() - client.lastApiAt) / 1000);
      setLeft(remaining <= WARN_SECONDS && remaining > 0 ? remaining : null);
    };
    tick();
    const t = window.setInterval(tick, 5000);
    return () => window.clearInterval(t);
  }, [limit]);
  if (left === null) return null;
  return (
    <div role="alertdialog" aria-label="Session about to end" className="card fixed bottom-20 right-4 z-40 flex max-w-sm flex-col gap-3 p-4 md:bottom-6">
      <p className="m-0">You will be signed out in about {Math.max(1, Math.ceil(left / 60))} minute{left > 60 ? "s" : ""} because of inactivity.</p>
      <div className="flex justify-end"><Button variant="primary" onClick={() => void refresh()}>Stay signed in</Button></div>
    </div>
  );
}
