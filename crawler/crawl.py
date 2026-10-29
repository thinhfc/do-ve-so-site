"""Fetch Vietnamese state lottery results and publish them as static JSON for the Do Ve So app.

Output: api/v1/<region>/<yyyy-MM-dd>.json and api/v1/index.json. Standard library only.
A station is published only when every prize tier has the expected count and digit length,
so a malformed source never reaches the app.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

FEEDS = {
    "south": "https://xskt.com.vn/rss-feed/mien-nam-xsmn.rss",
    "central": "https://xskt.com.vn/rss-feed/mien-trung-xsmt.rss",
    "north": "https://xskt.com.vn/rss-feed/mien-bac-xsmb.rss",
}
KEEP_DAYS = 60
VN_TZ = dt.timezone(dt.timedelta(hours=7))
TIERS = ["db", "g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"]

# (count, digits) per tier.
SHAPE = {
    "south": {"db": (1, 6), "g1": (1, 5), "g2": (1, 5), "g3": (2, 5), "g4": (7, 5),
              "g5": (1, 4), "g6": (3, 4), "g7": (1, 3), "g8": (1, 2)},
    "north": {"db": (1, 5), "g1": (1, 5), "g2": (2, 5), "g3": (6, 5), "g4": (4, 4),
              "g5": (6, 4), "g6": (3, 3), "g7": (4, 2)},
}
SHAPE["central"] = SHAPE["south"]

# Station codes must match DoVeSo/Data/StationSchedule.swift.
STATIONS = {
    "XSHCM": ["TP. Hồ Chí Minh", "TP.HCM", "TP HCM", "Hồ Chí Minh", "HCM", "TPHCM"],
    "XSDT": ["Đồng Tháp"], "XSCM": ["Cà Mau"],
    "XSBTR": ["Bến Tre"], "XSVT": ["Vũng Tàu", "Bà Rịa Vũng Tàu"], "XSBL": ["Bạc Liêu"],
    "XSDN": ["Đồng Nai"], "XSCT": ["Cần Thơ"], "XSST": ["Sóc Trăng"],
    "XSTN": ["Tây Ninh"], "XSAG": ["An Giang"], "XSBTH": ["Bình Thuận"],
    "XSVL": ["Vĩnh Long"], "XSBD": ["Bình Dương"], "XSTV": ["Trà Vinh"],
    "XSLA": ["Long An"], "XSBP": ["Bình Phước"], "XSHG": ["Hậu Giang"],
    "XSTG": ["Tiền Giang"], "XSKG": ["Kiên Giang"], "XSDL": ["Đà Lạt", "Lâm Đồng"],
    "XSTTH": ["Thừa Thiên Huế", "Thừa T. Huế", "Huế", "TT Huế"], "XSPY": ["Phú Yên"],
    "XSDLK": ["Đắk Lắk", "Đắc Lắc", "Daklak", "Đắk Lắc"], "XSQNM": ["Quảng Nam"],
    "XSDNG": ["Đà Nẵng"], "XSKH": ["Khánh Hòa", "Khánh Hoà"],
    "XSBDI": ["Bình Định"], "XSQT": ["Quảng Trị"], "XSQB": ["Quảng Bình"],
    "XSGL": ["Gia Lai"], "XSNT": ["Ninh Thuận"],
    "XSQNG": ["Quảng Ngãi"], "XSDNO": ["Đắk Nông", "Đắc Nông", "Daknong"], "XSKT": ["Kon Tum"],
}
CANONICAL = {code: names[0] for code, names in STATIONS.items()}


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]", "", text)


ALIASES = {normalize(alias): code for code, names in STATIONS.items() for alias in names}


def station_for(name: str) -> tuple[str, str] | None:
    code = ALIASES.get(normalize(name))
    return (code, CANONICAL[code]) if code else None


LABEL = re.compile(r"(ĐB|[1-8]):\s*")


def parse_block(text: str) -> dict[str, list[str]]:
    """'ĐB: 111082 1: 37166 ... 7: 1078: 96' → {'db': [...], ...}. G7/G8 may be glued together."""
    marks = list(LABEL.finditer(text))
    prizes: dict[str, list[str]] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        tier = "db" if m.group(1) == "ĐB" else f"g{m.group(1)}"
        prizes[tier] = re.findall(r"\d+", text[m.end():end])
    return prizes


def valid(prizes: dict[str, list[str]], region: str) -> bool:
    shape = SHAPE[region]
    if set(prizes) != set(shape):
        return False
    return all(len(nums) == count and all(len(n) == digits for n in nums)
               for tier, (count, digits) in shape.items() for nums in [prizes[tier]])


def item_date(link: str, title: str) -> dt.date | None:
    m = re.search(r"ngay-(\d{1,2})-(\d{1,2})-(\d{4})", link)
    if m:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{1,2})/(\d{1,2})", title)
    if not m:
        return None
    today = dt.datetime.now(VN_TZ).date()
    guess = dt.date(today.year, int(m.group(2)), int(m.group(1)))
    return guess if guess <= today else guess.replace(year=today.year - 1)


def parse_feed(xml_text: str, region: str) -> dict[dt.date, list[dict]]:
    days: dict[dt.date, list[dict]] = {}
    for item in ET.fromstring(xml_text).iter("item"):
        day = item_date(item.findtext("link", ""), item.findtext("title", ""))
        desc = item.findtext("description", "")
        if day is None:
            continue
        blocks = [("Miền Bắc", desc)] if region == "north" else re.findall(r"\[([^\]]+)\]([^\[]*)", desc)
        results = []
        for name, body in blocks:
            prizes = parse_block(body)
            if not valid(prizes, region):
                print(f"skip {region} {day} {name.strip()}: unexpected prize shape", file=sys.stderr)
                continue
            if region == "north":
                code, display = "XSMB", "Miền Bắc"
            else:
                found = station_for(name.strip())
                if found is None:
                    print(f"skip {region} {day} {name.strip()}: unknown station", file=sys.stderr)
                    continue
                code, display = found
            results.append({"code": code, "name": display,
                            "prizes": [{"tier": t, "numbers": prizes[t]} for t in TIERS if t in prizes]})
        if results:
            days[day] = results
    return days


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "DoVeSo-results/1.0 (+https://thinhfc.github.io/do-ve-so-site/)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def write_json(path: Path, payload: dict) -> bool:
    """Write only when the content changed (ignoring updatedAt), so unchanged runs make no commit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = json.loads(path.read_text())
        if {k: v for k, v in old.items() if k != "updatedAt"} == {k: v for k, v in payload.items() if k != "updatedAt"}:
            return False
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return True


def main(root: Path) -> int:
    api = root / "api" / "v1"
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    failures = 0
    for region, url in FEEDS.items():
        try:
            days = parse_feed(fetch(url), region)
        except Exception as error:  # one broken feed must not stop the others
            print(f"feed {region} failed: {error}", file=sys.stderr)
            failures += 1
            continue
        for day, results in days.items():
            if write_json(api / region / f"{day.isoformat()}.json",
                          {"date": day.isoformat(), "region": region, "updatedAt": now, "results": results}):
                print(f"updated {region} {day}")
    cutoff = dt.datetime.now(VN_TZ).date() - dt.timedelta(days=KEEP_DAYS)
    for file in api.glob("*/*.json"):
        if dt.date.fromisoformat(file.stem) < cutoff:
            file.unlink()
    index = {region: sorted((f.stem for f in (api / region).glob("*.json")), reverse=True)
             for region in FEEDS if (api / region).exists()}
    write_json(api / "index.json", {"updatedAt": now, "days": index})
    return 1 if failures == len(FEEDS) else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
