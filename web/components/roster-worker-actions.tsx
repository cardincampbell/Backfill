"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { deactivateWorker, reactivateWorker, transferWorker } from "@/lib/shifts-api";

type LocationOption = { id: number; name: string };

type RosterWorkerActionsProps = {
  workerId: number;
  isActive: boolean;
  locationId: number;
  locations: LocationOption[];
};

export function RosterWorkerActions({ workerId, isActive, locationId, locations }: RosterWorkerActionsProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [targetLocationId, setTargetLocationId] = useState<number | "">("");

  const otherLocations = locations.filter((l) => l.id !== locationId);

  async function handleToggle() {
    setBusy(true);
    try {
      const result = isActive
        ? await deactivateWorker(workerId)
        : await reactivateWorker(workerId);
      if (result) router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleTransfer() {
    if (!targetLocationId) return;
    setBusy(true);
    try {
      const result = await transferWorker(workerId, Number(targetLocationId));
      if (result) {
        router.refresh();
        setShowTransfer(false);
        setTargetLocationId("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6 }}>
        <button
          className="button-secondary button-small"
          disabled={busy}
          onClick={handleToggle}
        >
          {busy && !showTransfer
            ? (isActive ? "Deactivating\u2026" : "Reactivating\u2026")
            : (isActive ? "Deactivate" : "Reactivate")}
        </button>
        {otherLocations.length > 0 && (
          <button
            className="button-secondary button-small"
            disabled={busy}
            onClick={() => setShowTransfer(!showTransfer)}
          >
            Transfer
          </button>
        )}
      </div>
      {showTransfer && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8 }}>
          <select
            value={targetLocationId}
            onChange={(e) => setTargetLocationId(e.target.value ? Number(e.target.value) : "")}
            style={{
              padding: "6px 10px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--line-strong)",
              fontSize: "0.78rem",
              background: "var(--panel)",
              color: "var(--text)",
              font: "inherit",
            }}
          >
            <option value="">Select location</option>
            {otherLocations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
          <button
            className="button button-small"
            disabled={busy || !targetLocationId}
            onClick={handleTransfer}
          >
            {busy ? "Transferring\u2026" : "Go"}
          </button>
          <button
            className="button-secondary button-small"
            onClick={() => { setShowTransfer(false); setTargetLocationId(""); }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
