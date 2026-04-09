# QA Auth Accounts

Use real environment-specific accounts created through the normal signup flows. Do not commit live credentials to the repo.

## Required Accounts

Create one account for each shared QA environment:

- `Patient QA account`
- `Clinician QA account`

## Patient Account Checklist

1. Sign up through the patient portal `/signup`
2. Complete onboarding
3. Keep the account usable for:
   - login verification
   - onboarding verification
   - document upload verification
   - invite-code join verification

## Clinician Account Checklist

1. Sign up through the clinician portal `/signup`
2. Verify clinic profile fields are populated
3. Keep the account usable for:
   - login verification
   - dashboard access verification
   - invite-code generation
   - patient linking workflows

## Linking the Accounts

1. Sign in as the clinician QA user
2. Generate an invite code
3. Sign in as the patient QA user
4. Join the clinician with that invite code during onboarding or later through the patient flow

## Credential Sharing

- Share credentials with teammates out-of-band only
- Never place live passwords in the repo, screenshots, or committed environment files
- If a password changes, notify teammates in the same out-of-band channel

## Reset / Recovery

- If the patient account drifts, recreate it through the patient signup flow
- If the clinician account drifts, recreate it through the clinician signup flow
- Re-link the accounts with a fresh invite code after recreation
