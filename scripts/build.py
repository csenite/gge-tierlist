"""Build index.html (GitHub Pages) and the bare artifact page from template.html + data/site.json."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="referrer" content="no-referrer">\n')


def page():
    data = json.loads((ROOT / "data/site.json").read_text())
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = (ROOT / "template.html").read_text()
    assert tpl.count("/*DATA*/") == 1
    return tpl.replace("/*DATA*/", blob)


def main():
    s = page()
    (ROOT / "artifact.html").write_text(s)
    i = s.index("</style>") + len("</style>")
    (ROOT / "index.html").write_text(
        HEAD + s[:i]
        + "\n<style>body{margin:0;font-size:14px}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
        + s[i:] + "\n</body>\n</html>\n")


if __name__ == "__main__":
    main()
