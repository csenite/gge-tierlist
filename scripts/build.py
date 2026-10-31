"""Build index.html (GitHub Pages) and the bare artifact page from template.html + data/site.json."""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from series_rules import ORDER, families  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="referrer" content="no-referrer">\n')


def _norm(s):
    return re.sub(r"（[^（）]*）|\s", "", s).upper()


def find_icon(icons, name):
    """Game8 spells some series differently in the unit data and the series list; match loosely."""
    if name in icons:
        return icons[name]
    n = _norm(name)
    norm = {_norm(k): v for k, v in icons.items()}
    if n in norm:
        return norm[n]
    best = max((k for k in norm if k and n.startswith(k)), key=len, default=None)
    return norm[best] if best else None


def series_meta(data):
    """English series families and a Game8 series icon for every unit on the site."""
    path = ROOT / "data/series.json"
    if not path.exists():
        return
    series = json.loads(path.read_text())
    names = {u["n"] for l in data["lists"]
             for g in (l["groups"].values() if "groups" in l else [l["tiers"]])
             for v in g.values() for u in v}
    ser, used = {}, set()
    for n in sorted(names):
        jp = series["units"].get(n, [])
        fams = families(jp)
        icons = []
        for s in jp:
            i = find_icon(series["icons"], s)
            if i and i not in [x[0] for x in icons]:
                icons.append([i, (families([s]) or [s])[0]])
        if fams:
            ser[n] = {"f": fams, "i": icons[0][0] if icons else None, "is": icons}
            used.update(fams)
    data["ser"] = ser
    data["fams"] = [f for f in ORDER if f in used]


def soshage_meta(data):
    """Official English names, thumbnails and series logos from soshage.com, keyed by the site's unit name.

    A unit gets the same soshage match on every tab; EX versions stay separate from their SSR versions.
    """
    path = ROOT / "data/soshage.json"
    if not path.exists():
        return
    from soshage import Soshage, thumb, logo, RARITY
    S = Soshage.from_cache(path)
    series = {s["id"]: s for s in S.series}
    names = json.loads((ROOT / "data/names.json").read_text())
    jp_of = {}
    for jp, en in names.items():
        jp_of.setdefault(en, []).append(jp)
    sos, used, missing, done = {}, set(), [], {}
    gpath = ROOT / "data/series.json"
    gseries = json.loads(gpath.read_text())["units"] if gpath.exists() else {}
    by_ja = {_norm(s["ja"]): s for s in S.series if s.get("ja")}
    for l in data["lists"]:
        for g in (l["groups"].values() if "groups" in l else [l["tiers"]]):
            for v in g.values():
                for u in v:
                    tags = u["t"].split()
                    ex = "EX" in tags or (l["id"] == "strongest" and "UR" not in tags)
                    key = u["n"] + ("|EX" if ex else "")
                    u["k"] = key
                    if key in done:
                        continue
                    want = 5 if ex or "UR" in tags else next((RARITY[t] for t in tags if t in RARITY), None)
                    cands = sorted(jp_of.get(u["n"], []), key=lambda j: ("EX" in j) != ex)
                    m = next((m for m in (S.match(j, want) for j in cands) if m), None)
                    if m and ex and not m["en"].endswith("(EX)"):
                        m = next((x for x in (S.match(re.sub(r"画像$", "", j) + "（EX）", 5) for j in cands) if x), m)
                    if m and not ex and m["en"].endswith("(EX)"):
                        m = next((x for x in (S.match(j, want or 4) for j in cands) if x and not x["en"].endswith("(EX)")), m)
                    done[key] = True
                    if not m:
                        # Not on soshage yet: keep Game8's picture and use Game8's series, matched by Japanese name.
                        jp_series = gseries.get(u["n"], [])
                        ss = [by_ja[_norm(j)] for j in jp_series if _norm(j) in by_ja]
                        missing.append(u["n"])
                        if ss:
                            used.update(s["id"] for s in ss)
                            sos[key] = {"n": u["n"], "th": f"https://img.game8.jp/{u['i']}/show",
                                        "s": [[s["en"], logo(s)] for s in ss]}
                        continue
                    ss = [series[i] for i in m["series"] if i in series]
                    if not ss:
                        missing.append(u["n"])
                    used.update(s["id"] for s in ss)
                    sos[key] = {"n": re.sub(r"\s*\(EX\)$", "", m["en"]), "th": thumb(m),
                                "s": [[s["en"], logo(s)] for s in ss]}
    data["sos"] = sos
    data["sosSeries"] = sorted({series[i]["en"] for i in used}, key=lambda x: x.casefold())
    data["sosMissing"] = missing


def page(template="template.html"):
    data = json.loads((ROOT / "data/site.json").read_text())
    series_meta(data)
    if template != "template.html":
        soshage_meta(data)
        if data.get("sosMissing"):
            print("no soshage match:", ", ".join(sorted(set(data["sosMissing"]))))
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = (ROOT / template).read_text()
    assert tpl.count("/*DATA*/") == 1
    return tpl.replace("/*DATA*/", blob)


def full_doc(s):
    i = s.index("</style>") + len("</style>")
    return (HEAD + s[:i]
            + "\n<style>body{margin:0;font-size:14px}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
            + s[i:] + "\n</body>\n</html>\n")


def main():
    s = page()
    (ROOT / "artifact.html").write_text(s)
    (ROOT / "index.html").write_text(full_doc(s))
    if (ROOT / "template-preview.html").exists():
        (ROOT / "preview.html").write_text(full_doc(page("template-preview.html")))


if __name__ == "__main__":
    main()
