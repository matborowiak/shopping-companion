# Shopping companion

A Claude Code agent that looks up one product on the German stores and recommends the best-value listing.

It searches Amazon.de, Geizhals, Idealo, and MyDealz. For each wording of the product it reads up to three result pages. Wordings cover the name you typed, a German or English variant, and the model code with and without hyphens. The ranking uses price, rating, and the number of votes.

## Run it in Claude Code

From this directory:

```bash
claude
```

Then describe the product, or run:

```text
/shop Sony WH-1000XM5
```

To make this agent the session:

```bash
claude --agent deal-hunter
```

The agent runs `python3 -m shop`, then uses its own fetch for any page the script was challenged on. It answers with one recommendation, the next few listings, and any store it could not read.

## Run the search yourself

Python 3.11 or newer. No extra packages.

```bash
python3 -m shop "Sony WH-1000XM5" --pages 3
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--query` | Another wording of the same product. Repeat the flag. |
| `--pages` | Pages per query. Default 3. |
| `--sources` | `amazon,geizhals,idealo,mydealz`, or a subset. |
| `--max-queries` | Cap on wordings. Default 6. |
| `--refresh` | Ignore the six-hour page cache in `.cache/`. |

The write-up is `runs/<timestamp>/report.md`. `blocked.json` lists pages that came back as a challenge instead of results.

Geizhals and Idealo often answer a script with a bot check. The script records those URLs and stops. It does not solve the check. In Claude Code, the agent loads the same public URL with WebFetch and feeds the text back:

```bash
python3 -m shop ingest \
  --run runs/<timestamp> \
  --source geizhals \
  --query "Sony WH-1000XM5" \
  --page 1 \
  --url "https://geizhals.de/?fs=Sony+WH-1000XM5&hloc=de" \
  --file page.md
```

If a later page repeats the previous page's listings, that query stops. Some specific products only have one page of results.

## How a winner is chosen

A listing has to be the product you asked for. Accessories, other model numbers, multipacks, and used or refurbished units are set aside unless your words asked for them.

Ratings are converted to one scale. Amazon and Geizhals stars run from 1 to 5. Idealo's Note is a German school grade, where 1.0 is best. A rating backed by few votes is pulled toward a middling 4.0/5 until more reviews support it. That adjusted quality is squared, weighted by how many votes exist, and divided by the price. After a few hundred reviews, more votes do not raise the score further, so two well-reviewed listings are separated by stars and price. The best score is shown as 100.

MyDealz temperature is interest in the deal, not a review of the product. A deal can still win when the same model is well reviewed elsewhere and the deal price is lower. A price under 40% of the median for that model is treated as not credible, unless the deal is clearly hot.

The result page and slot are shown. They do not change the score.

Prices are whatever the page displayed: Amazon's offer, the Geizhals or Idealo "from" price, and the MyDealz deal price. Shipping and the seller can change the real cost. Check the live page before paying.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
