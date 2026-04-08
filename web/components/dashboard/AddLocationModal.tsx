"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Building2, X } from "lucide-react";

import {
  useAppWorkspaceRefresh,
} from "@/components/app-workspace";
import { PlaceAutocomplete } from "@/components/place-autocomplete";
import type { WorkspaceBusiness } from "@/lib/api/workspace";
import { createLocationFromPlace } from "@/lib/api/workspace";
import type { PlaceSuggestion } from "@/lib/api/places";

export type CreatedLocationResult = {
  id: string;
  business_id: string;
  name: string;
  display_name: string;
  slug: string;
};

export default function AddLocationModal({
  isDark = false,
  open,
  business,
  onClose,
  onCreated,
}: {
  isDark?: boolean;
  open: boolean;
  business: WorkspaceBusiness | null;
  onClose: () => void;
  onCreated?: (
    createdLocation: CreatedLocationResult,
    business: WorkspaceBusiness,
  ) => void | Promise<void>;
}) {
  const refreshWorkspace = useAppWorkspaceRefresh();
  const [locationQuery, setLocationQuery] = useState("");
  const [selectedPlace, setSelectedPlace] = useState<PlaceSuggestion | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setLocationQuery("");
      setSelectedPlace(null);
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  const panelClass = isDark
    ? "bg-[#0F2E4C] border border-white/[0.08]"
    : "bg-white border border-[#E5E7EB]";
  const borderClass = isDark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const textPrimaryClass = isDark ? "text-white" : "text-[#0A2540]";
  const footerClass = isDark ? "bg-white/[0.03]" : "bg-[#FAFBFC]";
  const closeButtonClass = isDark
    ? "p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
    : "p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors";
  const cancelButtonClass = isDark
    ? "px-4 py-2.5 rounded-lg text-[13px] text-[#C1CED8] border border-white/[0.08] hover:bg-white/[0.04] transition-all"
    : "px-4 py-2.5 rounded-lg text-[13px] text-[#5E6D7A] border border-[#E5E7EB] hover:bg-[#F7F8FA] transition-all";
  const disabledButtonClass = isDark
    ? "bg-white/[0.08] text-[#8898AA] cursor-not-allowed"
    : "bg-[#E5E7EB] text-[#8898AA] cursor-not-allowed";
  const errorClass = isDark
    ? "text-[#FCA5A5] bg-[#7F1D1D]/20 border border-[#F87171]/20"
    : "text-[#B42318] bg-[#FEF3F2] border border-[#FECACA]";

  const businessLabel = useMemo(() => {
    if (!business) {
      return "your business";
    }
    return business.business_display_name ?? business.business_name;
  }, [business]);

  const timezone = business?.locations[0]?.timezone ?? "America/Los_Angeles";
  const canSubmit = Boolean(business && selectedPlace && !submitting);

  async function handleSubmit() {
    if (!business) {
      setError("No business is available for this location right now.");
      return;
    }
    if (!selectedPlace) {
      setError("Search and select a real place first.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const createdLocation = await createLocationFromPlace(
        business.business_id,
        selectedPlace,
        { timezone },
      );
      await refreshWorkspace();
      if (onCreated) {
        await onCreated(createdLocation, business);
      }
      onClose();
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Could not add this location.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm"
          exit={{ opacity: 0 }}
          initial={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className={`mx-4 w-full max-w-lg overflow-hidden rounded-2xl shadow-2xl sm:mx-0 ${panelClass}`}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            onClick={(event) => event.stopPropagation()}
            transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
          >
            <div
              className={`flex items-center justify-between border-b px-4 py-5 sm:px-6 ${borderClass}`}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#635BFF]/10">
                  <Building2 size={18} className="text-[#635BFF]" />
                </div>
                <div>
                  <h2
                    className={`text-[16px] ${textPrimaryClass}`}
                    style={{ fontWeight: 600 }}
                  >
                    Add Location
                  </h2>
                  <p
                    className="text-[12px] text-[#8898AA]"
                    style={{ fontWeight: 420 }}
                  >
                    Add a new location to {businessLabel}.
                  </p>
                </div>
              </div>
              <button
                className={closeButtonClass}
                onClick={onClose}
                type="button"
              >
                <X size={18} className="text-[#8898AA]" />
              </button>
            </div>

            <div className="space-y-4 px-4 py-5 sm:px-6">
              <div>
                <label
                  className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                  style={{ fontWeight: 500 }}
                >
                  Location Search
                </label>
                <PlaceAutocomplete
                  appearance={isDark ? "dark" : "light"}
                  autoFocus
                  compact
                  onInputChange={(value) => {
                    setLocationQuery(value);
                    setError(null);
                    if (selectedPlace && value !== selectedPlace.label) {
                      setSelectedPlace(null);
                    }
                  }}
                  onSelect={(place) => {
                    setSelectedPlace(place);
                    setLocationQuery(place.label);
                    setError(null);
                  }}
                  placeholder="Search for a location or paste an address"
                  selectedPlace={selectedPlace}
                  showFooter={false}
                  value={locationQuery}
                />
              </div>

              {error ? (
                <div className={`rounded-xl px-3.5 py-3 text-[12px] ${errorClass}`}>
                  {error}
                </div>
              ) : null}
            </div>

            <div
              className={`flex items-center justify-end gap-3 border-t px-4 py-4 sm:px-6 ${borderClass} ${footerClass}`}
            >
              <button
                className={cancelButtonClass}
                onClick={onClose}
                style={{ fontWeight: 480 }}
                type="button"
              >
                Cancel
              </button>
              <button
                className={`rounded-lg px-5 py-2.5 text-[13px] transition-all duration-300 ${
                  canSubmit
                    ? "text-white hover:shadow-[0_0_20px_rgba(99,91,255,0.25)]"
                    : disabledButtonClass
                }`}
                onClick={() => {
                  void handleSubmit();
                }}
                style={{
                  fontWeight: 540,
                  background: canSubmit
                    ? "linear-gradient(135deg, #635BFF, #8B5CF6)"
                    : undefined,
                }}
                type="button"
              >
                {submitting ? "Adding…" : "Add Location"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
