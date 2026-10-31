"""Group Game8's Japanese series names into English series families for the filter."""
import re

# (pattern, English family). A Game8 series can match more than one family; first matches win order.
RULES = [
    (r"GQuuuuuuX", "GQuuuuuuX"),
    (r"^SD|SD戦国伝|SDガンダム|SDコマンド|ラクロアン|三国", "SD Gundam"),
    (r"G ?GENERATION", "G Generation originals"),
    (r"0083", "Gundam 0083: Stardust Memory"),
    (r"サンダーボルト", "Gundam Thunderbolt"),
    (r"閃光のハサウェイ", "Hathaway's Flash"),
    (r"逆襲のシャア|CCA-MSV", "Char's Counterattack"),
    (r"ガンダムNT", "Gundam Narrative"),
    (r"ガンダムUC|UC-MSV", "Gundam Unicorn"),
    (r"ZZ|SENTINEL|ヴァルプルギス|BATTLE MASTER", "Gundam ZZ"),
    (r"Zガンダム|ADVANCE OF Z|Z-MSV|M-MSV|グリーンダイバーズ|エコール|GUNDAM EVOLVE", "Zeta Gundam"),
    (r"F90|F91|フォーミュラー|クロスボーン", "Gundam F90 / F91 / Crossbone"),
    (r"Vガンダム", "Victory Gundam"),
    (r"Gガンダム", "G Gundam"),
    (r"ガンダムW", "Gundam Wing"),
    (r"ガンダムX", "Gundam X"),
    (r"∀", "Turn A Gundam"),
    (r"SEED DESTINY|STARGAZER|天空の皇女", "Gundam SEED Destiny"),
    (r"SEED", "Gundam SEED"),
    (r"ガンダム00", "Gundam 00"),
    (r"AGE", "Gundam AGE"),
    (r"鉄血", "Iron-Blooded Orphans"),
    (r"水星の魔女", "The Witch from Mercury"),
    (r"レコンギスタ", "Reconguista in G"),
    (r"^機動戦士ガンダム$|THE ORIGIN|MSV|MS-X|IGLOO|第08MS小隊|BLUE DESTINY|ポケットの中|CROSS DIMENSION|"
     r"ミッシングリンク|ギレン|BATTLEFIELD RECORD|Lost War|ファントム|カタナ|ダブルフェイク|コロニーの落ちた地で",
     "Mobile Suit Gundam (One Year War)"),
    (r"ビルド|ガンプラ|プラモ|EXA", "Gunpla & other"),
]
ORDER = [f for _, f in RULES]


def families(series_list):
    out = []
    for s in series_list:
        s = s.strip()
        for pat, fam in RULES:
            if re.search(pat, s):
                if fam not in out:
                    out.append(fam)
                break
    return out
