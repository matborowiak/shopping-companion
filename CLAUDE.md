# Shopping companion

This repo finds the best-value listing for one product on the German stores: Amazon.de, Geizhals, Idealo, and MyDealz.

When the user wants to buy something, compare prices, or asks which offer is worth it, follow `.claude/skills/shop/SKILL.md` exactly.

Rules that always apply:

- Every price, star rating, and vote count in the answer comes from a page read in this session. Never fill a gap from memory.
- Read up to 3 pages for each wording of the product. Search several wordings when the same item has more than one name.
- Do not solve captchas, rotate proxies, or work around a block. If a script is challenged, use WebFetch on that public URL and continue. If WebFetch is challenged too, say that source was unavailable.
- Confirm the winner is the requested product before you recommend it. A cheaper accessory, a different model, a multipack, or a used unit does not win unless the user asked for it.
