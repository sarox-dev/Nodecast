# Save intent implementation plan

Status: implementation in progress; no production migration or release verified.

## Product contract

- Saving remains immediate and independent of AI. Adding a reason is optional.
- A user-entered reason is distinct from an AI hypothesis and source content. AI must never invent or overwrite user intent.
- A user can edit a reason or explicitly decline further prompts. Silence after seven days expires the prompt without recording a refusal.
- Background inference sees only the current capture's bounded title and selected text, not other evidence. External processing must be opt-in with clear provider/data disclosure.
- Suggested categories and tags are editable suggestions, not facts. Time proximity is only a weak signal for proposed relationships and cannot create confirmed relations.
- Raw capture provenance stays immutable; reason metadata belongs to its capture and account.

## Delivery stages

1. Add non-destructive per-capture metadata migration and account-scoped reason API. Preserve raw data and existing capture insertion; validate isolation and upgrades on temporary databases.
2. Add optional, keyboard-accessible Add reason action after a successful extension save, using the existing account-bound extension token. Provide editing from the saved-source view; failed reason updates must not invalidate the original save.
3. Implement an opt-in inference feature and explicit job dispatch in the existing durable job worker. Use bounded current-capture input, a versioned prompt and structured output with an unknown outcome. Store hypotheses separately from confirmed user reasons; apply compare-and-set so a late job cannot overwrite a user edit or decline. Retry safely and prevent duplicate jobs.
4. Build a quiet review queue with saved-time expiry and distinct declined/expired outcomes. Offer batch dismissal and settings to disable prompts. Never reprompt dismissed or expired items automatically.
5. Add user-approved/recent reason suggestions and separately labelled generated categories/tags. Respect corrections and never silently recreate removed suggestions.
6. Evaluate retrieval using confirmed intent and separately weighted hypotheses, source evidence and weak temporal signals. Do not promote guesses into source facts or confirmed relations. Test semantic examples and unrelated same-hour captures before integration.

## Verification and rollout

- Isolated tests: migration of legacy databases, capture ownership, raw immutability, AI failure and retry, delayed-job races, timeout/expiry, explicit decline, disabled processing, prompt injection, duplicate jobs and deletion.
- Extension tests: every save route, keyboard and mouse, narrow viewports, capture success with reason update failure, token changes and account isolation.
- Evaluate inference on representative labelled captures: precision of suggestions, unknown rate, incorrect intent attribution and user interaction cost.
- Verify full pairing -> capture -> reason -> account switch in an authenticated browser. Test Chromium and Firefox builds.
- Never migrate a live user's `contents/` without target-specific approval. Prior to deployment make an approved backup and verify migration against a disposable copy; roll back code without deleting user data if health checks fail.
