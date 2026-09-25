import type { ClientDetail } from "../types";

export interface ClientDetailHeaderProps {
  client: ClientDetail;
}

/** spec.md CQ-026 "Frontend": name, contact details and assigned LO. */
export function ClientDetailHeader({ client }: ClientDetailHeaderProps) {
  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-lg font-semibold text-navy-900">{client.name}</h1>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-600">
        <span>{client.email}</span>
        {client.phone && <span>{client.phone}</span>}
        <span>
          LO: <span className="text-navy-900">{client.lo_name}</span>
        </span>
      </div>
    </div>
  );
}
