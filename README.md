# FitFindr — Starter Kit

## Demo

<video src="demo.mp4" controls title="FitFindr demo"></video>

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`
Filters the 40-item dataset by price and size (when provided), scores each remaining listing by counting keyword matches across `title`, `description`, `style_tags`, and `category`, drops zero-score listings, and returns the survivors sorted by relevance. Returns `[]` if nothing matches — never raises.

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`
Calls the Groq LLM to suggest 1–2 outfit combinations using the new item and the user's wardrobe pieces. `new_item` is a listing dict from `search_listings`; `wardrobe` has an `items` list of wardrobe-item dicts. If `wardrobe["items"]` is empty, uses a generic styling prompt instead of referencing specific pieces. Returns `""` on API failure.

### `create_fit_card(outfit: str, new_item: dict) → str`
Generates a 2–4 sentence Instagram-style caption using the outfit suggestion text and the listing's `title`, `price`, and `platform` fields. Runs at temperature 0.9 for variety. Returns an error string immediately if `outfit` is empty or whitespace — no LLM call made.

---

## Planning Loop

`run_agent(query, wardrobe)` runs a fixed three-step sequence with early exits:

1. **Parse** — regex extracts `description`, `size`, and `max_price` from the query. No LLM needed.
2. **Search** — calls `search_listings`. If the result is `[]`, sets `session["error"]` and returns immediately. `suggest_outfit` is never called with empty input.
3. **Outfit** — calls `suggest_outfit` with `session["selected_item"]` (always `results[0]`) and the wardrobe. If the return is `""` (LLM failure), sets `session["error"]` and returns early.
4. **Fit card** — calls `create_fit_card` with the outfit string and selected item. Returns the completed session.

The key branch is after step 2: a nonsense query like `"designer ballgown size XXS under $5"` returns `session["error"]` set and `outfit_suggestion`/`fit_card` both `None`. A valid query populates all four output fields with `error = None`.

---

## State Management

All inter-step data lives in a single `session` dict initialized at the start of `run_agent`:

| Key | Written | Read by |
|---|---|---|
| `parsed` | step 1 | step 2 |
| `search_results` | step 2 | — (reference only) |
| `selected_item` | step 2 | steps 3 & 4 |
| `outfit_suggestion` | step 3 | step 4 |
| `fit_card` | step 4 | `app.py` |
| `error` | any early exit | `app.py` |

Nothing is passed as function arguments between tools — each step reads from the session dict that the previous step wrote to. `app.py` reads `selected_item`, `outfit_suggestion`, `fit_card`, and `error` to populate the three Gradio panels.

---

## Error Handling

**`search_listings`** — returns `[]` on no match; no exception path exists. Tested with `"zzzxxx"` and `size="XXS", max_price=5` — both return `[]` cleanly. The agent catches this and sets `session["error"] = "No listings found matching your description, size, or budget..."`.

**`suggest_outfit`** — empty wardrobe is handled as a separate prompt path, not an error. The response starts with `"Since you haven't added wardrobe items yet, here are general styling ideas: "`. If the Groq API throws, the except block returns `""` and the agent sets `session["error"] = "Could not generate outfit suggestions. Please try again."`.

**`create_fit_card`** — guards against empty/`None`/whitespace `outfit` before touching the LLM. Passing `outfit=""` returns `"Could not create a fit card — outfit data was missing or incomplete."` instantly. Same string is returned on Groq exceptions.

---

## Spec Reflection

**Where the spec helped:** Writing out the exact conditional logic in the Planning Loop section before coding meant the early-exit structure was obvious to implement. Having the branch conditions written in plain English (`if not session["search_results"]: return session`) made it hard to accidentally call `suggest_outfit` with no input.

**Where implementation diverged:** The spec said parsing could use "regex, string splitting, or the LLM." I planned to potentially use the LLM for parsing but switched to regex after seeing how consistent the query patterns were. It's faster, cheaper, and deterministic — no risk of the parser itself failing and killing the whole interaction.

---

## AI Usage

**Planning loop implementation** — I gave Claude the full Architecture diagram from `planning.md` (the Mermaid flowchart) and the Planning Loop section describing the four numbered steps with their exact branch conditions. Claude generated `run_agent()` with the session dict structure and early exits. I reviewed it and made two changes: (1) it originally stored `selected_item` inside the search block without a separate step, which I broke out to match the spec; (2) it used a hardcoded `results[0]` inline instead of assigning to `session["selected_item"]` first, which would have broken the state flow to `create_fit_card`.

**`suggest_outfit` implementation** — I gave Claude the Tool 2 spec block (inputs, return value, empty-wardrobe behavior with the exact required prefix string) and the wardrobe schema field list. It produced the two-prompt-path structure correctly. What I revised: the original system prompt said "fashion stylist" generically; I changed it to specifically mention secondhand and thrifted fashion to keep the suggestions relevant to the app's context.
