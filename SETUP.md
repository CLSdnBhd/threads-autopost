# One-time setup (about 30 minutes)

You do the sign-ins and paste the keys yourself. Claude never sees your passwords or keys.
Do the parts in order. If anything looks different from these steps, tell Claude what you see.

---

## Part A: Give the system permission to post on your Threads (≈15 min)

1. On your computer, go to **developers.facebook.com** and log in with the Facebook account
   linked to your Instagram/Threads. If asked, register as a developer (free).
2. Click **My Apps → Create App**.
   - Use case: choose **Access the Threads API**.
   - App name: anything, e.g. `Calvin Threads Poster`. Skip the business portfolio if asked.
3. Inside the app, open **Use cases → Access the Threads API → Customize**. Make sure these
   permissions are added:
   `threads_basic`, `threads_content_publish`, `threads_manage_insights`, `threads_read_replies`.
4. Go to **App roles → Roles → Add people → Threads Tester** and enter your Threads username.
5. On your phone, in **Threads**: *Settings → Account → Website permissions → Invites*,
   and **accept** the invite.
6. Back in the Meta app: **Use cases → Access the Threads API → Settings**. Find
   **User Token Generator**, click **Generate access token** next to your account, approve,
   and copy the token.
7. In Finder, open the `threads-autopost` folder and create a plain text file named `.env`
   (TextEdit → Format → Make Plain Text) containing:
   ```
   THREADS_TOKEN=paste-the-token-here
   THREADS_APP_SECRET=paste-app-secret-here
   ```
   The app secret is under **App settings → Basic → App secret → Show**.
8. Tell Claude **"token added"**. Claude will run `tools/check_token.py` to confirm which account
   it posts as and, if it's a short-lived token, turn it into a 60-day one.

## Part B: Set up the free cloud timer on GitHub (≈10 min)

1. Sign up at **github.com** (free). Choose a username.
2. Click **+ → New repository**:
   - Name: `threads-autopost`
   - **Public** (Threads can only fetch photos from a public link. Your keys never go in it.)
   - Don't add a README. Click **Create repository**.
3. Create one access key so your Mac can upload and the token can renew itself:
   **Profile photo → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
   - Name: `threads-autopost`, expiry: 1 year
   - Repository access: **Only select repositories → threads-autopost**
   - Permissions → Repository: **Contents: Read and write**, **Secrets: Read and write**,
     **Workflows: Read and write**
   - Generate, and keep the tab open (you'll paste it twice below).
4. In the repository: **Settings → Secrets and variables → Actions → New repository secret**. Add two:
   - `THREADS_TOKEN`: the Threads token from your `.env` (use the 60-day one after Claude upgrades it)
   - `GH_PAT`: the GitHub access key from step 3
5. Tell Claude your **GitHub username** and **WhatsApp number**.

## Part C: Connect and test (≈5 min, with Claude)

1. Claude makes the first upload. The first time, a Terminal tab asks for your GitHub username,
   and for the **password** you paste the access key from Part B step 3. Your Mac remembers it after that.
2. In GitHub: **Actions → Post to Threads → Run workflow**, tick **Dry run**, then Run.
   It should finish green and show "Nothing due" (or the post it would make).
3. Real test: Claude queues one test post. You approve it, then run the workflow again with its
   **post_id** and Dry run unticked. Check that it appears on your Threads with the reply and WhatsApp link.

## Part D: Every week from now on

- Drop new properties into `threads-autopost/inbox/` (one folder each: photos + `details.txt`,
  see `inbox/_EXAMPLE-mont-kiara-3r2b/details.txt`).
- Sunday: Claude prepares the week (or ask anytime: **"prepare next week's Threads posts"**).
- Open the review page, ask for any changes, say **"approve all"**. Done for the week.

### Good to know
- Posts go out at 1:00 PM and 8:00 PM Malaysia time. GitHub can run 5–20 min late at busy times.
- If a slot is missed by more than 10 hours (e.g. you approved late), it's skipped, not double-posted.
- The token renews itself on the 1st and 15th of every month.
- To pause everything: GitHub → Actions → Post to Threads → **⋯ → Disable workflow**.
