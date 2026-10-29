import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crawler"))
import crawl  # noqa: E402

SOUTH = """<rss><channel><item>
<title>KẾT QUẢ XỔ SỐ MIỀN NAM NGÀY 29/10 (Thứ Năm)</title>
<description>
[Tây Ninh]
ĐB: 375284
1: 26571
2: 10417
3: 49657 - 19614
4: 67466 - 13899 - 69424 - 37310 - 02825 - 28924 - 19895
5: 1293
6: 0969 - 9301 - 9684
7: 0098: 15
[Nơi Lạ]
ĐB: 1
</description>
<link>https://xskt.com.vn/xsmn/ngay-29-10-2026</link>
</item></channel></rss>"""

NORTH = """<rss><channel><item>
<title>KẾT QUẢ XỔ SỐ MIỀN BẮC NGÀY 29/10 (Thứ Năm)</title>
<description>
ĐB: 53401
1: 47745
2: 62988 - 46737
3: 48305 - 12492 - 78217 - 29106 - 90525 - 25381
4: 4352 - 7734 - 0900 - 2827
5: 1885 - 3123 - 3284 - 2452 - 7149 - 6951
6: 759 - 626 - 969
7: 96 - 49 - 18 - 55</description>
<link>https://xskt.com.vn/xsmb/ngay-29-10-2026</link>
</item></channel></rss>"""


class CrawlTests(unittest.TestCase):
    def test_south_splits_glued_g7_g8_and_maps_station(self):
        days = crawl.parse_feed(SOUTH, "south")
        (day, results), = days.items()
        self.assertEqual(day.isoformat(), "2026-10-29")
        self.assertEqual(len(results), 1)  # malformed unknown station skipped
        station = results[0]
        self.assertEqual((station["code"], station["name"]), ("XSTN", "Tây Ninh"))
        prizes = {p["tier"]: p["numbers"] for p in station["prizes"]}
        self.assertEqual(prizes["g7"], ["009"])
        self.assertEqual(prizes["g8"], ["15"])
        self.assertEqual(prizes["db"], ["375284"])

    def test_north_shape(self):
        (results,) = crawl.parse_feed(NORTH, "north").values()
        prizes = {p["tier"]: p["numbers"] for p in results[0]["prizes"]}
        self.assertEqual(results[0]["code"], "XSMB")
        self.assertNotIn("g8", prizes)
        self.assertEqual(len(prizes["g7"]), 4)

    def test_aliases(self):
        self.assertEqual(crawl.station_for("Thừa T. Huế")[0], "XSTTH")
        self.assertEqual(crawl.station_for("TP. HCM")[0], "XSHCM")
        self.assertIsNone(crawl.station_for("Hà Nội"))


if __name__ == "__main__":
    unittest.main()
