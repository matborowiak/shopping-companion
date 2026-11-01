---
name: shop
description: >-
  Search Amazon.de, Geizhals, Idealo, and MyDealz for a product, read three
  pages of several query wordings, and recommend the best-value buy from
  price, star rating, and review count. Use when the user names something
  they want to buy, compare, or check for a deal in Germany.
argument-hint: "[product, for example Sony WH-1000XM5]"
allowed-tools: Bash, Read, Write, Glob, Grep, WebFetch, WebSearch
---

# Shop the German stores

Find the best-value listing for the product the user named. Work from the repo root.

## 1. Name the searches

If the request does not name a product, ask what they want. If it does, do not wait.

Build 3 to 6 search strings for the same item:

- the words the user used
- a German wording and an English wording, when those differ
- the bare model code, with and without hyphens (`WH-1000XM5` and `WH1000XM5`)
- a common other name, only when you are sure it is the same product

Do not add `kaufen`, `billig`, or `günstig`. Do not search a different model "to compare" unless the user asked for alternatives.

## 2. Crawl with the script

```bash
python3 -m shop "USER WORDS" --query "wording two" --query "wording three" --pages 3
```

The script also adds its own variants, keeps at most 6 queries, and reads up to 3 pages of each query on Amazon.de, Geizhals, Idealo, and MyDealz. It waits between requests. It writes `runs/<timestamp>/report.md`, `offers.json`, and `blocked.json`. The last stdout line is `RUN_DIR=...`.

Pass `--sources amazon` (or a comma-separated subset) when the user wants fewer stores.

## 3. Fill pages the script could not read

Open `blocked.json`. For each pending URL:

1. WebFetch that exact URL.
2. If the first product title is the same as the previous page of that query, stop that query. The site repeated a page. Do not keep fetching copies.
3. Otherwise write the fetched text to `RUN_DIR/fetched/<source>-p<page>-<n>.md`.
4. Add it back:

```bash
python3 -m shop ingest --run RUN_DIR --source geizhals --query "the query" --page 1 --url "the url" --file RUN_DIR/fetched/geizhals-p1-1.md
```

Use the source, query, page, and url from `blocked.json`. Fetch page 1 of a blocked query before pages 2 and 3. Skip a later page when page 1 was empty or a repeat.

If WebFetch is also challenged, leave that source out and say so. Do not guess its prices. WebSearch may only help you find the product's real name. Snippets are not prices.

## 4. Judge the report

Read `report.md` after the ingests. The value index already balances price, rating, and vote count.

Reject the printed winner, and take the next row that passes, when any of these are true:

- it is a different product, a different model, or the wrong form factor (in-ear versus over-ear, for example)
- it is an accessory, a multipack, or used or refurbished, and the user did not ask for that
- the title and the link disagree
- the price is so low that the listing is not credible, and MyDealz heat is not clearly positive

Say which row you rejected and why.

## 5. Answer

Lead with the buy: product name, price in euro, store and seller, link, rating, vote count, and one sentence on why it beat the next real option. Then a short table of the next few listings. Then any store you could not read.

Prices are a snapshot. Tell the user to confirm the seller, shipping, and return terms on the live page. MyDealz heat is votes on the deal, not reviews of the product. Idealo's Note is a German school grade where 1.0 is best. Geizhals and Idealo "ab" prices are the cheapest offer those sites listed, which may be a marketplace seller.

Remember a seller only when the user tells you they had a bad experience with them. Do not remember prices.
