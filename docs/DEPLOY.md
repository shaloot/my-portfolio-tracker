# Deploy free on GitHub Pages

You run every command below yourself - nothing here touches your GitHub account
automatically. After you push, the included Action
(`.github/workflows/update.yml`) takes over: it fetches EOD data, commits
refreshed `data/*.json` back to the repo, and publishes the site to Pages.

Prerequisite: build the data at least once locally first so the repo has
`data/*.json` (see the README "Build and run locally" section) - or just let the
first workflow run generate it.

## 1. Create a public repo and push this project
```bash
git init
git add .
git commit -m "Initial portfolio tracker"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```
*What this did:* published your code to GitHub. Refresh your repo page - you
should see all the files. Keep the repo **public** so Actions minutes and Pages
hosting stay free.

## 2. Turn on GitHub Pages via Actions
Go to your repo -> **Settings -> Pages** -> under **Build and deployment ->
Source**, choose **GitHub Actions**.

*What this did:* told GitHub to publish the site from the workflow (not from a
branch). You should see "Your site is ready to be published" once the first run
finishes.

## 3. Let the workflow run
Go to the **Actions** tab -> open **"Update & deploy portfolio"** -> **Run
workflow**.

*What this did:* ran `fetch.py` with live data, committed refreshed `data/*.json`
back to the repo, and deployed to Pages. When it finishes (green check), the job
summary shows your live URL: `https://<your-username>.github.io/<repo-name>/`.
After this it re-runs automatically every weekday evening and on every change you
push.

## 4. (Optional) Switch to a keyed provider
Only if you want Twelve Data for US reliability:

- **Settings -> Secrets and variables -> Actions -> Variables** -> add
  `PRICE_PROVIDER_US` = `twelvedata`.
- **-> Secrets** -> add `TWELVEDATA_API_KEY` = your key from twelvedata.com.

*What this did:* the next build uses Twelve Data for US symbols. The key stays in
CI and is never sent to the browser.

---

## Free-by-design guardrails

- **One fetch per day**, not per visitor -> API usage is constant regardless of traffic.
- **Keyless defaults** -> nothing to leak; a secret is needed only if you opt into Twelve Data.
- **Per-symbol failures degrade gracefully** -> one bad ticker never breaks the build.
- **Public repo** -> GitHub Actions minutes and Pages hosting are free.
