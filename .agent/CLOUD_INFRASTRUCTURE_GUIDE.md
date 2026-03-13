# Phase 1.4: Cloud Infrastructure & Cost-Saving Strategy

This guide outlines exactly how we will deploy the MediAgent infrastructure and, more importantly, **how we will stretch our $300 Google Cloud credit across the next 10 months** leading up to the December demo.

## The "Scale-to-Zero" Cost Strategy

To survive 10 months on a fixed budget, our golden rule is **Scale-to-Zero**. We will rely heavily on generous free tiers across all platforms, ensuring that when the app is not actively being developed or demoed, it costs exactly $0.00.

| Service | Platform | Cost Strategy | Expected Monthly Cost |
|---------|----------|---------------|------------------------|
| **Backend API** | GCP Cloud Run | Set `min-instances: 0` and `max-instances: 2`. Cloud Run's free tier gives 2M requests/month free. It will spin down completely when not in use. | $0.00 |
| **Frontend (Portals)** | Vercel | Use a **Hobby** account. Do NOT create a Vercel "Team" ($20/mo/user). Have one person link the GitHub repo; PRs will still auto-deploy preview links for everyone via GitHub integrations. | $0.00 |
| **Database & Auth** | Supabase | Free tier. Note: Free projects pause after 1 week of inactivity. Just go to the Supabase dashboard and click "Restore" when returning to work. | $0.00 |
| **Cron Jobs** | GCP Cloud Scheduler | GCP gives 3 free cron jobs per month per billing account. We will consolidate our tasks into 3 distinct endpoints. | $0.00 |
| **Error Tracking** | Sentry | Developer Free Tier gives 5,000 errors/month. | $0.00 |
| **AI Subsystems** | Gemini API | Use the free tier (15 Requests Per Minute). Perfect for development. | $0.00 |

*With this setup, your $300 credit is purely a safety net for unexpected spikes, data egress overages, or heavy load-testing near demo day.*

---

## Execution Steps for the Team

### 1. Google Cloud Platform (GCP) Setup
We will host our backend on GCP. 

> [!CAUTION]
> **The 90-Day Credit Expiration Trap!**
> The $300 free trial credit on Google Cloud **expires exactly 90 days after activation**, regardless of how much you have spent. Since our demo is in 10 months (December), **DO NOT ACTIVATE THIS CREDIT YET.**

**The Team Account Strategy:**
If you activate the $300 credit right now, it will expire in June. Instead, use a "Relay" approach across your teammates. **You do NOT need to recreate the project or database.** Google Cloud decouples "Projects" from "Billing Accounts". You simply change which billing account powers the project.

- **Phase 1 (March – May):** Rely purely on the "Always Free" tier (`min-instances: 0` on Cloud Run). This requires a billing account, but no trial credits need to be active if we stay under limits. Alternatively, Teammate A activates their 90-day trial.
- **Phase 2 (June – August):** Teammate B activates their 90-day trial. The Project Admin goes to `GCP Console -> Billing -> Change Billing Account` and links Teammate B's new trial to the existing project.
- **Phase 3 (Sept – Demo Day):** Teammate C activates their 90-day trial, and the Project Admin links it. This credit covers the massive traffic spike, load testing, and keeping the server "warm" (`min-instances: 1`) for the live December demo.

**Setup Steps:**
- **Step 1:** Choose *one* team member's Google account to act as the current host. They create the project `mediagent-dev`.
- **Step 2:** Go to **IAM & Admin** and add all other teammates as "Project Owners" or "Billing Managers" so everyone has access to manage billing later.
- **Step 3:** Go to **IAM & Admin** and add all teammates as "Editors" so everyone has access to the console and metrics.
- **Step 4:** Enable the following APIs:
  - Cloud Run API
  - Cloud Scheduler API
  - Artifact Registry API
  - Secret Manager API

### 2. Backend Deployment (Cloud Run)
Instead of a rented server (VPS/EC2) that runs 24/7 and drains the $300 quickly, we use serverless containers.
- **Step 1:** We will create a GitHub Action (`.github/workflows/deploy-backend.yml`).
- **Step 2:** When a PR merges to `main`, the Action builds the Docker container and pushes it to GCP Artifact Registry.
- **Step 3:** The Action deploys to Cloud Run with these strict cost-saving flags:
  ```bash
  gcloud run deploy mediagent-backend \
    --image <image-url> \
    --min-instances 0 \     # <-- THIS IS THE COST SAVER
    --max-instances 2 \     # Prevents massive runaway scaling costs
    --cpu 1 \
    --memory 512Mi \
    --allow-unauthenticated
  ```
- **Why this matters:** `min-instances 0` is the secret sauce. The server sleeps when we sleep. The only downside is a slight 2-second "cold start" delay on the very first API request of the day.

### 4. Frontend Deployment (Vercel)
Vercel is unbeatable for Next.js, but team plans are expensive. We will bypass this.
- **Step 1:** One person logs into Vercel using their personal GitHub account (Hobby plan).
- **Step 2:** Create two new Vercel projects: `mediagent-patient` and `mediagent-clinician`.
- **Step 3:** Link them to the `apps/patient-portal` and `apps/clinician-portal` directories in our monorepo.
- **Step 4:** Set up Environment Variables in the Vercel UI.
- **Teammate workflow:** Teammates do NOT need Vercel accounts. When they push a commit or open a Pull Request on GitHub, Vercel's GitHub Bot will automatically build it and post a preview link directly in the PR comments!

### 5. Cron Jobs (Cloud Scheduler)
We need cron jobs to trigger the backend to calculate adherence scores and send daily reminders.
- **Step 1:** In GCP, search for Cloud Scheduler.
- **Step 2:** Create a job that runs periodically (e.g., `0 8 * * *` for 8:00 AM daily).
- **Step 3:** Set the target to `HTTP`, Method to `POST`, and point it to the Cloud Run backend URL (e.g., `https://backend-url.run.app/api/v1/cron/daily-update`).
- **Cost Saving:** Keep it under 3 total jobs to stay 100% free. If we have more than 3 background tasks, we will trigger them all from a single API endpoint.

### 6. Managing Secrets (Environment Variables)
Since we have multiple cloud platforms, keeping `.env` files synced is critical.
- **Local Dev:** We will maintain an up-to-date `.env.example` in the repo. Teammates must duplicate it to `.env` locally.
- **Backend (GCP):** Store secrets (Supabase keys, Gemini keys) in GCP Secret Manager. We will grant the Cloud Run service account access to read them at runtime.
- **Frontend (Vercel):** Add them through the Vercel Project Settings -> Environment Variables.

### 7. Sentry Setup (Error Monitoring)
- **Step 1:** Go to Sentry.io and create a free Developer plan.
- **Step 2:** Create a Python/FastAPI project and two React/Next.js projects.
- **Step 3:** Invite teammates to the Sentry org.
- **Step 4:** Add the DSN keys to local `.env`, GCP, and Vercel. Sentry will now catch all 500 errors and unhandled exceptions, alerting us in Slack/Discord before demo day.

---

## 🎯 Summary for Demo Day (December)
By strictly following the `min-instances: 0` rule and leveraging free tiers, the $300 credit will remain largely untouched by December. 

**Demo Preparation:**
About one week before the live demo, we will temporarily update our Cloud Run deployment to `min-instances: 1`. This stops the container from sleeping, ensuring there is absolutely zero "cold start" delay when presenting to the judges/audience. This will finally start burning a few dollars of the $300 credit, but you will have plenty of budget left to easily cover it!
