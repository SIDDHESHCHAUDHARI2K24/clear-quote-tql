"use client";

import { CheckboxField, Field } from "../fields";
import { getBool, getString } from "../paths";
import type { TabFormProps } from "./TabForm";

export interface ConsentTabProps extends TabFormProps {
  /** Tab 1's `first_name last_name` (plan.md: "typed_name ... must equal
   * tab 1 first_name + ' ' + last_name, case-insensitive"). */
  expectedName: string;
  consentVersion: string;
  consentText: string;
}

/** Tab 4 (spec.md table): the three consent checkboxes and a typed
 * signature. The wizard's shared button bar (not this component) submits
 * the application once this tab validates. */
export function ConsentTab({
  data,
  set,
  errorFor,
  disabled,
  expectedName,
  consentVersion,
  consentText,
}: ConsentTabProps) {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-navy-900">Consent</h2>
        <div className="max-h-40 overflow-y-auto rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-600">
          {consentText}
        </div>
        <p className="text-xs text-neutral-500">Version {consentVersion}</p>
      </section>

      <section className="flex flex-col gap-3">
        <CheckboxField
          id="soft-pull-authorized"
          label="I authorize Clear Quote to run a soft credit pull. This will not affect my credit score."
          checked={getBool(data, "soft_pull_authorized")}
          disabled={disabled}
          onChange={(checked) => set("soft_pull_authorized", checked, "soft_pull_authorized")}
          error={errorFor("soft_pull_authorized")}
        />
        <CheckboxField
          id="contact-consent"
          label="I agree to be contacted about my application by phone, email or text."
          checked={getBool(data, "contact_consent")}
          disabled={disabled}
          onChange={(checked) => set("contact_consent", checked, "contact_consent")}
          error={errorFor("contact_consent")}
        />
        <CheckboxField
          id="terms-accepted"
          label="I agree to the terms above."
          checked={getBool(data, "terms_accepted")}
          disabled={disabled}
          onChange={(checked) => set("terms_accepted", checked, "terms_accepted")}
          error={errorFor("terms_accepted")}
        />
      </section>

      <Field
        id="typed-name"
        label="Type your full name to sign"
        placeholder={expectedName || "Your full name"}
        value={getString(data, "typed_name")}
        disabled={disabled}
        onChange={(e) => set("typed_name", e.target.value, "typed_name")}
        error={errorFor("typed_name")}
      />
    </div>
  );
}
