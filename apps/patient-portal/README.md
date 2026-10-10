This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

Care-team roles are displayed as readable en-US/es-MX labels rather than raw stored
codes; unknown roles use generic care-team copy. API transport recovery retries GET/HEAD
once after 100–249 ms, honors cancellation, and never retries HTTP errors or writes.
Today localizes connection/save errors using the loaded profile language. An uncertain
save leaves the task pending; refresh to inspect persisted state before a manual retry.

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Care team conversations

In Chat, choose **Care team messages**, then explicitly select a linked clinician.
Each clinician has a separate thread labelled with their clinic. Nora remains a
separate AI conversation; operational alerts are not human replies. The chooser,
composer, notices and recovery states support en-US and es-MX.
Genuine older human messages remain in a separately labelled, read-only historical
archive. They are not migrated into addressed threads, attributed to the selected
clinician, or given a reply route. Operational alerts remain filtered out.

Conversation requests use the authenticated `/api/v1/care-conversations` contract.
Messages load in pages of 50 with server cursors. The visible inbox and selected
thread poll every 15 seconds. Inbox refresh updates recipients and removes revoked
choices while preserving selection and drafts; unread
counts come from the server. Read markers reference the last displayed message ID.
An uncertain send preserves its text and UUID for an explicit retry, including
thread/view switches. The pending body is locked until that retry resolves.
Definitive validation rejection preserves text for editing. An idempotency mismatch
warns that the prior message may exist and requires confirmation to prepare a new
send key; preparation does not send the message.
Drafts are held in memory; reloading or signing out clears them.
These messages are not continuously monitored; the screen carries a 911 notice.

Requires the matching backend and conversation migration before rollout.
No deployed or browser acceptance is implied by local component tests.

## Visits scheduling

Visits shows appointment times and response deadlines in the patient's saved
timezone and `en-US`/`es-MX` locale. Slice 5 adds expired history without response
controls and translated overlap/expiry/past-time messages. Failed actions keep the
list visible; a saved response followed by a failed refresh has a distinct notice.
Visits refreshes at pending deadlines and on browser focus. The server/database
remains authoritative for expiry and booking conflicts.

Migrations 042 and 043 must be applied before activating the Slice 5 backend.
See [the scheduling design](../../.agent/specs/sch-001-appointment-scheduling.md#14-slice-5--booking-conflicts-and-proposal-expiry)
for rollout order and synthetic acceptance steps.

Confirmed/scheduled cards now include **Add to calendar / Agregar al calendario**.
Each click checks the current appointment and authorization before downloading an
`.ics` file. It contains a generic localized title, exact start/end and location;
clinical reasons and notes are omitted. It is a one-time copy: later changes and
cancellations do not sync, and the calendar app uses its own display timezone.
Failed downloads keep the visit list visible with a translated retry notice.
See [Slice 6 verification and click-through](../../.agent/specs/sch-001-appointment-scheduling.md#15-slice-6--one-time-calendar-export).

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
