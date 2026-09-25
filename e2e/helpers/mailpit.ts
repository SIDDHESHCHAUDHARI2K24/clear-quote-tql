// Reads the most recent OTP email Mailpit received for `to`, via Mailpit's
// REST API (https://mailpit.axllent.org/docs/api-v1/), and extracts the
// 6-digit sign-in code both `auth/staff/service.py` and
// `auth/borrower/service.py` send (`_OTP_EMAIL_HTML`: "Your Clear Quote
// sign-in code is <strong>{code}</strong>."). Mailpit runs on :8025 in the
// shared local stack (infra/docker-compose.yml) -- one Mailpit instance for
// every worktree/slot (docs/backlog/phase-p3-p4-foundation.md "How workers
// use it": up to 10 slots can run `make e2e` concurrently against it), so
// this uses Mailpit's *search* endpoint (`to:"<email>"`, confirmed against
// a live instance to return the same `{messages: [...]}` shape as
// `/api/v1/messages`) scoped to the recipient's own mailbox, instead of
// paging through the N most recent messages across every mailbox -- a
// fixed page size there could put this email past the page boundary while
// other slots' logins are also sending mail.

const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";
const OTP_SUBJECT = "Your Clear Quote sign-in code";
const OTP_CODE_RE = /\b(\d{6})\b/;

interface MailpitMessageSummary {
  ID: string;
  To: { Address: string }[];
  Subject: string;
  Created: string;
}

interface MailpitMessagesResponse {
  messages: MailpitMessageSummary[];
}

interface MailpitMessage {
  Text: string;
  HTML: string;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${MAILPIT_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Mailpit request failed: ${path} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

// Polls (Mailpit delivery over local SMTP is fast but not synchronous with
// the API call that triggered it) for the newest OTP email to `email`,
// then extracts its 6-digit code. Throws if none arrives within `timeoutMs`.
export async function readOtpCode(email: string, timeoutMs = 10_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  const normalized = email.toLowerCase();
  const query = encodeURIComponent(`to:"${normalized}" subject:"${OTP_SUBJECT}"`);

  while (Date.now() < deadline) {
    const { messages } = await fetchJson<MailpitMessagesResponse>(
      `/api/v1/search?query=${query}&limit=10`,
    );
    const candidates = [...messages].sort(
      (a, b) => new Date(b.Created).getTime() - new Date(a.Created).getTime(),
    );

    if (candidates.length > 0) {
      const full = await fetchJson<MailpitMessage>(`/api/v1/message/${candidates[0].ID}`);
      const match = OTP_CODE_RE.exec(full.Text || full.HTML);
      if (match) return match[1];
    }

    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(`No OTP email arrived for ${email} within ${timeoutMs}ms`);
}
