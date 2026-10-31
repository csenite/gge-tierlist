# G Generation Eternal tier lists (English)

Game8 (Japan) tier lists for SD Gundam G Generation Eternal, with official English unit names.
Live at https://csenite.github.io/gge-tierlist/

- `data/site.json` holds every list: English names, tags, thumbnails and the translated notes.
- `data/names.json` maps Game8's Japanese unit names to official English names.
- `template.html` is the page; `scripts/build.py` puts the data into it and writes `index.html`.
- `scripts/scrape.py` reads Game8 and updates `data/site.json`.

Every day at 08:41 Malaysia time, `.github/workflows/daily.yml` runs the scraper.
If every unit already has an English name it rebuilds and publishes the site.
If Game8 added a unit with no English name yet, or changed its commentary, it leaves the
site as it is and opens a "needs-translation" issue. Add the names to `data/names.json`
(or update the notes in `data/site.json`) and push; the workflow then runs again and publishes.
