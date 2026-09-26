"use client";

import { Select } from "@cq/ui";

import { CheckboxField, Field } from "../fields";
import { getBool, getString } from "../paths";
import type { JsonRecord } from "../paths";
import type { TabFormProps } from "./TabForm";

const MARITAL_OPTIONS = [
  { value: "unmarried", label: "Unmarried" },
  { value: "married", label: "Married" },
  { value: "separated", label: "Separated" },
];

const HOUSING_OPTIONS = [
  { value: "rent", label: "Rent" },
  { value: "own", label: "Own" },
  { value: "rent_free", label: "Live rent-free" },
];

function p(prefix: string, name: string): string {
  return prefix ? `${prefix}.${name}` : name;
}

interface AddressFieldsProps {
  data: JsonRecord;
  set: TabFormProps["set"];
  errorFor: TabFormProps["errorFor"];
  disabled: boolean;
  prefix: string;
  idPrefix: string;
}

/** Street/city/state/zip, reused for `current_address` and
 * `prior_address` (react-doctor `no-high-complexity-react-function`: split
 * out of `YouTab`). */
function AddressFields({ data, set, errorFor, disabled, prefix, idPrefix }: AddressFieldsProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field
        id={`${idPrefix}-street`}
        label="Street address"
        className="sm:col-span-2"
        value={getString(data, p(prefix, "street"))}
        disabled={disabled}
        onChange={(e) => set(p(prefix, "street"), e.target.value, p(prefix, "street"))}
        error={errorFor(p(prefix, "street"))}
      />
      <Field
        id={`${idPrefix}-city`}
        label="City"
        value={getString(data, p(prefix, "city"))}
        disabled={disabled}
        onChange={(e) => set(p(prefix, "city"), e.target.value, p(prefix, "city"))}
        error={errorFor(p(prefix, "city"))}
      />
      <div className="grid grid-cols-2 gap-3">
        <Field
          id={`${idPrefix}-state`}
          label="State"
          maxLength={2}
          value={getString(data, p(prefix, "state"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "state"), e.target.value, p(prefix, "state"))}
          error={errorFor(p(prefix, "state"))}
        />
        <Field
          id={`${idPrefix}-zip`}
          label="ZIP"
          inputMode="numeric"
          maxLength={5}
          value={getString(data, p(prefix, "zip"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "zip"), e.target.value, p(prefix, "zip"))}
          error={errorFor(p(prefix, "zip"))}
        />
      </div>
    </div>
  );
}

interface PersonIdentityFieldsProps {
  data: JsonRecord;
  set: TabFormProps["set"];
  errorFor: TabFormProps["errorFor"];
  disabled: boolean;
  prefix: string;
  idPrefix: string;
  email?: string;
}

/** Name/phone/DOB/SSN/marital status/dependents -- reused for the
 * borrower and, when added, the co-borrower (react-doctor
 * `no-high-complexity-react-function`). The SSN input never carries a
 * previously-saved value (decision 25): once `ssn_set` is true it shows a
 * "saved" hint instead, and a blank/untouched input keeps the one on
 * file. */
function PersonIdentityFields({
  data,
  set,
  errorFor,
  disabled,
  prefix,
  idPrefix,
  email,
}: PersonIdentityFieldsProps) {
  const ssnSet = getBool(data, p(prefix, "ssn_set"));
  const ssnLast4 = getString(data, p(prefix, "ssn_last4"));
  const ssnValue = getString(data, p(prefix, "ssn"));

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          id={`${idPrefix}-first-name`}
          label="First name"
          value={getString(data, p(prefix, "first_name"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "first_name"), e.target.value, p(prefix, "first_name"))}
          error={errorFor(p(prefix, "first_name"))}
        />
        <Field
          id={`${idPrefix}-last-name`}
          label="Last name"
          value={getString(data, p(prefix, "last_name"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "last_name"), e.target.value, p(prefix, "last_name"))}
          error={errorFor(p(prefix, "last_name"))}
        />
      </div>

      {email !== undefined && (
        <Field id={`${idPrefix}-email`} label="Email" value={email} disabled readOnly />
      )}
      {email === undefined && (
        <Field
          id={`${idPrefix}-email`}
          label="Email (optional)"
          type="email"
          value={getString(data, p(prefix, "email"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "email"), e.target.value, p(prefix, "email"))}
          error={errorFor(p(prefix, "email"))}
        />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          id={`${idPrefix}-phone`}
          label="Cell phone"
          type="tel"
          inputMode="tel"
          value={getString(data, p(prefix, "cell_phone"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "cell_phone"), e.target.value, p(prefix, "cell_phone"))}
          error={errorFor(p(prefix, "cell_phone"))}
        />
        <Field
          id={`${idPrefix}-dob`}
          label="Date of birth"
          type="date"
          value={getString(data, p(prefix, "dob"))}
          disabled={disabled}
          onChange={(e) => set(p(prefix, "dob"), e.target.value, p(prefix, "dob"))}
          error={errorFor(p(prefix, "dob"))}
        />
      </div>

      <Field
        id={`${idPrefix}-ssn`}
        label="Social Security number"
        inputMode="numeric"
        placeholder="123-45-6789"
        value={ssnValue}
        disabled={disabled}
        onChange={(e) => set(p(prefix, "ssn"), e.target.value, p(prefix, "ssn"))}
        error={errorFor(p(prefix, "ssn"))}
        helperText={
          ssnSet && !ssnValue
            ? `SSN on file: •••-••-${ssnLast4} (leave blank to keep it)`
            : undefined
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          id={`${idPrefix}-marital-status`}
          label="Marital status"
          options={MARITAL_OPTIONS}
          value={getString(data, p(prefix, "marital_status"))}
          disabled={disabled}
          onChange={(value) => set(p(prefix, "marital_status"), value, p(prefix, "marital_status"))}
          error={errorFor(p(prefix, "marital_status"))}
        />
        <Field
          id={`${idPrefix}-dependents`}
          label="Dependents"
          inputMode="numeric"
          value={getString(data, p(prefix, "dependents_count"))}
          disabled={disabled}
          onChange={(e) =>
            set(p(prefix, "dependents_count"), e.target.value, p(prefix, "dependents_count"))
          }
          error={errorFor(p(prefix, "dependents_count"))}
        />
      </div>
    </div>
  );
}

export interface YouTabProps extends TabFormProps {
  email: string;
}

/** Tab 1 (spec.md table): borrower identity, current + prior address, and
 * an optional co-borrower. */
export function YouTab({ data, set, errorFor, disabled, email }: YouTabProps) {
  const years = getString(data, "residence_years");
  const months = getString(data, "residence_months");
  const totalMonths =
    (years === "" ? 0 : Number(years) || 0) * 12 + (months === "" ? 0 : Number(months) || 0);
  const showPriorAddress =
    (years !== "" && months !== "" && totalMonths < 24) || Boolean(errorFor("prior_address"));
  const hasCoBorrower = getBool(data, "has_co_borrower");

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-navy-900">You</h2>
        <PersonIdentityFields
          data={data}
          set={set}
          errorFor={errorFor}
          disabled={disabled}
          prefix=""
          idPrefix="you"
          email={email}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-md font-semibold text-navy-900">Current address</h3>
        <AddressFields
          data={data}
          set={set}
          errorFor={errorFor}
          disabled={disabled}
          prefix="current_address"
          idPrefix="current-address"
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select
            id="housing-status"
            label="Own or rent"
            options={HOUSING_OPTIONS}
            value={getString(data, "housing_status")}
            disabled={disabled}
            onChange={(value) => set("housing_status", value, "housing_status")}
            error={errorFor("housing_status")}
          />
          <Field
            id="residence-years"
            label="Years there"
            inputMode="numeric"
            value={years}
            disabled={disabled}
            onChange={(e) => set("residence_years", e.target.value, "residence_years")}
            error={errorFor("residence_years")}
          />
          <Field
            id="residence-months"
            label="Months there"
            inputMode="numeric"
            value={months}
            disabled={disabled}
            onChange={(e) => set("residence_months", e.target.value, "residence_months")}
            error={errorFor("residence_months")}
          />
        </div>
      </section>

      {showPriorAddress && (
        <section className="flex flex-col gap-3">
          <h3 className="text-md font-semibold text-navy-900">Prior address</h3>
          <p className="text-sm text-neutral-600">
            You&rsquo;ve lived at your current address under 2 years -- add where you lived before.
          </p>
          {errorFor("prior_address") && (
            <p role="alert" className="text-xs text-status-danger">
              {errorFor("prior_address")}
            </p>
          )}
          <AddressFields
            data={data}
            set={set}
            errorFor={errorFor}
            disabled={disabled}
            prefix="prior_address"
            idPrefix="prior-address"
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select
              id="prior-housing-status"
              label="Own or rent (prior address)"
              options={HOUSING_OPTIONS}
              value={getString(data, "prior_housing_status") || "rent"}
              disabled={disabled}
              onChange={(value) => set("prior_housing_status", value, "prior_housing_status")}
              error={errorFor("prior_housing_status")}
            />
            <Field
              id="prior-residence-years"
              label="Years there"
              inputMode="numeric"
              value={getString(data, "prior_address.residence_years")}
              disabled={disabled}
              onChange={(e) =>
                set(
                  "prior_address.residence_years",
                  e.target.value,
                  "prior_address.residence_years",
                )
              }
              error={errorFor("prior_address.residence_years")}
            />
            <Field
              id="prior-residence-months"
              label="Months there"
              inputMode="numeric"
              value={getString(data, "prior_address.residence_months")}
              disabled={disabled}
              onChange={(e) =>
                set(
                  "prior_address.residence_months",
                  e.target.value,
                  "prior_address.residence_months",
                )
              }
              error={errorFor("prior_address.residence_months")}
            />
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <CheckboxField
          id="has-co-borrower"
          label="Add a co-borrower"
          checked={hasCoBorrower}
          disabled={disabled}
          onChange={(checked) => set("has_co_borrower", checked, "has_co_borrower")}
        />
        {hasCoBorrower && (
          <div className="flex flex-col gap-3 border-l-2 border-neutral-100 pl-4">
            <h3 className="text-md font-semibold text-navy-900">Co-borrower</h3>
            {errorFor("co_borrower") && (
              <p role="alert" className="text-xs text-status-danger">
                {errorFor("co_borrower")}
              </p>
            )}
            <PersonIdentityFields
              data={data}
              set={set}
              errorFor={errorFor}
              disabled={disabled}
              prefix="co_borrower"
              idPrefix="co-borrower"
            />
          </div>
        )}
      </section>
    </div>
  );
}
