"""Match Game8 units to soshage.com's game data, which has the official English names,
thumbnails and series for every unit."""
import difflib
import json
import pathlib
import re
import sys
import unicodedata

API = "https://soshage.com/ggetapi/{lang}/{path}"
IMG = "https://img.kusoge.xyz/ggenet/"
RARITY = {"N": 1, "R": 2, "SR": 3, "SSR": 4, "UR": 5}
ROLE = {"ATK": 1, "DEF": 2, "SUP": 3}


def norm(name):
    """Normalise a Japanese unit name: width, brackets, Game8's rarity/role suffixes and spacing."""
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"画像$", "", s)
    hint = None
    m = re.findall(r"\(([^()]*)\)", s)
    for part in m:
        bits = re.split(r"[/／]", part)
        tagged = [b for b in bits if b in RARITY or b in ("攻撃", "支援", "耐久", "ユニット")]
        if tagged:
            hint = next((RARITY[b] for b in bits if b in RARITY), hint)
            rest = "/".join(b for b in bits if b not in tagged)
            s = s.replace(f"({part})", f"({rest})" if rest else "")
    s = re.sub(r"[［【\[]", "(", s)
    s = re.sub(r"[］】\]]", ")", s)
    s = s.translate(str.maketrans("べぺへぱばびぴぶぷぼぽ", "ベペヘパバビピブプボポ"))
    s = s.replace("ジ・オリジン", "THEORIGIN").replace("THE ORIGIN", "THEORIGIN")
    s = re.sub(r"(装備型|装備|仕様機|専用機|専用|版|機)(?=\))", "", s)
    s = re.sub(r"/?(SSR|UR|SR|EX)(?=\))", lambda m: "" if m.group(1) != "EX" else m.group(0), s)
    s = s.replace("()", "")
    s = s.replace("・", "").replace("=", "").replace(" ", "").replace("ー", "-").replace("―", "-").replace("－", "-")
    s = s.replace("O", "0") if re.search(r"O(ガンダム|\b)", s) else s
    s = s.replace(".", "")
    return s, hint


class Soshage:
    def __init__(self, units_en, units_ja, series_en, series_ja):
        en = {u["id"]: u for u in units_en}
        sja = {s["id"]: s for s in series_ja}
        self.series = []
        for s in series_en:
            if not s.get("name"):
                continue
            self.series.append({"id": s["id"], "en": s["name"].strip(), "ja": (sja.get(s["id"]) or {}).get("name", ""),
                                "logo": s.get("icon"), "sort": s.get("sort", 0)})
        self.series.sort(key=lambda s: s["sort"])
        self.units = []
        self.by_norm = {}
        for u in units_ja:
            e = en.get(u["id"])
            if not e:
                continue
            rec = {"id": u["id"], "en": e["name"].strip(), "ja": u["name"].strip(), "icon": e["icon"],
                   "rarity": e["rarity"], "series": [x["series_id"] for x in e.get("series_set") or []],
                   "role": e.get("role")}
            self.units.append(rec)
            self.by_norm.setdefault(norm(rec["ja"])[0], []).append(rec)

    @classmethod
    def from_cache(cls, path):
        """Load the compact copy kept in data/soshage.json."""
        d = json.load(open(path))
        obj = cls.__new__(cls)
        obj.series, obj.units, obj.by_norm = d["series"], d["units"], {}
        for rec in obj.units:
            obj.by_norm.setdefault(norm(rec["ja"])[0], []).append(rec)
        return obj

    @classmethod
    def from_files(cls, folder):
        load = lambda n: json.load(open(f"{folder}/{n}"))
        return cls(load("unit_en.json"), load("unit_ja.json"), load("series_en.json"), load("series_ja.json"))

    @classmethod
    def fetch(cls):
        """Download the English and Japanese unit and series lists from soshage.com."""
        import requests
        get = lambda lang, path: requests.get(API.format(lang=lang, path=path), timeout=120,
                                              headers={"User-Agent": "gge-tierlist"}).json()
        unit = "unit?order_by=rarity:desc"
        return cls(get("en", unit), get("ja", unit), get("en", "series/v2"), get("ja", "series/v2"))

    def save(self, path):
        d = {"series": self.series, "units": self.units}
        pathlib.Path(path).write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

    def match(self, jp, rarity=None, close=True, role=None):
        """role: 1=ATK, 2=DEF, 3=SUP. Some units exist twice at the same rarity with different roles."""
        key, hint = norm(jp)
        cands = self.by_norm.get(key, [])
        want = rarity or hint
        if len(cands) > 1 and want:
            exact = [c for c in cands if c["rarity"] == want]
            cands = exact or cands
        if len(cands) > 1 and role:
            cands = [c for c in cands if c.get("role") == role] or cands
        if len(cands) > 1:
            cands = sorted(cands, key=lambda c: -c["rarity"])
        if cands:
            return cands[0]
        form = re.sub(r"[(（［\[][^()（）［］\[\]]*形態[)）］\]]", "", jp)
        if form != jp:
            # Game8 lists some transformed forms (MA mode etc.) separately; soshage has the unit once.
            return self.match(form, rarity, close, role)
        if not close:
            return None
        # Game8 and the game spell some names slightly differently; accept a close match.
        for k in difflib.get_close_matches(key, list(self.by_norm), n=3, cutoff=0.88):
            pool = self.by_norm[k]
            if want:
                pool = [c for c in pool if c["rarity"] == want] or pool
            if role:
                pool = [c for c in pool if c.get("role") == role] or pool
            return sorted(pool, key=lambda c: -c["rarity"])[0]
        return None


def thumb(unit):
    return f"{IMG}thumb/thum_{unit['icon']}.webp"


def logo(series):
    return f"{IMG}series/logo_l_{series['logo']}.webp" if series.get("logo") else None


if __name__ == "__main__":
    # Refresh data/soshage.json. A failed download keeps the old copy, so the daily update still runs.
    out = pathlib.Path(__file__).resolve().parent.parent / "data/soshage.json"
    try:
        S = Soshage.fetch()
    except Exception as e:
        print("soshage download failed, keeping the old copy:", e)
        sys.exit(0)
    if len(S.units) < 1000 or len(S.series) < 50:
        print(f"soshage returned only {len(S.units)} units and {len(S.series)} series, keeping the old copy")
        sys.exit(0)
    S.save(out)
    print(f"soshage: {len(S.units)} units, {len(S.series)} series")
