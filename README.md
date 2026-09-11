# The Daily Twenty

Your own daily news page: world, business, technology, entertainment and games, Malaysia and Singapore. It includes photos and search, and each headline links to the full article.

GitHub rebuilds it for free every morning at 6:00 AM Malaysia time. You can also refresh it any time.

## One-time setup (about 10 minutes)

1. **Create the repository.** Sign in at github.com, click **+** (top right), choose **New repository**, name it `daily-twenty`, set it to **Public**, and click **Create repository**.
2. **Upload the files.** On the new repository page, click **uploading an existing file**. Drag in everything from this folder: `build.py`, `feeds.json`, `template.html`, `README.md`, `.gitignore` and the `.github` folder. Then click **Commit changes**.
   - If the `.github` folder didn't come across (Mac Finder hides folders that start with a dot), click **Add file → Create new file**. Type `.github/workflows/daily.yml` as the name, paste in the contents of that file, and commit.
3. **Turn on the website.** Go to **Settings → Pages**, and under **Build and deployment → Source** choose **GitHub Actions**.
4. **Build the first edition.** Go to the **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**. Pick **Build The Daily Twenty**, click **Run workflow**, then click the green **Run workflow** button.
5. **Open your page.** After about two minutes, visit `https://YOUR-GITHUB-USERNAME.github.io/daily-twenty/` and bookmark it (or use **Add to Home Screen** on your phone).

## Everyday use

- The page updates itself every morning. Stories published since your last visit are marked **New**.
- **Refresh now** on the page opens GitHub. Press **Run workflow**, and the page updates in about two minutes (you need to be signed in to GitHub).
- **Saved** stories are kept in the browser you saved them in, so your phone and laptop each keep their own list.

## Changing things

- **Sources:** edit `feeds.json` on GitHub (pencil icon). Each section lists feeds as `{"source": "Name", "url": "RSS link"}`. A feed that stops working is skipped automatically. Open the latest run in the Actions tab to see which feeds worked (OK / ERR).
- **Stories per section:** `per_section` in `feeds.json` (default 12). `max_per_source` stops one outlet from filling a row.
- **Update time:** edit `.github/workflows/daily.yml`. The line `cron: "0 22 * * *"` means 22:00 UTC, which is 6:00 AM in Malaysia. For 7:00 AM use `"0 23 * * *"`. To update twice a day, add a second line such as `- cron: "0 10 * * *"` (6:00 PM).

## Good to know

- Everything used here is free: public RSS feeds, GitHub Actions and GitHub Pages.
- X (Twitter) isn't included because its API is paid.
- Some outlets (e.g. Bloomberg, The Straits Times) put some articles behind a paywall. Their headlines still appear, but reading the full article may need a subscription.
- The repository must stay public for free GitHub Pages. It only contains the page code and the public headlines.
