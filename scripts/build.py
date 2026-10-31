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


def page(template="template.html"):
    data = json.loads((ROOT / "data/site.json").read_text())
    series_meta(data)
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
