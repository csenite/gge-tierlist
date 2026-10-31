# G Generation Eternal tier lists (English)

Game8 (Japan) tier lists for SD Gundam G Generation Eternal, with official English unit names.
Live at https://csenite.github.io/gge-tierlist/

- `data/site.json` holds every list: English names, tags, thumbnails and the translated notes.
- `data/names.json` maps Game8's Japanese unit names to official English names.
- `template.html` is the page; `scripts/build.py` puts the data into it and writes `index.html`.
- `scripts/scrape.py` reads Game8 and updates `data/site.json`.
- `scripts/soshage.py` downloads soshage.com's official English names, thumbnails and series into
  `data/soshage.json`. The page shows those names, pictures and series logos.

Every day at 08:41 Malaysia time, `.github/workflows/daily.yml` refreshes the soshage data, then
runs the scraper. A new Game8 unit gets its English name from soshage when the Japanese names match.
If every unit has an English name it rebuilds and publishes the site.
If Game8 added a unit that isn't on soshage yet, or changed its commentary, it leaves the
site as it is and opens a "needs-translation" issue. Add the names to `data/names.json`
(or update the notes in `data/site.json`) and push; the workflow then runs again and publishes.
