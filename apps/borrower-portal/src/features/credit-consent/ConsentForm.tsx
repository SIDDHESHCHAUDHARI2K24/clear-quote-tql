"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button, extractErrorMessage } from "@cq/ui";

import type { PortalConsent } from "./api";
import { acceptConsent, declineConsent } from "./api";

const GENERIC_ERROR = "Something went wrong. Try again.";
const REASON_MAX_LENGTH = 1000;

interface ConsentFormProps {
  consent: PortalConsent;
  onDecided: (consent: PortalConsent) => void;
  /** A 409 from accept or decline: the request changed under the borrower
   * (decided elsewhere, expired, or new text). The page re-fetches it. */
  onStale: () => void;
  /** A 401: the session ended; the page sends the borrower to login. */
  onUnauthorized: () => void;
  /** Shown above the form after a re-fetch left the request pending. */
  notice?: string | null;
}

/** The API error code, e.g. `NAME_MISMATCH`, from an error body. */
function errorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("error" in error)) return null;
  const inner = (error as { error?: unknown }).error;
  if (typeof inner !== "object" || inner === null || !("code" in inner)) return null;
  const code = (inner as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

function ConsentText({ consent, headingId }: { consent: PortalConsent; headingId: string }) {
  const paragraphs = consent.text.body.split("\n\n");
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-0 p-4"
    >
      <h2 id={headingId} className="text-base font-semibold text-navy-900">
        Credit check authorization
      </h2>
      {paragraphs.map((paragraph) => (
        <p key={paragraph} className="text-sm text-navy-900">
          {paragraph}
        </p>
      ))}
      <p className="text-xs text-neutral-500">Version {consent.text.version}</p>
    </section>
  );
}

interface FieldErrorProps {
  id: string;
  message: string | null;
}

function FieldError({ id, message }: FieldErrorProps) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-status-danger">
      {message}
    </p>
  );
}

interface DeclinePanelProps {
  consentId: string;
  disabled: boolean;
  onDecided: (consent: PortalConsent) => void;
  onStale: () => void;
  onUnauthorized: () => void;
  onError: (message: string) => void;
}

/** "Decline" reveals an optional reason and a confirm button, so a stray
 * tap never declines. */
function DeclinePanel({
  consentId,
  disabled,
  onDecided,
  onStale,
  onUnauthorized,
  onError,
}: DeclinePanelProps) {
  const reasonId = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  async function confirmDecline() {
    setPending(true);
    try {
      const { data, error, response } = await declineConsent(consentId, reason);
      if (data) {
        onDecided(data);
        return;
      }
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      if (response.status === 409) {
        onStale();
        return;
      }
      onError(extractErrorMessage(error, GENERIC_ERROR));
    } catch {
      onError(GENERIC_ERROR);
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" disabled={disabled} onClick={() => setOpen(true)}>
        Decline
      </Button>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 p-4">
      <label htmlFor={reasonId} className="text-sm font-medium text-navy-900">
        Reason for declining (optional)
      </label>
      <textarea
        id={reasonId}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        rows={3}
        maxLength={REASON_MAX_LENGTH}
        disabled={pending}
        className="rounded-md border border-neutral-200 bg-neutral-0 p-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
      />
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" isLoading={pending} onClick={() => void confirmDecline()}>
          Confirm decline
        </Button>
        <Button variant="ghost" disabled={pending} onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function validate(checked: boolean, name: string) {
  return {
    checkbox: checked ? null : "Check the box to authorize the credit check.",
    name: name.trim() ? null : "Type your full name to sign.",
  };
}

/**
 * The pending request (CQ-033): the versioned consent text, a required
 * "I authorize…" checkbox, a required typed full name, and Authorize /
 * Decline. Errors are linked to their inputs with `aria-describedby` and
 * `aria-invalid`; the first invalid input takes focus (AC7).
 */
export function ConsentForm({
  consent,
  onDecided,
  onStale,
  onUnauthorized,
  notice = null,
}: ConsentFormProps) {
  const baseId = useId();
  const ids = {
    heading: `${baseId}-heading`,
    checkbox: `${baseId}-authorize`,
    checkboxError: `${baseId}-authorize-error`,
    name: `${baseId}-name`,
    nameHint: `${baseId}-name-hint`,
    nameError: `${baseId}-name-error`,
  };
  const checkboxRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [checked, setChecked] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [errors, setErrors] = useState<{ checkbox: string | null; name: string | null }>({
    checkbox: null,
    name: null,
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Set on NAME_MISMATCH: the input is disabled while pending, so it takes
  // focus once the submit settles and re-enables it.
  const focusNameOnSettle = useRef(false);

  useEffect(() => {
    if (!pending && focusNameOnSettle.current) {
      focusNameOnSettle.current = false;
      nameRef.current?.focus();
    }
  }, [pending]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setServerError(null);
    const next = validate(checked, typedName);
    setErrors(next);
    if (next.checkbox) {
      checkboxRef.current?.focus();
      return;
    }
    if (next.name) {
      nameRef.current?.focus();
      return;
    }
    setPending(true);
    try {
      const { data, error, response } = await acceptConsent(consent.id, typedName.trim(), {
        version: consent.text.version,
        sha256: consent.text.sha256,
      });
      if (data) {
        onDecided(data);
        return;
      }
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      if (response.status === 409) {
        onStale();
        return;
      }
      if (errorCode(error) === "NAME_MISMATCH") {
        setErrors({ checkbox: null, name: extractErrorMessage(error, GENERIC_ERROR) });
        focusNameOnSettle.current = true;
        return;
      }
      setServerError(extractErrorMessage(error, GENERIC_ERROR));
    } catch {
      setServerError(GENERIC_ERROR);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-navy-900">Authorize a credit check</h1>
        <p className="text-navy-900">
          {consent.lo?.name ?? "Your loan officer"} is asking for your permission to run a hard
          credit check to finalize your pre-approval.
        </p>
      </header>

      {notice && (
        <p role="status" className="rounded-md bg-neutral-100 p-3 text-sm text-navy-900">
          {notice}
        </p>
      )}

      <ConsentText consent={consent} headingId={ids.heading} />

      <form
        noValidate
        onSubmit={(event) => void handleSubmit(event)}
        className="flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-start gap-2">
            <input
              ref={checkboxRef}
              id={ids.checkbox}
              type="checkbox"
              checked={checked}
              onChange={(event) => setChecked(event.target.checked)}
              required
              aria-required="true"
              aria-invalid={errors.checkbox ? true : undefined}
              aria-describedby={errors.checkbox ? ids.checkboxError : undefined}
              disabled={pending}
              className="mt-1 h-5 w-5 shrink-0"
            />
            <label htmlFor={ids.checkbox} className="text-sm text-navy-900">
              {consent.text.authorization}
            </label>
          </div>
          <FieldError id={ids.checkboxError} message={errors.checkbox} />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={ids.name} className="text-sm font-medium text-navy-900">
            Type your full name to sign
          </label>
          <input
            ref={nameRef}
            id={ids.name}
            type="text"
            autoComplete="name"
            value={typedName}
            onChange={(event) => setTypedName(event.target.value)}
            required
            aria-required="true"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={`${ids.nameHint}${errors.name ? ` ${ids.nameError}` : ""}`}
            disabled={pending}
            maxLength={200}
            className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
          />
          <p id={ids.nameHint} className="text-xs text-neutral-500">
            As it appears on your application: {consent.borrower_name}
          </p>
          <FieldError id={ids.nameError} message={errors.name} />
        </div>

        {serverError && (
          <p role="alert" className="text-sm text-status-danger">
            {serverError}
          </p>
        )}

        <div className="flex flex-wrap items-start gap-3">
          <Button type="submit" isLoading={pending}>
            Authorize
          </Button>
          <DeclinePanel
            consentId={consent.id}
            disabled={pending}
            onDecided={onDecided}
            onStale={onStale}
            onUnauthorized={onUnauthorized}
            onError={setServerError}
          />
        </div>
      </form>
    </div>
  );
}
