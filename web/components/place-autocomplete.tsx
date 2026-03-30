"use client";

import { useDeferredValue, useEffect, useRef, useState } from "react";

import {
  autocompletePlaces,
  getPlaceDetails,
  type PlaceSuggestion,
} from "@/lib/api/places";

type PlaceAutocompleteProps = {
  value: string;
  selectedPlace: PlaceSuggestion | null;
  onInputChange: (value: string) => void;
  onSelect: (place: PlaceSuggestion) => void;
  placeholder: string;
  autoFocus?: boolean;
};

function newSessionToken(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function PlaceAutocomplete({
  value,
  selectedPlace,
  onInputChange,
  onSelect,
  placeholder,
  autoFocus = false,
}: PlaceAutocompleteProps) {
  const deferredQuery = useDeferredValue(value.trim());
  const blurTimeoutRef = useRef<number | null>(null);

  const [sessionToken, setSessionToken] = useState<string>(() => newSessionToken());
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectingPlaceId, setSelectingPlaceId] = useState<string | null>(null);
  const [provider, setProvider] = useState<string>("google");
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);

  useEffect(() => {
    if (selectedPlace && value === selectedPlace.label) {
      setSuggestions([]);
      return;
    }
    if (deferredQuery.length < 2) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    setLoading(true);
    void autocompletePlaces(deferredQuery, sessionToken).then((payload) => {
      if (cancelled) {
        return;
      }
      setSuggestions(payload?.suggestions ?? []);
      setProvider(payload?.provider ?? "google");
      setLoading(false);
      setOpen(true);
    });

    return () => {
      cancelled = true;
    };
  }, [deferredQuery, selectedPlace, sessionToken, value]);

  useEffect(() => {
    return () => {
      if (blurTimeoutRef.current !== null) {
        window.clearTimeout(blurTimeoutRef.current);
      }
    };
  }, []);

  async function handleSelectSuggestion(suggestion: PlaceSuggestion) {
    setSelectingPlaceId(suggestion.place_id);
    const details = await getPlaceDetails(suggestion.place_id, sessionToken);
    const resolvedPlace = details ?? suggestion;
    onSelect(resolvedPlace);
    setSuggestions([]);
    setOpen(false);
    setSelectingPlaceId(null);
    setSessionToken(newSessionToken());
  }

  function handleBlur() {
    blurTimeoutRef.current = window.setTimeout(() => {
      setOpen(false);
    }, 120);
  }

  function handleFocus() {
    if (suggestions.length > 0) {
      setOpen(true);
    }
  }

  return (
    <div className="place-field">
      <input
        className="ob-input"
        type="text"
        value={value}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(event) => {
          onInputChange(event.target.value);
          setOpen(true);
        }}
        onFocus={handleFocus}
        onBlur={handleBlur}
        autoComplete="off"
        spellCheck={false}
      />
      {open && (loading || suggestions.length > 0 || deferredQuery.length >= 2) ? (
        <div className="place-dropdown">
          {loading ? (
            <div className="place-dropdown-status">Searching places…</div>
          ) : suggestions.length > 0 ? (
            <>
              <div className="place-dropdown-list">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion.place_id}
                    type="button"
                    className={`place-option${selectedPlace?.place_id === suggestion.place_id ? " place-option-selected" : ""}`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      void handleSelectSuggestion(suggestion);
                    }}
                    disabled={selectingPlaceId !== null}
                  >
                    <span className="place-option-primary">
                      {selectingPlaceId === suggestion.place_id ? "Selecting…" : suggestion.name}
                    </span>
                    {suggestion.secondary_text ? (
                      <span className="place-option-secondary">{suggestion.secondary_text}</span>
                    ) : null}
                  </button>
                ))}
              </div>
              <div className="place-dropdown-footer">
                {provider === "google" ? "Powered by Google" : "Suggested locations"}
              </div>
            </>
          ) : (
            <div className="place-dropdown-status">
              Search for a real location or address and choose one result.
            </div>
          )}
        </div>
      ) : null}
      {selectedPlace ? (
        <div className="place-selected-meta">
          <span className="place-selected-badge">
            {selectedPlace.provider === "google" ? "Verified place" : "Saved suggestion"}
          </span>
          {selectedPlace.formatted_address ? (
            <span className="place-selected-address">{selectedPlace.formatted_address}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
