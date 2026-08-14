"use client";

import { Check, MapPin } from "lucide-react";
import {
  type FocusEvent,
  type KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import styles from "./page.module.css";

export type PropertyAddressValue = {
  street_address: string;
  city: string;
  state: string;
  postal_code: string;
};

type PropertyAddressErrors = Partial<Record<keyof PropertyAddressValue, string>>;

type AddressSuggestion = PropertyAddressValue & {
  provider_id: string | null;
  label: string;
};

type AddressSuggestionResponse = {
  available: boolean;
  suggestions: AddressSuggestion[];
};

type PropertyAddressFieldProps = {
  apiBaseUrl: string;
  value: PropertyAddressValue;
  errors: PropertyAddressErrors;
  onChange: (value: PropertyAddressValue) => void;
  onStart: () => void;
};

const suggestionDelayMs = 250;
const suggestionTimeoutMs = 4_000;

export function PropertyAddressField({
  apiBaseUrl,
  value,
  errors,
  onChange,
  onStart,
}: PropertyAddressFieldProps) {
  const listboxId = useId();
  const addressControlRef = useRef<HTMLDivElement>(null);
  const streetInputRef = useRef<HTMLInputElement>(null);
  const cityInputRef = useRef<HTMLInputElement>(null);
  const stateInputRef = useRef<HTMLInputElement>(null);
  const postalCodeInputRef = useRef<HTMLInputElement>(null);
  const lastEmittedValueKey = useRef(addressValueKey(value));
  const [query, setQuery] = useState(() => displayAddress(value));
  const [selectedLabel, setSelectedLabel] = useState<string | null>(() =>
    isCompleteAddress(value) ? displayAddress(value) : null,
  );
  const [manualMode, setManualMode] = useState(false);
  const [isAddressEngaged, setIsAddressEngaged] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [lookupStatus, setLookupStatus] = useState<
    "idle" | "loading" | "unavailable" | "no_results"
  >("idle");
  const hasManualAddressErrors = Boolean(
    errors.city || errors.state || errors.postal_code,
  );
  const showManualMode = manualMode || hasManualAddressErrors;
  const hasIncompleteAddress = hasMeaningfulAddressData(value) && !isCompleteAddress(value);
  const showAddressDetails =
    showManualMode || hasIncompleteAddress || (isAddressEngaged && !selectedLabel);

  useEffect(() => {
    const nextValueKey = addressValueKey(value);
    if (nextValueKey === lastEmittedValueKey.current) return;
    lastEmittedValueKey.current = nextValueKey;
    const nextDisplay = displayAddress(value);
    setQuery(nextDisplay);
    setSelectedLabel(isCompleteAddress(value) ? nextDisplay : null);
    setManualMode(false);
    setIsAddressEngaged(false);
    setSuggestions([]);
    setActiveIndex(-1);
    setLookupStatus("idle");
  }, [value]);

  useEffect(() => {
    const cleanQuery = query.trim();
    if (
      showManualMode ||
      selectedLabel ||
      !isFocused ||
      cleanQuery.length < 3
    ) {
      return;
    }

    const controller = new AbortController();
    let disposed = false;
    const delay = window.setTimeout(async () => {
      setLookupStatus("loading");
      const timeout = window.setTimeout(() => controller.abort(), suggestionTimeoutMs);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/public/address-suggestions?q=${encodeURIComponent(cleanQuery)}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("Address suggestions are unavailable.");
        const payload = (await response.json()) as AddressSuggestionResponse;
        if (disposed) return;
        const nextSuggestions = Array.isArray(payload.suggestions)
          ? payload.suggestions.filter(isUsableSuggestion).slice(0, 6)
          : [];
        setSuggestions(nextSuggestions);
        setActiveIndex(nextSuggestions.length ? 0 : -1);
        setLookupStatus(
          !payload.available
            ? "unavailable"
            : nextSuggestions.length
              ? "idle"
              : "no_results",
        );
      } catch {
        if (!disposed) {
          setLookupStatus("unavailable");
          setSuggestions([]);
          setActiveIndex(-1);
        }
      } finally {
        window.clearTimeout(timeout);
      }
    }, suggestionDelayMs);

    return () => {
      disposed = true;
      window.clearTimeout(delay);
      controller.abort();
    };
  }, [apiBaseUrl, isFocused, query, selectedLabel, showManualMode]);

  function updateQuery(nextQuery: string) {
    onStart();
    if (showManualMode) setManualMode(true);
    setQuery(nextQuery);
    setSelectedLabel(null);
    setSuggestions([]);
    setActiveIndex(-1);
    setLookupStatus("idle");
    emitChange(
      showManualMode
        ? { ...value, street_address: nextQuery }
        : {
            street_address: nextQuery,
            city: "",
            state: "GA",
            postal_code: "",
          },
    );
  }

  function chooseSuggestion(suggestion: AddressSuggestion) {
    onStart();
    const nextValue = {
      street_address: suggestion.street_address,
      city: suggestion.city,
      state: suggestion.state.toUpperCase(),
      postal_code: suggestion.postal_code,
    };
    acceptCompleteAddress(nextValue, suggestion.label);
  }

  function showManualEntry() {
    onStart();
    setManualMode(true);
    setIsAddressEngaged(true);
    setSelectedLabel(null);
    setSuggestions([]);
    setActiveIndex(-1);
    setLookupStatus("idle");
    setQuery(value.street_address || query.split(",", 1)[0].trim());
    window.requestAnimationFrame(() => cityInputRef.current?.focus());
  }

  function emitChange(nextValue: PropertyAddressValue) {
    lastEmittedValueKey.current = addressValueKey(nextValue);
    onChange(nextValue);
  }

  function updateManualAddress() {
    onStart();
    const nextValue = readRenderedAddress();
    if (isCompleteAddress(nextValue) && !manualMode) {
      acceptCompleteAddress(nextValue, displayAddress(nextValue));
      return;
    }
    setManualMode(true);
    emitChange(nextValue);
  }

  function readRenderedAddress(streetAddress?: string): PropertyAddressValue {
    return {
      street_address: streetAddress ?? streetInputRef.current?.value ?? value.street_address,
      city: cityInputRef.current?.value ?? value.city,
      state: (stateInputRef.current?.value ?? value.state).toUpperCase(),
      postal_code: postalCodeInputRef.current?.value ?? value.postal_code,
    };
  }

  function handleStreetInput(nextQuery: string) {
    if (selectedLabel) {
      updateQuery(nextQuery);
      return;
    }
    const renderedAddress = readRenderedAddress(nextQuery);
    if (isCompleteAddress(renderedAddress)) {
      onStart();
      acceptCompleteAddress(renderedAddress, displayAddress(renderedAddress));
      return;
    }
    updateQuery(nextQuery);
  }

  function acceptCompleteAddress(nextValue: PropertyAddressValue, label: string) {
    const shouldRestoreStreetFocus = [
      cityInputRef.current,
      stateInputRef.current,
      postalCodeInputRef.current,
    ].includes(document.activeElement as HTMLInputElement | null);
    emitChange(nextValue);
    setQuery(label);
    setSelectedLabel(label);
    setSuggestions([]);
    setActiveIndex(-1);
    setLookupStatus("idle");
    setManualMode(false);
    setIsAddressEngaged(false);
    if (shouldRestoreStreetFocus) {
      window.requestAnimationFrame(() => streetInputRef.current?.focus({ preventScroll: true }));
    }
  }

  function handleAddressControlBlur(event: FocusEvent<HTMLDivElement>) {
    if (
      event.relatedTarget instanceof Node &&
      addressControlRef.current?.contains(event.relatedTarget)
    ) {
      return;
    }
    setIsAddressEngaged(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!suggestions.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) =>
        current <= 0 ? suggestions.length - 1 : current - 1,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseSuggestion(suggestions[activeIndex >= 0 ? activeIndex : 0]);
    } else if (event.key === "Escape") {
      setSuggestions([]);
      setActiveIndex(-1);
    }
  }

  const inputDescriptionIds = [
    "property_address-guidance",
    errors.street_address ? "property_address-error" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={styles.addressControl}
      ref={addressControlRef}
      onBlurCapture={handleAddressControlBlur}
      onFocusCapture={() => setIsAddressEngaged(true)}
    >
      <label className={styles.field} htmlFor="property_address">
        <span>
          <strong>Property address</strong>
          <span className={styles.visuallyHidden}> (required)</span>
        </span>
        <div className={styles.addressSearch}>
          <MapPin size={18} aria-hidden="true" />
          <input
            ref={streetInputRef}
            id="property_address"
            name="property_address"
            autoCapitalize="words"
            autoComplete="section-property address-line1"
            enterKeyHint="next"
            required
            role="combobox"
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-expanded={Boolean(suggestions.length)}
            aria-activedescendant={
              activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined
            }
            aria-invalid={Boolean(errors.street_address)}
            aria-describedby={inputDescriptionIds}
            placeholder="Start typing the property address"
            value={query}
            onBlur={() => {
              setIsFocused(false);
              window.setTimeout(() => {
                setSuggestions([]);
                setActiveIndex(-1);
              }, 120);
            }}
            onChange={(event) => handleStreetInput(event.target.value)}
            onFocus={() => {
              onStart();
              setIsFocused(true);
            }}
            onPointerDownCapture={() => setIsAddressEngaged(true)}
            onKeyDown={handleKeyDown}
          />
        </div>
        <small className={styles.addressGuidance} id="property_address-guidance">
          Choose a matching property, or enter the address manually.
        </small>
        {errors.street_address ? (
          <p className={styles.fieldError} id="property_address-error">
            {errors.street_address}
          </p>
        ) : null}
      </label>

      {suggestions.length ? (
        <ul className={styles.addressSuggestions} id={listboxId} role="listbox">
          {suggestions.map((suggestion, index) => (
            <li
              key={`${suggestion.provider_id ?? suggestion.label}-${index}`}
            >
              <button
                aria-selected={activeIndex === index}
                id={`${listboxId}-option-${index}`}
                role="option"
                tabIndex={-1}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => chooseSuggestion(suggestion)}
              >
                <MapPin size={16} aria-hidden="true" />
                <span>{suggestion.label}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className={styles.addressStatus} aria-live="polite">
        {lookupStatus === "loading" ? <span>Finding matching properties...</span> : null}
        {lookupStatus === "no_results" ? (
          <span>No exact match yet. You can enter the address manually.</span>
        ) : null}
        {lookupStatus === "unavailable" ? (
          <span>Suggestions are temporarily unavailable. Manual entry still works.</span>
        ) : null}
        {selectedLabel ? (
          <span className={styles.addressConfirmed}>
            <Check size={15} aria-hidden="true" /> Address selected
          </span>
        ) : null}
        {!showManualMode && !showAddressDetails ? (
          <button type="button" onClick={showManualEntry}>
            {selectedLabel ? "Edit address" : "Enter address manually"}
          </button>
        ) : null}
      </div>

      <div
        className={`${styles.manualAddress} ${
          showAddressDetails ? "" : styles.manualAddressCollapsed
        }`}
        aria-hidden={!showAddressDetails}
      >
        <p>Enter the remaining address details.</p>
        <div className={styles.manualAddressGrid}>
          <label className={`${styles.field} ${styles.manualCity}`} htmlFor="property_city">
            <span><strong>City</strong><span className={styles.visuallyHidden}> (required)</span></span>
            <input
              ref={cityInputRef}
              id="property_city"
              name="property_city"
              autoCapitalize="words"
              autoComplete="section-property address-level2"
              required
              tabIndex={showAddressDetails ? undefined : -1}
              value={value.city}
              onChange={updateManualAddress}
              aria-invalid={Boolean(errors.city)}
              aria-describedby={errors.city ? "property_city-error" : undefined}
              placeholder="Atlanta"
            />
            {errors.city ? <p className={styles.fieldError} id="property_city-error">{errors.city}</p> : null}
          </label>
          <label className={styles.field} htmlFor="property_state">
            <span><strong>State</strong><span className={styles.visuallyHidden}> (required)</span></span>
            <input
              ref={stateInputRef}
              id="property_state"
              name="property_state"
              autoCapitalize="characters"
              autoComplete="section-property address-level1"
              maxLength={2}
              required
              tabIndex={showAddressDetails ? undefined : -1}
              value={value.state}
              onChange={updateManualAddress}
              aria-invalid={Boolean(errors.state)}
              aria-describedby={errors.state ? "property_state-error" : undefined}
              placeholder="GA"
            />
            {errors.state ? <p className={styles.fieldError} id="property_state-error">{errors.state}</p> : null}
          </label>
          <label className={styles.field} htmlFor="property_postal_code">
            <span><strong>ZIP code</strong><span className={styles.visuallyHidden}> (required)</span></span>
            <input
              ref={postalCodeInputRef}
              id="property_postal_code"
              name="property_postal_code"
              autoComplete="section-property postal-code"
              inputMode="numeric"
              required
              tabIndex={showAddressDetails ? undefined : -1}
              value={value.postal_code}
              onChange={updateManualAddress}
              aria-invalid={Boolean(errors.postal_code)}
              aria-describedby={
                errors.postal_code ? "property_postal_code-error" : undefined
              }
              placeholder="30303"
            />
            {errors.postal_code ? (
              <p className={styles.fieldError} id="property_postal_code-error">
                {errors.postal_code}
              </p>
            ) : null}
          </label>
        </div>
      </div>
    </div>
  );
}

function isCompleteAddress(value: PropertyAddressValue) {
  return Boolean(
    value.street_address.trim() &&
      value.city.trim() &&
      /^[A-Za-z]{2}$/.test(value.state.trim()) &&
      /^\d{5}(?:-\d{4})?$/.test(value.postal_code.trim()),
  );
}

function hasMeaningfulAddressData(value: PropertyAddressValue) {
  return Boolean(
    value.street_address.trim() ||
      value.city.trim() ||
      value.postal_code.trim() ||
      (value.state.trim() && value.state.trim().toUpperCase() !== "GA"),
  );
}

function displayAddress(value: PropertyAddressValue) {
  if (!isCompleteAddress(value)) return value.street_address;
  return `${value.street_address}, ${value.city}, ${value.state.toUpperCase()} ${value.postal_code}`;
}

function addressValueKey(value: PropertyAddressValue) {
  return [value.street_address, value.city, value.state, value.postal_code].join("\u0000");
}

function isUsableSuggestion(value: AddressSuggestion) {
  return Boolean(
    value &&
      typeof value.label === "string" &&
      value.label.trim() &&
      typeof value.street_address === "string" &&
      value.street_address.trim() &&
      typeof value.city === "string" &&
      value.city.trim() &&
      typeof value.state === "string" &&
      /^[A-Za-z]{2}$/.test(value.state.trim()) &&
      typeof value.postal_code === "string" &&
      /^\d{5}(?:-\d{4})?$/.test(value.postal_code.trim()),
  );
}
