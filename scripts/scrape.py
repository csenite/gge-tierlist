"""Read Game8's G Generation Eternal tier lists and update data/site.json.

Units are matched to the site's existing English entries by their Game8
thumbnail, then by Japanese name through data/names.json, then to soshage.com's
official English name (data/soshage.json, refreshed by scripts/soshage.py). A unit
that can't be matched needs a human translation: the script then leaves site.json alone and
writes report.md, so a partial update is never published.

Exit codes: 0 = done (site.json may have changed), 2 = needs translation.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from soshage import Soshage, ROLE as SOS_ROLE

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://game8.jp/ggene-eternal/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
UNIT_JSON = "https://assets.game8.jp/tools/script_template/ggene_unit.json"
UR_BOARD = "https://game8.jp/api/user_rating_tier_boards/3"
ROLE = {"攻撃": "ATK", "支援": "SUP", "耐久": "DEF"}
ORDER = ["SSS", "SS", "S", "A", "B", "C", "D"]

# list id -> (page id, Game8 tab label for each group; "_" = ungrouped)
TABLES = {
    "ssr": ("685124", {"_": "開発・配布"}),
    "gacha": ("685124", {"_": "ガチャ"}),
    "dev": ("684941", {"_": "通常・イベント開発"}),
    "ult": ("684941", {"_": "アルティメット開発"}),
    "sp": ("684033", {"ATK": "攻撃", "SUP": "支援", "DEF": "耐久"}),
    "ssp": ("750190", {"ATK": "攻撃", "SUP": "支援", "DEF": "耐久"}),
}
PAGES = {"strongest": "682964", **{k: v[0] for k, v in TABLES.items()}}
BY_SERIES = "684093"  # one row per series (and per tag), its best units in order; each links to its own tier page
ROW_TABLES = {"byseries": "シリーズ別最強", "bytag": "タグ別最強"}


class Source:
    def __init__(self, local):
        self.local = pathlib.Path(local) if local else None
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.8",
                               "Referer": "https://game8.jp/"})

    def get(self, url, name):
        if self.local:
            return (self.local / name).read_text()
        for attempt in range(3):
            r = self.s.get(url, timeout=60)
            if r.status_code == 200:
                time.sleep(2)
                return r.text
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"{url} returned {r.status_code}")

    def page(self, pid):
        return self.get(BASE + pid, pid + ".html")

    def json(self, url, name):
        return json.loads(self.get(url, name))


def img_key(url):
    m = re.search(r"img\.game8\.jp/(\d+/[0-9a-f]+\.\w+)", url or "")
    return m.group(1) if m else None


def tier_of(label):
    m = re.search(r"(SSS|SS|S|A|B|C|D)", label or "")
    return m.group(1) if m else None


def tab_tables(soup):
    """Map each Game8 tab label to the tier table inside that tab."""
    out = {}
    for box in soup.select(".a-tabContainer"):
        labels = [t.get_text(strip=True) for t in box.select(".a-tab")]
        panels = box.select(".a-tabPanels > .a-tabPanel")
        for lab, panel in zip(labels, panels):
            t = panel.find("table")
            if t is not None and lab not in out:
                out[lab] = t
    return out


def parse_table(table):
    tiers = {}
    for tr in table.find_all("tr"):
        th = tr.find("th")
        im = th.find("img") if th else None
        alt = (im.get("alt") or "") if im else ""
        if not alt.startswith("評価"):
            continue
        k = tier_of(alt[2:])
        units = []
        for td in tr.find_all("td"):
            for u in td.find_all("img"):
                units.append({"jp": (u.get("alt") or "").strip(),
                              "i": img_key(u.get("data-src") or u.get("src"))})
        tiers[k] = units
    return tiers


def parse_series_table(soup, heading="シリーズ別最強"):
    """Rows of the series (or tag) table: [{"s": name, "label": Game8's short name, "logo": img key, "page": id, "units": [...]}]."""
    h = next((h for h in soup.find_all("h3") if heading in h.get_text()), None)
    table = h.find_next("table") if h else None
    if not table:
        raise RuntimeError(f"{BY_SERIES}: series table not found")
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        logo = tds[0].find("img")
        link = tds[0].find("a")
        page = re.search(r"/(\d+)$", link.get("href") or "") if link else None
        units = [{"jp": re.sub(r"画像$", "", (u.get("alt") or "").strip()),
                  "i": img_key(u.get("data-src") or u.get("src"))} for u in tds[1].find_all("img")]
        rows.append({"s": re.sub(r"画像$", "", (logo.get("alt") or "").strip()) if logo else tds[0].get_text(strip=True),
                     "label": tds[0].get_text(" ", strip=True),
                     "logo": img_key(logo.get("data-src") or logo.get("src")) if logo else None,
                     "page": page.group(1) if page else None,
                     "units": units})
    if len(rows) < 5 or any(not r["units"] for r in rows):
        raise RuntimeError(f"{BY_SERIES}: read {len(rows)} series rows; page layout may have changed")
    return rows


def parse_series_page(soup, pid):
    """A series page's own tier list: the first table after the h3 「最強機体ランキング・Tier表」."""
    h = next((h for h in soup.find_all("h3") if h.get_text(strip=True) == "最強機体ランキング・Tier表"), None)
    table = h.find_next("table") if h else None
    tiers = parse_table(table) if table else {}
    if not tiers or None in tiers:
        raise RuntimeError(f"{pid}: series tier table not found or unreadable")
    # data-filter on each unit picture holds its rarity and role, e.g. "UR 攻撃"
    filters = {img_key(i.get("data-src") or i.get("src")): (i.get("data-filter") or "") for i in table.find_all("img")}
    for k in list(tiers):
        v = tiers[k] = [u for u in tiers[k] if u["jp"].endswith("画像")]  # drop overlay badges such as "overlay-1"
        if not v:
            del tiers[k]
        for u in v:
            u["jp"] = re.sub(r"画像$", "", u["jp"])
            u["f"] = filters.get(u["i"], "")
    return tiers


def notes_text(soup):
    """Game8's commentary: the "latest additions" section through the text under the tier table.

    Runs from the first h2 that mentions 最新 to the ranking-history heading
    (変動履歴) or the second h2 after it, whichever comes first.
    """
    h2s = soup.find_all("h2")
    start = next((h for h in h2s if "最新" in h.get_text()), None)
    if start is None:
        return ""
    later = [h.sourceline for h in h2s if h.sourceline > start.sourceline]
    stops = later[1:2] + [h.sourceline for h in soup.find_all(["h3", "h4"])
                          if "変動履歴" in h.get_text() and h.sourceline > start.sourceline][:1]
    stop = min(stops) if stops else float("inf")
    parts = []
    for e in soup.find_all(["h3", "h4", "p", "td"]):
        if (start.sourceline < e.sourceline < stop and not e.find(["p", "td"])
                and e.find_parent(class_="a-tabPanel") is None):
            t = e.get_text(" ", strip=True)
            if t:
                parts.append(t)
    return "\n".join(parts)


def date_modified(html):
    m = re.search(r'"dateModified"\s*:\s*"([^"]+)"', html)
    return m.group(1) if m else None


def scrape(src):
    game8, dates, notes = {}, {}, {}
    soups = {}
    for lid, pid in PAGES.items():
        if pid not in soups:
            html = src.page(pid)
            dates[pid] = date_modified(html)
            soups[pid] = BeautifulSoup(html, "html.parser")
            notes[pid] = notes_text(soups[pid])
    for lid, (pid, groups) in TABLES.items():
        tabs = tab_tables(soups[pid])
        game8[lid] = {}
        for g, lab in groups.items():
            if lab not in tabs:
                raise RuntimeError(f"{lid}: tab {lab} not found on page {pid}")
            game8[lid][g] = parse_table(tabs[lab])
    board = src.json(UR_BOARD, "board3.json")
    ur, ur_roles = {}, {}
    ser = {"key": {}, "title": {}, "icon": {}, "banner": {}}
    for t in board["tiers"]:
        k = tier_of(t.get("label") or t.get("value"))
        ur[k] = []
        for it in t["items"]:
            jp = it["title"].strip()
            ur[k].append({"jp": jp, "i": img_key(it.get("image_url"))})
            # col_57 「恒常or限定」: permanent or limited gacha banner
            b = (it.get("filter_values") or {}).get("col_57")
            b = b[0] if isinstance(b, list) and b else b
            if b in ("限定", "恒常"):
                ser["banner"][img_key(it.get("image_url"))] = "L" if b == "限定" else "N"
            sv = (it.get("filter_values") or {}).get("col_54")
            if sv:
                parts = [x.strip() for x in sv.split(":") if x.strip()]
                ser["key"].setdefault(img_key(it.get("image_url")), parts)
                ser["title"].setdefault(jp, parts)
            for v in (it.get("filter_values") or {}).values():
                for x in (v if isinstance(v, list) else [v]):
                    if x in ROLE:
                        ur_roles[jp] = ROLE[x]
    game8["strongest"] = {"_": ur}
    roles = {}
    cats = src.json(UNIT_JSON, "ggene_unit.json")
    for cat in cats:
        for u in cat.get("db_data", []):
            if u.get("col_1") == "シリーズ" and u.get("image_url"):
                ser["icon"][u["title"].strip()] = img_key(u["image_url"])
    for cat in cats:
        for u in cat.get("db_data", []):
            if u.get("col_2") in ROLE:
                roles[u["title"].strip()] = ROLE[u["col_2"]]
            # Banner backup for UR board items whose 恒常or限定 value is blank: col_57, or the gacha name in col_4
            b = u.get("col_57") or ""
            g = u.get("col_4") or ""
            if b not in ("限定", "恒常") and g.endswith("ガチャ"):
                b = "恒常" if g.startswith("恒常") else "限定"
            k = img_key(u.get("image_url"))
            if b in ("限定", "恒常") and k and k not in ser["banner"]:
                ser["banner"].setdefault("_unit:" + u["title"].strip(), "L" if b == "限定" else "N")
                ser["banner"].setdefault("_key:" + k, "L" if b == "限定" else "N")
            # UR records keep the series in col_54; SSR records in col_11 or col_59
            for col in ("col_54", "col_11", "col_59"):
                v = u.get(col) or ""
                parts = [x.strip() for x in v.split(":") if x.strip()]
                if parts and (col == "col_54" or all(x in ser["icon"] for x in parts)):
                    ser["key"].setdefault(img_key(u.get("image_url")), parts)
                    ser["title"].setdefault(u["title"].strip(), parts)
                    break
    roles.update(ur_roles)
    html = src.page(BY_SERIES)
    dates[BY_SERIES] = date_modified(html)
    soup = BeautifulSoup(html, "html.parser")
    ser["rows"] = {lid: parse_series_table(soup, kw) for lid, kw in ROW_TABLES.items()}
    for r in [r for rows in ser["rows"].values() for r in rows]:
        if r["page"]:
            html = src.page(r["page"])
            dates[r["page"]] = date_modified(html)
            r["tiers"] = parse_series_page(BeautifulSoup(html, "html.parser"), r["page"])
    return game8, dates, notes, roles, ser


def units_of(lst):
    if "rows" in lst:
        return {"_": {r["label"]: r["units"] for r in lst["rows"]}}
    if "groups" in lst:
        return {g: lst["groups"][g] for g in lst["groups"]}
    return {"_": lst["tiers"]}


def check_counts(game8, site):
    """Refuse obviously broken reads: empty lists or a list that lost over a third of its units."""
    for lid, groups in game8.items():
        new = sum(len(v) for g in groups.values() for v in g.values())
        old = sum(len(v) for g in units_of(site[lid]).values() for v in g.values())
        if new == 0 or new < old * 2 / 3:
            raise RuntimeError(f"{lid}: read {new} units, site has {old}; page layout may have changed")
        for g in groups.values():
            for k, v in g.items():
                if k is None:
                    raise RuntimeError(f"{lid}: a tier label couldn't be read")
                for u in v:
                    if not u["jp"] or not u["i"]:
                        raise RuntimeError(f"{lid} {k}: a unit is missing its name or image")


def fmt_date(iso):
    d = datetime.date.fromisoformat(iso[:10])
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="read saved pages from this folder instead of Game8")
    ap.add_argument("--report", default=str(ROOT / "report.md"))
    args = ap.parse_args()

    site_path, names_path, state_path = ROOT / "data/site.json", ROOT / "data/names.json", ROOT / "data/state.json"
    site = json.loads(site_path.read_text())
    names = json.loads(names_path.read_text()) if names_path.exists() else {}
    state = json.loads(state_path.read_text()) if state_path.exists() else {"dates": {}, "notes": {}}
    lists = {l["id"]: l for l in site["lists"]}

    game8, dates, notes, roles, ser = scrape(Source(args.local))
    check_counts(game8, lists)

    by_key = {}
    for l in site["lists"]:
        for g in units_of(l).values():
            for v in g.values():
                for u in v:
                    by_key.setdefault(u["i"], u["n"])

    sos_path = ROOT / "data/soshage.json"
    sos = Soshage.from_cache(sos_path) if sos_path.exists() else None
    auto, guess = {}, {}

    def from_soshage(jp, lid, role):
        """Official English name from soshage, without the "(EX)" the site shows as a tag."""
        if not sos:
            return None
        want = 5 if lid == "strongest" else 4 if lid in ("ssr", "gacha") else None
        m = sos.match(jp, want, close=False, role=SOS_ROLE.get(role))
        if m:
            auto[jp] = re.sub(r"\s*\(EX\)$", "", m["en"])
            return auto[jp]
        # A close but not exact match is often a sibling unit, so it only goes in the report as a hint.
        m = sos.match(jp, want)
        if m:
            guess[jp] = m["en"]
        return None

    unknown, changes = [], []
    new_lists = {}
    for lid, groups in game8.items():
        old = lists[lid]
        old_groups = units_of(old)
        in_list = {u["i"]: u for g in old_groups.values() for v in g.values() for u in v}
        in_list_by_name = {u["n"]: u for g in old_groups.values() for v in g.values() for u in v}
        out, added = {}, []
        for g, tiers in groups.items():
            out[g] = {}
            for k in ORDER:
                if k not in tiers:
                    continue
                row = []
                for u in tiers[k]:
                    en = (in_list[u["i"]]["n"] if u["i"] in in_list else by_key.get(u["i"]) or names.get(u["jp"])
                          or from_soshage(u["jp"], lid, roles.get(u["jp"]) or g))
                    if not en:
                        unknown.append((lid, g, k, u))
                        continue
                    names.setdefault(u["jp"], en)
                    prev = in_list.get(u["i"]) or in_list_by_name.get(en)
                    if prev is not None:
                        tags = prev["t"]
                    else:
                        added.append(en)
                        role = roles.get(u["jp"]) or (g if g != "_" else "")
                        tags = " ".join(x for x in [("EX" if "（EX）" in u["jp"] else "UR") if lid == "strongest" else "",
                                                    "" if g != "_" else role] if x)
                    rec = {"n": en, "t": tags, "i": u["i"]}
                    if lid == "strongest":
                        b = (ser["banner"].get(u["i"]) or ser["banner"].get("_key:" + u["i"])
                             or ser["banner"].get("_unit:" + u["jp"]))
                        if b:
                            rec["b"] = b
                    row.append(rec)
                out[g][k] = row
        if out != old_groups:
            strip = lambda gs: {g: {k: [(u["n"], u["t"]) for u in v] for k, v in t.items()} for g, t in gs.items()}
            moved = strip(out) != strip(old_groups)
            new_lists[lid] = (out, added, moved)
            if moved:
                changes.append(lid)

    # Strongest units by series and by tag: one row each, units in Game8's order,
    # plus each series/tag page's own tier list (opened by clicking the row).
    row_lists = {}
    for rlid, rows in ser["rows"].items():
        if rlid not in lists:
            continue
        added = []
        known = {u["i"]: u for r in lists[rlid]["rows"]
                 for u in r["units"] + [x for v in (r.get("tiers") or {}).values() for x in v]}

        def resolve(u, label, flt=""):
            jp = u["jp"]
            if u["i"] in known:
                return known[u["i"]]
            fr = flt.split()
            role = (roles.get(jp) or roles.get(jp + "画像") or next((ROLE[x] for x in fr if x in ROLE), "")
                    or next((v for k, v in ROLE.items() if k in jp), ""))
            en = by_key.get(u["i"]) or names.get(jp) or names.get(jp + "画像") or from_soshage(jp + "画像", rlid, role)
            if not en:
                unknown.append((rlid, "_", label, u))
                return None
            names.setdefault(jp + "画像", en)
            rar = ("EX" if "（EX）" in jp else next((x for x in ("UR", "SSR", "SR") if x in fr), "")
                   or next((x for x in ("SSR", "SR") if re.search(rf"[（／/]{x}[）／/]", jp)), ""))
            added.append(en)
            known[u["i"]] = {"n": en, "t": " ".join(x for x in (rar, role) if x), "i": u["i"]}
            return known[u["i"]]

        out = []
        for r in rows:
            row = [x for x in (resolve(u, r["label"]) for u in r["units"]) if x]
            tiers = {k: [x for x in (resolve(u, f"{r['label']} {k}", u.get("f", "")) for u in v) if x]
                     for k, v in (r.get("tiers") or {}).items()}
            out.append({"s": r["s"], "label": r["label"], "logo": r["logo"], "page": r["page"],
                        "units": row, "tiers": tiers})
        row_lists[rlid] = (out, added)

    # Series per English unit name; existing entries (including hand-filled ones) are kept.
    series_path = ROOT / "data/series.json"
    series = json.loads(series_path.read_text()) if series_path.exists() else {"units": {}, "icons": {}}
    jp_of = {}
    for jp, en in names.items():
        jp_of.setdefault(en, []).append(re.sub(r"画像$", "", jp).strip())
    no_series = []
    for lid, groups in game8.items():
        for g in groups.values():
            for v in g.values():
                for u in v:
                    en = names.get(u["jp"]) or by_key.get(u["i"])
                    if not en or en in series["units"]:
                        continue
                    found = ser["key"].get(u["i"]) or next(
                        (ser["title"][j] for j in [re.sub(r"画像$", "", u["jp"]).strip()] + jp_of.get(en, [])
                         if j in ser["title"]), None)
                    if found:
                        series["units"][en] = found
                    elif en not in no_series:
                        no_series.append(en)
    series["icons"].update(ser["icon"])

    report = []
    if unknown:
        report.append("## Units that need an English name\n")
        report.append("Add each one to `data/names.json` as `\"Japanese name\": \"Official English name\"`, then push. "
                      "The site is not updated until every unit has a name.\n")
        seen = set()
        for lid, g, k, u in unknown:
            if u["jp"] in seen:
                continue
            seen.add(u["jp"])
            hint = f" (closest soshage name: {guess[u['jp']]})" if u["jp"] in guess else ""
            report.append(f"- `{u['jp']}` ({lid}{'' if g == '_' else ' ' + g}, tier {k}, role {roles.get(u['jp'], '?')}) "
                          f"https://img.game8.jp/{u['i']}/show{hint}")
    changed_notes = [pid for pid, t in notes.items() if state["notes"].get(pid) not in (None, hashlib.sha1(t.encode()).hexdigest())]
    if changed_notes:
        report.append("\n## Game8 commentary changed (the site's \"Latest notes\" may need a new translation)\n")
        for pid in changed_notes:
            report.append(f"### {BASE}{pid}\n\n```\n{notes[pid]}\n```\n")

    if auto:
        print("named from soshage:", ", ".join(f"{jp} = {en}" for jp, en in auto.items()))

    if no_series:
        report.append("\n## Units with no series on Game8 yet\n")
        report.append("Add each to `data/series.json` under `units` as `\"English name\": [\"Game8 series name\"]`. "
                      "They show without a series icon until then.\n")
        report.extend(f"- {en}" for en in no_series)

    if unknown:
        pathlib.Path(args.report).write_text("\n".join(report) + "\n")
        print(f"{len(unknown)} unit(s) need translation; site.json left unchanged")
        return 2

    for rlid, (rows, added) in row_lists.items():
        l = lists[rlid]
        strip = lambda rows: [(r["s"], [u["n"] for u in r["units"]],
                               {k: [u["n"] for u in v] for k, v in (r.get("tiers") or {}).items()}) for r in rows]
        if strip(rows) != strip(l["rows"]):
            changes.append(rlid)
            if dates.get(BY_SERIES):
                l["updated"] = fmt_date(dates[BY_SERIES])
            l["new"] = sorted(set(added))
        l["rows"] = rows
    for lid, (out, added, moved) in new_lists.items():
        l = lists[lid]
        if "groups" in l:
            l["groups"] = out
        else:
            l["tiers"] = out["_"]
        if added:
            l["new"] = added
        present = {u["n"] for g in out.values() for v in g.values() for u in v}
        l["new"] = [n for n in l.get("new", []) if n in present]
        if moved and dates.get(PAGES[lid]):
            l["updated"] = fmt_date(dates[PAGES[lid]])
    site_path.write_text(json.dumps(site, ensure_ascii=False, indent=1) + "\n")
    series_path.write_text(json.dumps(series, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    names_path.write_text(json.dumps(dict(sorted(names.items())), ensure_ascii=False, indent=1) + "\n")
    state = {"dates": dates, "notes": {pid: hashlib.sha1(t.encode()).hexdigest() for pid, t in notes.items()}}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    if report and (unknown or changed_notes):
        pathlib.Path(args.report).write_text("\n".join(report) + "\n")
    print("changed lists:", ", ".join(changes) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
