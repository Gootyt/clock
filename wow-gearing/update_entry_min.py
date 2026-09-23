#!/usr/bin/env python3
"""A WoW Gearing Ajánló HTML-ben frissíti az entryMin értékeket a 25. percentilis alapján.

Források:
  live.csv  – Mythic+ kulcsszintenként (vesszővel tagolt):
              mythic_level, p25_item_level  →  "Mythic+ <szint>" sorok
  stat.csv  – raidbossonként (pontosvesszővel tagolt, tizedesvesszős):
              Nehézség, Boss, 25. percentilis  →  "Raid - <Boss> <Nehézség>" sorok

Ahol nincs adat (a CSV-ben nem szereplő szint, még meg nem ölt boss üres
percentilissel, "Összes boss" összesítő), ott az entryMin változatlan marad.
A HTML-ben csak az entryMin utáni szám cserélődik, minden más bájtra ugyanaz marad.

Használat:
  python update_entry_min.py              # a szkript mappájában lévő fájlokat frissíti
  python update_entry_min.py --dry-run    # csak kiírja, mi változna
  python update_entry_min.py --html be.html --output ki.html --live live.csv --stat stat.csv
"""
import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Egy GROUPS-sor eleje: { name: "...", entryMin: <szám>
ROW_RE = re.compile(
    r'(?P<prefix>\{\s*name:\s*"(?P<name>[^"]*)",\s*entryMin:\s*)(?P<value>\d+(?:\.\d+)?)'
)
# Ezekhez a sorokhoz várunk adatot a CSV-kből
SCOPE_PREFIXES = ("Mythic+ ", "Raid - ")
TOTAL_ROW = "Összes boss"


def parse_number(text):
    """'301,8' vagy '301.8' → 301.8; üres mező → None."""
    text = text.strip().replace(",", ".")
    return float(text) if text else None


def format_ilvl(value):
    """Legfeljebb 2 tizedes, felesleges nullák nélkül: 276.0 → '276', 303.2 → '303.2'."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def read_csv(path, delimiter, required):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        missing = [col for col in required if col not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"Hiba: {path} – hiányzó oszlop(ok): {', '.join(missing)}")
        return list(reader)


def load_mplus(path):
    """live.csv → {"Mythic+ 2": 276.0, ...}"""
    targets = {}
    for row in read_csv(path, ",", ["mythic_level", "p25_item_level"]):
        level = row["mythic_level"].strip()
        if level:
            targets[f"Mythic+ {level}"] = parse_number(row["p25_item_level"])
    return targets


def load_raid(path):
    """stat.csv → {"Raid - Sszorak Heroic": 315.9, ...} (az összesítő sor nélkül)"""
    targets = {}
    for row in read_csv(path, ";", ["Nehézség", "Boss", "25. percentilis"]):
        boss = row["Boss"].strip()
        difficulty = row["Nehézség"].strip()
        if boss and difficulty and boss != TOTAL_ROW:
            targets[f"Raid - {boss} {difficulty}"] = parse_number(row["25. percentilis"])
    return targets


def update_html(html, targets):
    """Visszaadja az új HTML-t és a sorok besorolását (changed / unchanged / no_data)."""
    changed, unchanged, no_data = [], [], []
    seen = set()

    def replace(match):
        name, old_text = match["name"], match["value"]
        seen.add(name)
        new_value = targets.get(name)
        if new_value is None:
            if name.startswith(SCOPE_PREFIXES):
                no_data.append((name, old_text))
            return match[0]
        new_text = format_ilvl(new_value)
        if float(old_text) == float(new_text):
            unchanged.append(name)
            return match[0]
        changed.append((name, old_text, new_text))
        return match["prefix"] + new_text

    new_html = ROW_RE.sub(replace, html)
    if not seen:
        sys.exit("Hiba: a HTML-ben nem található egyetlen { name: ..., entryMin: ... } sor sem.")

    # CSV-ben van érték, de nincs hozzá sor a HTML-ben (pl. elírt bossnév)
    orphans = sorted(name for name, value in targets.items() if value is not None and name not in seen)
    return new_html, changed, unchanged, no_data, orphans


def main():
    parser = argparse.ArgumentParser(
        description="entryMin frissítése a Mythic+ és raidboss sorokban a 25. percentilis alapján."
    )
    parser.add_argument("--live", type=Path, default=HERE / "live.csv", help="Mythic+ statisztika (live.csv)")
    parser.add_argument("--stat", type=Path, default=HERE / "stat.csv", help="raidboss statisztika (stat.csv)")
    parser.add_argument("--html", type=Path, default=HERE / "wow-gearing-ajanlo-refaktoralt.html",
                        help="a frissítendő HTML")
    parser.add_argument("-o", "--output", type=Path, help="kimeneti fájl (alapértelmezés: a --html felülírása)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="csak kiírja a változásokat, nem ír fájlt")
    args = parser.parse_args()

    targets = {**load_mplus(args.live), **load_raid(args.stat)}

    # newline="" → a sorvégek (LF/CRLF) érintetlenek maradnak
    with open(args.html, encoding="utf-8", newline="") as f:
        html = f.read()

    new_html, changed, unchanged, no_data, orphans = update_html(html, targets)

    width = max((len(name) for name, *_ in changed), default=0)
    print(f"Változott ({len(changed)}):")
    for name, old, new in changed:
        print(f"  {name:<{width}}  {old:>7} → {new}")
    print(f"Már naprakész ({len(unchanged)})")
    if no_data:
        print(f"Nincs adat, változatlan ({len(no_data)}):")
        for name, old in no_data:
            print(f"  {name} (marad: {old})")
    if orphans:
        print(f"Figyelem: ezekhez nincs sor a HTML-ben ({len(orphans)}):")
        for name in orphans:
            print(f"  {name}")

    if args.dry_run:
        print("\n--dry-run: nem történt írás.")
        return

    output = args.output or args.html
    if new_html != html or output != args.html:
        with open(output, "w", encoding="utf-8", newline="") as f:
            f.write(new_html)
    print(f"\nMentve: {output}")


if __name__ == "__main__":
    main()
