# do-ve-so-site

Public pages and static results data for the Dò Vé Số iPhone app.

- `privacy.html`, `support.html`: App Store Privacy Policy and Support URLs.
- `api/v1/<region>/<yyyy-MM-dd>.json`: results per day and region (`south`, `central`, `north`); `api/v1/index.json` lists available days. 404 = not published yet.
- `crawler/crawl.py`: fetches the public RSS feeds, validates every prize tier (count and digit length), writes JSON. Run by `.github/workflows/crawl.yml` every 10 minutes during draw hours.

Local: `python3 -m unittest discover -s tests && python3 crawler/crawl.py .`

Note: GitHub disables scheduled workflows in repos with no activity for 60 days; the bot's data commits keep it active. If results stop updating, check the Actions tab.
