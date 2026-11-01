import json
import tempfile
import unittest
from pathlib import Path

from shop.engine import BLOCKED, NOT_FETCHED, execute, ingest
from shop.models import Offer, Response
from shop.numbers import parse_count, parse_de_number, parse_eur
from shop.parsers import parse_amazon, parse_geizhals, parse_idealo, parse_mydealz
from shop.queries import expand_queries
from shop.relevance import classify
from shop.score import rank_offers

FIXTURES = Path(__file__).parent / "fixtures"


class NumbersTest(unittest.TestCase):
    def test_german_numbers(self):
        self.assertEqual(parse_de_number("4,2"), 4.2)
        self.assertEqual(parse_de_number("8.285"), 8285)
        self.assertEqual(parse_count("1.639"), 1639)
        self.assertEqual(parse_eur("207,04\xa0€"), 207.04)
        self.assertEqual(parse_eur("ab € 191,91"), 191.91)


class QueryTest(unittest.TestCase):
    def test_model_code_variants(self):
        queries = expand_queries("Sony WH-1000XM5", limit=6)
        folded = [query.casefold() for query in queries]
        self.assertIn("sony wh-1000xm5", folded)
        self.assertIn("sony wh1000xm5", folded)
        self.assertIn("wh-1000xm5", folded)

    def test_german_wording(self):
        queries = expand_queries("wireless headphones", limit=6)
        self.assertTrue(any("kopfhörer" in query.casefold() for query in queries))

    def test_extra_queries_are_kept(self):
        queries = expand_queries("XM5", ["Sony WH-1000XM5 Kopfhörer"], limit=6)
        self.assertEqual(queries[1], "Sony WH-1000XM5 Kopfhörer")


class ParseTest(unittest.TestCase):
    def test_amazon_fixture(self):
        html = (FIXTURES / "amazon_card.html").read_text(encoding="utf-8")
        offers = parse_amazon(html, "Sony WH-1000XM5", 1)
        self.assertGreaterEqual(len(offers), 1)
        offer = next(item for item in offers if item.external_id == "B09Y2MYL5C")
        self.assertAlmostEqual(offer.price_eur, 207.04)
        self.assertAlmostEqual(offer.rating, 4.2)
        self.assertEqual(offer.votes, 8285)
        self.assertFalse(offer.sponsored)
        self.assertEqual(offer.url, "https://www.amazon.de/dp/B09Y2MYL5C")

    def test_amazon_sponsored_card(self):
        html = """
        <div data-asin="B0SPONSOR1" data-component-type="s-search-result" data-csa-c-pos="4">
          <h2><span>Sony WH-1000XM5 Testprodukt</span></h2>
          <span class="a-offscreen">99,00 €</span>
          <span class="a-icon-alt">4,4 von 5 Sternen</span>
          <a aria-label="4.242 Bewertungen" class="s-underline-text">(4242)</a>
          <span class="s-sponsored-label-text">Gesponsert</span>
        </div>
        """
        offer = parse_amazon(html, "Sony WH-1000XM5", 2)[0]
        self.assertTrue(offer.sponsored)
        self.assertEqual(offer.votes, 4242)
        self.assertEqual(offer.rank, 4)
        self.assertEqual(offer.page, 2)

    def test_mydealz_fixture(self):
        html = (FIXTURES / "mydealz_thread.json").read_text(encoding="utf-8")
        offer = parse_mydealz(html, "Sony WH-1000XM5", 1)[0]
        self.assertAlmostEqual(offer.price_eur, 180.01)
        self.assertEqual(offer.extra["merchant"], "AliExpress")
        self.assertAlmostEqual(offer.extra["heat"], 338.63)
        self.assertFalse(offer.expired)
        self.assertIn("2862437", offer.url)

    def test_geizhals_text(self):
        text = (FIXTURES / "geizhals.md").read_text(encoding="utf-8")
        offers = parse_geizhals(text, "Sony WH-1000XM5", 1, "https://geizhals.de/?fs=test")
        self.assertEqual(offers[0].title, "Sony WH-1000XM5")
        self.assertAlmostEqual(offers[0].price_eur, 191.91)
        self.assertAlmostEqual(offers[0].rating, 4.6)
        self.assertEqual(offers[0].votes, 196)
        self.assertEqual(offers[0].extra["offer_count"], 90)
        self.assertEqual(offers[1].title, "Sony WH-1000XM5SA Black")
        self.assertIsNone(offers[1].rating)
        self.assertEqual(offers[2].title, "Geekria Shield Headphones Case für Sony")

    def test_idealo_text(self):
        text = (FIXTURES / "idealo.md").read_text(encoding="utf-8")
        offers = parse_idealo(text, "Sony WH-1000XM5", 1, "https://www.idealo.de/test")
        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0].title, "Sony WH-1000XM5")
        self.assertAlmostEqual(offers[0].rating, 1.4)
        self.assertEqual(offers[0].rating_scale, "grade6")
        self.assertEqual(offers[0].votes, 1639)
        self.assertAlmostEqual(offers[0].price_eur, 194.99)
        self.assertEqual(offers[0].extra["offer_count"], 130)
        self.assertEqual(offers[1].title, "Sony WF-1000XM5 Black")


class RelevanceAndScoreTest(unittest.TestCase):
    def test_filters(self):
        self.assertEqual(classify("Sony WH-1000XM5", "Sony WH-1000XM5 Black")[0], True)
        self.assertEqual(classify("Sony WH-1000XM5", "Sony WF-1000XM5")[1], "different-model")
        self.assertEqual(classify("Sony WH-1000XM5", "Ohrpolster für Sony WH-1000XM5")[1], "accessory")
        self.assertEqual(classify("Sony WH-1000XM5", "Sony WH-1000XM5 refurbished")[1], "used")
        self.assertEqual(classify("Sony WH-1000XM5", "2x Sony WH-1000XM5")[1], "bundle")

    def test_best_value_uses_price_and_review_volume(self):
        offers = [
            Offer(
                source="amazon",
                query="Sony WH-1000XM5",
                page=1,
                rank=1,
                title="Sony WH-1000XM5 Black",
                url="https://www.amazon.de/dp/B09Y2MYL5C",
                price_eur=207.04,
                rating=4.2,
                rating_scale="stars5",
                votes=8285,
                external_id="B09Y2MYL5C",
            ),
            Offer(
                source="amazon",
                query="Sony WH-1000XM5",
                page=1,
                rank=2,
                title="Sony WH-1000XM5 Mystery",
                url="https://www.amazon.de/dp/B000000000",
                price_eur=99.00,
                rating=5.0,
                rating_scale="stars5",
                votes=2,
                external_id="B000000000",
            ),
            Offer(
                source="mydealz",
                query="Sony WH-1000XM5",
                page=1,
                rank=1,
                title="Sony WH-1000XM5 Over-Ear",
                url="https://www.mydealz.de/deals/sony-wh-1000xm5-1",
                price_eur=180.01,
                external_id="1",
                extra={"heat": 338, "merchant": "AliExpress", "next_best_price": 207.04},
            ),
            Offer(
                source="geizhals",
                query="Sony WH-1000XM5",
                page=1,
                rank=3,
                title="Case für Sony WH-1000XM5",
                url="https://geizhals.de/case",
                price_eur=16.16,
                external_id="case",
            ),
            Offer(
                source="amazon",
                query="Sony WH-1000XM5",
                page=1,
                rank=5,
                title="Sony WH-1000XM6",
                url="https://www.amazon.de/dp/B0F2TT8Q7M",
                price_eur=347.00,
                rating=4.3,
                rating_scale="stars5",
                votes=1960,
                external_id="B0F2TT8Q7M",
            ),
        ]
        ranking = rank_offers("Sony WH-1000XM5", offers)
        self.assertEqual(ranking.winner.offer.source, "mydealz")
        self.assertAlmostEqual(ranking.winner.offer.price_eur, 180.01)
        self.assertEqual(ranking.winner.evidence_source, "amazon")
        self.assertEqual(ranking.winner.votes_used, 8285)
        self.assertEqual(ranking.winner.index, 100)
        reasons = {row.offer.external_id: row.reason for row in ranking.rows}
        self.assertEqual(reasons["case"], "accessory")
        self.assertEqual(reasons["B0F2TT8Q7M"], "different-model")
        # Five stars from two votes must not beat a heavily reviewed listing at a fair price.
        thin = next(row for row in ranking.rows if row.offer.external_id == "B000000000")
        reviewed = next(row for row in ranking.rows if row.offer.external_id == "B09Y2MYL5C")
        self.assertLess(thin.index, reviewed.index)

    def test_same_price_prefers_the_higher_rating_once_both_are_well_reviewed(self):
        offers = [
            Offer(
                source="amazon",
                query="Sony WH-1000XM5",
                page=1,
                rank=1,
                title="Sony WH-1000XM5 Black",
                url="https://www.amazon.de/dp/B09Y2MYL5C",
                price_eur=200,
                rating=4.2,
                rating_scale="stars5",
                votes=8000,
                external_id="more-votes",
            ),
            Offer(
                source="amazon",
                query="Sony WH-1000XM5",
                page=1,
                rank=2,
                title="Sony WH-1000XM5 Silver",
                url="https://www.amazon.de/dp/B09Y2LL45F",
                price_eur=200,
                rating=4.4,
                rating_scale="stars5",
                votes=2000,
                external_id="higher-stars",
            ),
        ]
        ranking = rank_offers("Sony WH-1000XM5", offers)
        self.assertEqual(ranking.winner.offer.external_id, "higher-stars")

    def test_idealo_grade_can_support_a_cheaper_listing(self):
        offers = [
            Offer(
                source="idealo",
                query="kettle",
                page=1,
                rank=1,
                title="Bosch kettle",
                url="https://www.idealo.de/a",
                price_eur=40,
                rating=1.4,
                rating_scale="grade6",
                votes=800,
                external_id="a",
            ),
            Offer(
                source="idealo",
                query="kettle",
                page=1,
                rank=2,
                title="Bosch kettle steel",
                url="https://www.idealo.de/b",
                price_eur=70,
                rating=1.3,
                rating_scale="grade6",
                votes=900,
                external_id="b",
            ),
        ]
        ranking = rank_offers("kettle", offers)
        self.assertEqual(ranking.winner.offer.external_id, "a")


class EngineTest(unittest.TestCase):
    def test_three_pages_stop_on_a_repeat_and_record_blocks(self):
        page_one = """
        <div data-asin="B09Y2MYL5C" data-component-type="s-search-result">
          <h2><span>Sony WH-1000XM5 Black</span></h2>
          <span class="a-offscreen">207,04 €</span>
          <span class="a-icon-alt">4,2 von 5 Sternen</span>
          <a aria-label="8.285 Bewertungen"></a>
        </div>
        """
        page_two = """
        <div data-asin="B09Y2LL45F" data-component-type="s-search-result">
          <h2><span>Sony WH-1000XM5 Silver</span></h2>
          <span class="a-offscreen">199,00 €</span>
          <span class="a-icon-alt">4,4 von 5 Sternen</span>
          <a aria-label="2.335 Bewertungen"></a>
        </div>
        """
        page_three = page_two
        urls = {}

        def amazon(page, body):
            urls[f"https://www.amazon.de/s?k=Sony+WH-1000XM5&page={page}&language=de_DE"] = Response(200, "", body)

        amazon(1, page_one)
        amazon(2, page_two)
        amazon(3, page_three)
        urls["https://geizhals.de/?fs=Sony+WH-1000XM5&hloc=de"] = Response(
            403, "", "Sichere Verbindung wird überprüft"
        )

        class Client:
            def __init__(self):
                self.calls = []

            def get(self, url):
                self.calls.append(url)
                return urls[url]

        client = Client()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "run"
            run = execute(
                "Sony WH-1000XM5",
                ["Sony WH-1000XM5"],
                pages=3,
                sources=["amazon", "geizhals"],
                client=client,
                directory=directory,
            )
            self.assertEqual({offer.external_id for offer in run.offers}, {"B09Y2MYL5C", "B09Y2LL45F"})
            statuses = {(item["source"], item["page"], item["status"]) for item in run.fetches}
            self.assertIn(("amazon", 3, "duplicate-page"), statuses)
            self.assertIn(("geizhals", 1, BLOCKED), statuses)
            self.assertIn(("geizhals", 2, NOT_FETCHED), statuses)
            self.assertIn(("geizhals", 3, NOT_FETCHED), statuses)
            geizhals_calls = [url for url in client.calls if "geizhals" in url]
            self.assertEqual(len(geizhals_calls), 1)
            pending = json.loads((directory / "blocked.json").read_text(encoding="utf-8"))["pending"]
            self.assertEqual(len(pending), 3)
            text = (FIXTURES / "geizhals.md").read_text(encoding="utf-8")
            first = pending[0]
            ingest(directory, first["source"], first["query"], first["page"], first["url"], text)
            updated = json.loads((directory / "offers.json").read_text(encoding="utf-8"))
            self.assertTrue(any(offer["source"] == "geizhals" for offer in updated["offers"]))
            self.assertTrue((directory / "report.md").read_text(encoding="utf-8").startswith("# Best value"))


if __name__ == "__main__":
    unittest.main()
