"use client";

import { useId, useState } from "react";
import type { FormEvent } from "react";

import { Button, Select, TextField, useAsyncSubmit } from "@cq/ui";

import { useBorrowerSession } from "../shell";
import type { PreferredContact, SupportRequestResponse, SupportTopic } from "./api";
import { SUPPORT_TOPICS, submitSupportRequest } from "./api";

const MESSAGE_MIN_LENGTH = 10;
const MESSAGE_MAX_LENGTH = 2000;
const GENERIC_ERROR = "Something went wrong. Try again.";

interface FormValues {
  topic: SupportTopic;
  message: string;
  preferredContact: PreferredContact;
  phone: string;
}

interface SubmitResult {
  reference: string;
  lo: SupportRequestResponse["lo"];
  preferredContact: PreferredContact;
}

/** The post-submit state: reference + the assigned LO's direct contact as
 * an alternative (spec.md). Split out so `SupportForm` doesn't also carry
 * this branch's JSX (react-doctor `no-high-complexity-react-function`). */
function SupportConfirmation({ result }: { result: SubmitResult }) {
  const contactWord = result.preferredContact === "phone" ? "phone" : "email";
  return (
    <div className="flex flex-col gap-3" role="status">
      <h1 className="text-2xl font-semibold text-navy-900">Message sent</h1>
      <p className="text-navy-900">
        Thanks — we&rsquo;ll be in touch by {contactWord}. Your reference is{" "}
        <strong>{result.reference}</strong>.
      </p>
      <p className="text-sm text-neutral-600">
        You can also reach {result.lo.name} directly at {result.lo.email}
        {result.lo.phone ? ` or ${result.lo.phone}` : ""}.
      </p>
    </div>
  );
}

interface MessageFieldProps {
  id: string;
  counterId: string;
  errorId: string;
  value: string;
  error: string | null;
  disabled: boolean;
  onChange: (value: string) => void;
}

/** Message textarea + character counter + linked error (split out of
 * `SupportForm` for react-doctor's `no-high-complexity-react-function`). */
function MessageField({
  id,
  counterId,
  errorId,
  value,
  error,
  disabled,
  onChange,
}: MessageFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-navy-900">
        Message
      </label>
      <textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        rows={5}
        maxLength={MESSAGE_MAX_LENGTH + 200}
        aria-invalid={error ? true : undefined}
        aria-describedby={`${counterId}${error ? ` ${errorId}` : ""}`}
        className="rounded-md border border-neutral-200 bg-neutral-0 p-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
      />
      <p id={counterId} className="text-xs text-neutral-500">
        {value.length}/{MESSAGE_MAX_LENGTH}
      </p>
      {error && (
        <p id={errorId} className="text-xs text-status-danger">
          {error}
        </p>
      )}
    </div>
  );
}

interface ContactFieldsProps {
  legendId: string;
  preferredContact: PreferredContact;
  onPreferredContactChange: (value: PreferredContact) => void;
  phoneId: string;
  phoneErrorId: string;
  phone: string;
  phoneError: string | null;
  disabled: boolean;
  onPhoneChange: (value: string) => void;
}

/** Preferred-contact radio group + the phone field it gates (split out of
 * `SupportForm` for react-doctor's `no-high-complexity-react-function`). */
function ContactFields({
  legendId,
  preferredContact,
  onPreferredContactChange,
  phoneId,
  phoneErrorId,
  phone,
  phoneError,
  disabled,
  onPhoneChange,
}: ContactFieldsProps) {
  return (
    <>
      <fieldset className="flex flex-col gap-2">
        <legend id={legendId} className="text-sm font-medium text-navy-900">
          Preferred contact
        </legend>
        <div className="flex gap-4" role="radiogroup" aria-labelledby={legendId}>
          <label className="flex items-center gap-2 text-sm text-navy-900">
            <input
              type="radio"
              name="preferred-contact"
              value="email"
              checked={preferredContact === "email"}
              onChange={() => onPreferredContactChange("email")}
              disabled={disabled}
            />
            Email
          </label>
          <label className="flex items-center gap-2 text-sm text-navy-900">
            <input
              type="radio"
              name="preferred-contact"
              value="phone"
              checked={preferredContact === "phone"}
              onChange={() => onPreferredContactChange("phone")}
              disabled={disabled}
            />
            Phone
          </label>
        </div>
      </fieldset>

      <TextField
        id={phoneId}
        name="phone"
        label={preferredContact === "phone" ? "Phone" : "Phone (optional)"}
        type="tel"
        autoComplete="tel"
        value={phone}
        disabled={disabled}
        onChange={(event) => onPhoneChange(event.target.value)}
        aria-invalid={phoneError ? true : undefined}
        aria-describedby={phoneError ? phoneErrorId : undefined}
      />
      {phoneError && (
        <p id={phoneErrorId} className="text-xs text-status-danger">
          {phoneError}
        </p>
      )}
    </>
  );
}

/**
 * `/support` (CQ-034 spec.md): topic + message + preferred contact +
 * phone, one submit, then a confirmation state with the reference and the
 * assigned LO's direct contact. `phone` prefills from `useBorrowerSession()`
 * -- `me.phone`, i.e. the borrower's `/me` response (plan.md Decision #3;
 * the party record was the other option but is per-application, not
 * per-borrower, so `/me` is the only source that works with 0 or 2+
 * applications).
 */
export function SupportForm() {
  const { me } = useBorrowerSession();

  const [topic, setTopic] = useState<SupportTopic>("application");
  const [message, setMessage] = useState("");
  const [preferredContact, setPreferredContact] = useState<PreferredContact>("email");
  const [phone, setPhone] = useState(me.phone ?? "");
  const [clientError, setClientError] = useState<{
    field: "message" | "phone";
    text: string;
  } | null>(null);
  const [result, setResult] = useState<SubmitResult | null>(null);

  const messageId = useId();
  const messageErrorId = useId();
  const messageCounterId = useId();
  const phoneId = useId();
  const phoneErrorId = useId();
  const contactLegendId = useId();

  const { pending, error, run } = useAsyncSubmit(
    async (values: FormValues) => {
      const { data, error: apiError } = await submitSupportRequest({
        topic: values.topic,
        message: values.message,
        preferred_contact: values.preferredContact,
        phone: values.phone || undefined,
      });
      if (!data) return { ok: false as const, error: apiError };
      return { ok: true as const, data };
    },
    {
      fallbackError: GENERIC_ERROR,
      onSuccess: (data, values) =>
        setResult({
          reference: data.reference,
          lo: data.lo,
          preferredContact: values.preferredContact,
        }),
    },
  );

  const trimmedMessage = message.trim();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setClientError(null);

    if (trimmedMessage.length < MESSAGE_MIN_LENGTH || trimmedMessage.length > MESSAGE_MAX_LENGTH) {
      setClientError({
        field: "message",
        text: `Message must be ${MESSAGE_MIN_LENGTH}-${MESSAGE_MAX_LENGTH} characters.`,
      });
      return;
    }

    if (preferredContact === "phone" && phone.trim().length === 0) {
      setClientError({ field: "phone", text: "Phone is required for a phone callback." });
      return;
    }

    void run({ topic, message: trimmedMessage, preferredContact, phone: phone.trim() });
  }

  if (result) {
    return <SupportConfirmation result={result} />;
  }

  const rateLimited = error === "Please try again later";
  const displayedError = clientError?.field ? null : (error ?? null);
  const messageError = clientError?.field === "message" ? clientError.text : null;
  const phoneError = clientError?.field === "phone" ? clientError.text : null;

  return (
    <form onSubmit={handleSubmit} noValidate className="flex max-w-lg flex-col gap-4">
      <h1 className="text-2xl font-semibold text-navy-900">Get in touch</h1>
      <p className="text-neutral-600">
        Tell us what&rsquo;s going on and we&rsquo;ll follow up as soon as we can.
      </p>

      <Select
        id="support-topic"
        label="What's this about?"
        value={topic}
        onChange={(value) => setTopic(value as SupportTopic)}
        options={SUPPORT_TOPICS}
        disabled={pending}
      />

      <MessageField
        id={messageId}
        counterId={messageCounterId}
        errorId={messageErrorId}
        value={message}
        error={messageError}
        disabled={pending}
        onChange={setMessage}
      />

      <ContactFields
        legendId={contactLegendId}
        preferredContact={preferredContact}
        onPreferredContactChange={setPreferredContact}
        phoneId={phoneId}
        phoneErrorId={phoneErrorId}
        phone={phone}
        phoneError={phoneError}
        disabled={pending}
        onPhoneChange={setPhone}
      />

      {displayedError && (
        <p role="alert" className="text-sm text-status-danger">
          {rateLimited ? "Please try again later" : displayedError}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        Send message
      </Button>
    </form>
  );
}
