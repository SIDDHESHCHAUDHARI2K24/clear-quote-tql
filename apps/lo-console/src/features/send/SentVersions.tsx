import Link from "next/link";

import { apiHref, type Loaded, type SentVersion } from "./api";
import { formatSentAt, outboxHref } from "./versions";

export interface SentVersionsProps {
  versions: Loaded<SentVersion[]> | null;
}

/** Every version this package was sent as, newest first: when, whether a
 * newer send replaced it, its PDF and its email in the Outbox. */
export function SentVersions({ versions }: SentVersionsProps) {
  if (versions === null || (versions.ok && versions.data.length === 0)) return null;
  return (
    <section className="flex flex-col gap-2" aria-labelledby="sent-versions-heading">
      <h3 id="sent-versions-heading" className="text-sm font-semibold text-navy-900">
        Sent versions
      </h3>
      {!versions.ok ? (
        <p role="alert" className="text-sm text-status-danger">
          {versions.message}
        </p>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="sent-versions">
          {versions.data.map((version) => (
            <li
              key={version.id}
              data-testid="sent-version"
              className="flex flex-col gap-1 rounded-md border border-neutral-200 px-3 py-2 text-sm text-navy-900"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">Version {version.version}</span>
                <span
                  className={
                    version.superseded
                      ? "text-xs text-neutral-600"
                      : "text-xs font-medium text-status-success"
                  }
                  data-testid="sent-version-state"
                >
                  {version.superseded ? "Superseded" : "Current"}
                </span>
              </div>
              <span className="text-neutral-600">
                Sent <time dateTime={version.sent_at}>{formatSentAt(version.sent_at)}</time>
                {version.recipient_email ? ` to ${version.recipient_email}` : ""}
                {version.viewed_at ? " · Viewed" : ""}
              </span>
              <div className="flex flex-wrap gap-3">
                {version.letter_url && (
                  <a
                    href={apiHref(version.letter_url)}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-navy-700 underline"
                  >
                    Download PDF
                  </a>
                )}
                {version.outbox_email_id && (
                  <Link
                    href={outboxHref(version.outbox_email_id)}
                    className="font-medium text-navy-700 underline"
                  >
                    Open in Outbox
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
