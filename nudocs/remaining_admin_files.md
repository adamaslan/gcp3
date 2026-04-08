# Remaining Files for Admin Dashboard

Because the automated file creation processes timed out or were cancelled continuously, the following exact files still need to be created in your workspace to complete the Admin Dashboard feature.

You can manually create these using the code blocks provided in the previous message, or we can try to find an alternative way to write them into your file system.

## 1. The Main UI Component
**File Path:** `frontend/src/app/admin/page.tsx`
- **Purpose:** Renders the secure, glassmorphism dashboard with buttons to trigger backend actions.
- **Dependencies:** Standard React (`useState`). No external packages are strictly required since all SVG icons are generated inline and Tailwind CSS is standard.

## 2. The API Route Proxies
These four Serverless API files are nearly identical in structure. They act as secure middlemen, receiving a `POST` request from the `/admin` browser, attaching the `SCHEDULER_SECRET` from `process.env.SCHEDULER_SECRET`, and proxying the request to the Python backend.

**File Paths:**
1. `frontend/src/app/api/admin/seed-etf-history/route.ts`
   - Proxies to: `POST $BACKEND_URL/admin/seed-etf-history`
   
2. `frontend/src/app/api/admin/compute-returns/route.ts`
   - Proxies to: `POST $BACKEND_URL/admin/compute-returns`

3. `frontend/src/app/api/admin/refresh-intraday/route.ts`
   - Proxies to: `POST $BACKEND_URL/refresh/intraday`

4. `frontend/src/app/api/admin/refresh-all/route.ts`
   - Proxies to: `POST $BACKEND_URL/refresh/all`

## 3. Environment Variable Reminder
**File Path:** `frontend/.env.local`
- **Action Required:** Ensure that `SCHEDULER_SECRET=your-secret-here` is added alongside your existing `BACKEND_URL` variable. This is critical for the new proxy routes to successfully authenticate with your FastAPI backend.
