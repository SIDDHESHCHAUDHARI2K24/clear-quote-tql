"use client";

import { useEffect, useState } from "react";

import { api } from "../lib/api-client";

type ApiState = "loading" | "reachable" | "unreachable";

export default function Home() {
  const [state, setState] = useState<ApiState>("loading");

  useEffect(() => {
    let cancelled = false;

    // A network failure (backend not running, DNS/CORS failure, etc.)
    // rejects this promise; openapi-fetch does not catch that itself, so we
    // must — the page must never throw, whether or not the API is up.
    api
      .GET("/health")
      .then(() => {
        if (!cancelled) setState("reachable");
      })
      .catch(() => {
        if (!cancelled) setState("unreachable");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold text-navy-900">Clear Quote — LO Console</h1>
      <p
        role="status"
        className={state === "unreachable" ? "text-status-danger" : "text-status-success"}
      >
        {state === "loading" && "Checking API…"}
        {state === "reachable" && "API reachable"}
        {state === "unreachable" && "API unreachable"}
      </p>
    </main>
  );
}
