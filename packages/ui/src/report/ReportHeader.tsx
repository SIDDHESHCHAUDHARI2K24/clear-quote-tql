import { formatDate, formatMoney } from "./format";
import type { ReportHeaderData } from "./types";

export interface ReportHeaderProps {
  header: ReportHeaderData;
}

export function ReportHeader({ header }: ReportHeaderProps) {
  return (
    <header className="rounded-lg bg-navy-900 px-6 py-8 text-neutral-0 sm:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">
            {header.first_name}, here are your numbers
          </h1>
          <p className="mt-2 text-navy-100">{header.property_label}</p>
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm text-navy-100">
            <div className="flex gap-1">
              <dt className="font-medium">Purchase price</dt>
              <dd className="num">{formatMoney(header.purchase_price)}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="font-medium">Prepared</dt>
              <dd>{formatDate(header.prepared_at)}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="font-medium">Rates as of</dt>
              <dd>{formatDate(header.rates_as_of)}</dd>
            </div>
          </dl>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex h-10 shrink-0 items-center justify-center rounded-md bg-sage-500 px-4 text-sm font-medium text-navy-900 hover:bg-sage-300 print:hidden"
        >
          Save as PDF
        </button>
      </div>
    </header>
  );
}
