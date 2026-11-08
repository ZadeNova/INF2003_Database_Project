# product_photos: Photos and a few new demonstration products

status: approved
plan owner: Erfan · implementers: a teammate (the data files) and Claude (the loader, already built) · reviewer: Erfan on
merge · phase 5 ([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: the frozen Tier 1 application; backlog
items #7 and #16 in [improvements](improvements.md)

**Purpose.** The demonstration should look like a working marketplace: pictured products on the home page and category
pages, a few believable new products from a merchant of their own, and (optionally) 3D models of two or three. Nothing here
adds a database feature; it supports the video and the "complete and realistic demonstration" line of the assessment.

## Contract

**Already built and committed** (Claude, branch `improvements/backlog`): [showcase.py](../../src/catalogue/showcase.py)
and the `seed_showcase` command, run by `seed_demo`; the default "Recommended" sort that puts featured products first;
the three readable demo shop names; tests; README section "Demonstration catalogue". The loader reads
[catalogue.json](../../data/demo_showcase/catalogue.json) and `data/demo_photos/`.

**The teammate's work, and only this** (branch `improvements/photos`):

| They add or edit | Limit |
|---|---|
| Photos in `data/demo_photos/` for the 30 listed Olist products (`<product id>.jpg`, `.png` or `.webp`) | 30 files |
| `licences.csv` in the same folder: one complete row per photo | one row per file |
| The `merchants`, `categories` and `products` lists in `catalogue.json` | 1 merchant (`demo-seller-4`), up to 12 products, up to 2 new categories (only if no existing one fits) |
| A photo for each new product | free-to-use sources, JPEG, PNG or WebP, at most 2 MB (aim for 1200 px and under 500 KB) |

The teammate chooses the merchant's name, the products, the categories and the images, within those limits and the
README's rules. The loader enforces the limits and the file rules and lists every problem in one run.

**Not in scope, and not touched:** application code, tests, migrations, schema, the benchmark and its data, Redis, row-level
security, the other batches, any docs or README (the teammate does not edit them), the 30 Olist products themselves (names,
prices, stock), seeded reviews or orders for new products, and creating anything through the website. Photos and products
live only as committed files, so a fresh clone reproduces them.

**Optional stretch: sneaker 3D models (`.glb`).** Only after Batch 6 and only if the schedule allows; otherwise dropped
without any effect on the rest. If built (about a day of Claude's time): an optional `model` field on a new product, files in
`data/demo_models/`, at most 3 models of at most 5 MB each, checked by the loader (glTF 2 header, no external links, a
licence row), stored in GridFS, served by one new route for visible products, and shown with a vendored `<model-viewer>`
that loads only on pages that have a model and falls back to the photo. No seller upload path, so AGENTS.md rule 7 is
unaffected. Until then the teammate may shortlist 1 to 3 CC0 or CC BY models (licence and size noted) and does not commit
them.

## Effect on the other batches

| Batch | Effect |
|---|---|
| 5 Redis, 6 benchmark, 6b full-text search, 7 code quality | None. They change `src/`, compose, `benchmarks/` and docs; this lane adds files under `data/demo_photos/`, `data/demo_models/` (stretch) and edits only three lists of one JSON file. The benchmark uses its own databases and `data/derived`. |
| 8 Row-level security | Claude checks that `seed_showcase` still works under the new roles. It runs as the owner role today. |
| Merge | Add-only files plus edits inside the three lists, which nobody else edits. Claude does not touch those lists or the photos while the branch is open. |

**After merging:** run `seed_showcase`, `scripts/check_docs.py` and the full suite once (`seed_demo` also runs on the test
data and will now create the teammate's merchant and products there). **Cut line:** if the branch is not ready by 13
November, merge only what passes `seed_showcase` without problems; photos not supplied simply show the category icon.

## Decisions

| ID | Decision | Why |
|---|---|---|
| a | Committed files and a loader, not products created in the app | Anything made in a person's database vanishes on a reset and never reaches the markers |
| b | New products go through the seller code path and keep the generated-content label | Same rules and audit as sellers; stock, prices and merchants are demonstration values |
| c | No seeded reviews or orders for new products | Seeded reviews need invented orders and would pollute the real delivery and review figures; the review flow is shown live |
| d | Limits are constants in the loader (12 products, 2 categories, 3 merchants, 3 models) | Keeps the lane small and the cost of a wrong guess low |
| e | 3D models are a stretch item with a drop condition | New third-party script and route, a few days before the freeze |

## Teammate instructions

Hand this section to the teammate. The product list below is a copy for convenience; `catalogue.json` (`olist_photos`) is
the source of truth for ids and names.

**Goal.** Give the demonstration a good first impression with photos and a few new products, as **committed files**. Do
not create products through the website: they would live only in your database and vanish on a reset.

**Deadline:** Friday 13 November. Push `improvements/photos` and tell Erfan.

**Files you may change:** `data/demo_photos/` (photos and `licences.csv`) and the `merchants`, `categories` and `products`
lists in `data/demo_showcase/catalogue.json`. Nothing else: no code, README or docs, and no other branches. Commit
messages use the `type: summary` style, for example `feat: photos for the showcase products`.

**Setup (once).**

```
git fetch && git checkout improvements/photos
python src/tools/init_env.py
docker compose up --build -d
docker compose run --rm migrate python manage.py import_olist
docker compose run --rm migrate python manage.py seed_demo
```

If you already have a database from before 8 November, run `docker compose down --volumes` first (the product names
changed). After editing your files, run `docker compose run --rm migrate python manage.py seed_showcase`. It lists every
problem in your files at once. Then look at http://127.0.0.1:8000/ (log in as `demo-seller-4`, password
`mercer-demo-seller`, to see your merchant). It is safe to run again and again.

### Job A: photos for 30 existing products (required)

Save one photo per row as `data/demo_photos/<product id>.jpg` (`.png` and `.webp` also work). The photo must show what the
name says and, where it can, what the attributes say. No logos or brand names, no watermarks, no faces, no text overlays.
Do not edit or rename these products.

| Product id | Category | Name | Attributes shown on the page |
|---|---|---|---|
| 33653 | Bed bath table | Lightweight cotton blanket, king size | material: cotton, pattern: geometric, size: king |
| 33374 | Bed bath table | Everyday cotton sheet set, single size | material: cotton, pattern: striped, size: single |
| 34008 | Health beauty | Nourishing cream body moisturiser, 50 ml | format: cream, skin type: combination, volume ml: 50 |
| 33989 | Health beauty | Light lotion foot treatment, 200 ml | format: lotion, skin type: combination, volume ml: 200 |
| 34118 | Sports leisure | Lightweight nylon gym bag for fitness | activity: fitness, material: nylon, outdoor: True |
| 33460 | Sports leisure | Sporty steel water bottle for running | activity: running, material: steel, outdoor: True |
| 33056 | Furniture decor | Warm classic bookshelf for the bedroom | material: metal, room: bedroom, style: classic |
| 31475 | Furniture decor | Simple classic side table for the bedroom | material: wood, room: bedroom, style: classic |
| 29399 | Computers accessories | Compact webcam, Windows compatibility | compatibility: Windows, connection: USB, wireless: False |
| 33413 | Computers accessories | Ergonomic wireless mouse, Windows compatibility | compatibility: Windows, connection: Bluetooth, wireless: True |
| 33246 | Housewares | Classic glass food container | capacity ml: 250, dishwasher safe: True, material: glass |
| 33097 | Housewares | Practical silicone ice tray | capacity ml: 500, dishwasher safe: False, material: silicone |
| 34094 | Watches gifts | Signature steel dress watch, gold case | case colour: gold, display: analogue, strap: steel |
| 32808 | Watches gifts | Modern leather wristwatch, gold case | case colour: gold, display: digital, strap: leather |
| 30955 | Telephony | Rugged black USB-C charging cable | accessory: cable, colour: black, connector: USB-C |
| 29241 | Telephony | Rugged black phone case | accessory: case, colour: black, connector: micro-USB |
| 32365 | Garden tools | Classic steel garden hedge shears | handle: plastic, material: steel, tool type: pruning |
| 29550 | Garden tools | Handy aluminium garden hose nozzle | handle: wood, material: aluminium, tool type: watering |
| 32066 | Auto | Everyday plastic dashboard phone holder, universal fit | fit: universal, material: plastic, use: interior |
| 31437 | Auto | Urban plastic squeegee, universal fit | fit: universal, material: plastic, use: maintenance |
| 33606 | Toys | Classic puppet set, ages 9+ | age years: 9, material: fabric, play type: pretend |
| 31250 | Toys | Bright wooden block set, ages 6+ | age years: 6, material: wood, play type: building |
| 33983 | Cool stuff | Curious wood model kit | material: wood, portable: False, theme: hobby |
| 31849 | Cool stuff | Clever metal phone stand | material: metal, portable: True, theme: desk |
| 33931 | Perfumery | Elegant floral body mist, 100 ml | concentration: eau de toilette, scent: floral, volume ml: 100 |
| 33036 | Perfumery | Elegant woody fragrance gift set, 30 ml | concentration: eau de parfum, scent: woody, volume ml: 30 |
| 34100 | Baby | Little silicone teether, 0+ months | age months: 0, care: machine wash, material: silicone |
| 30970 | Baby | Snug silicone bib set, 12+ months | age months: 12, care: machine wash, material: silicone |
| 33219 | Electronics | Compact Bluetooth speaker, mains powered | connection: Bluetooth, portable: False, power: mains |
| 31641 | Electronics | Everyday digital alarm clock, battery powered | connection: Wi-Fi, portable: False, power: battery |

### Job B: your own merchant and up to 12 new products

Edit `data/demo_showcase/catalogue.json`; fill the empty `merchants`, `categories` and `products` lists. Example:

```json
"merchants": [
  {"username": "demo-seller-4", "shop_name": "Harbour Garden Supply", "city": "sao paulo", "state": "SP"}
],
"categories": [
  {"slug": "kitchen-gadgets", "name_en": "Kitchen gadgets", "icon": "pot",
   "attributes": {"material": {"type": "string", "values": ["steel", "wood", "silicone"]}}}
],
"products": [
  {"merchant": "demo-seller-4", "category": "garden-tools", "name": "Steel hand trowel",
   "description": "A sturdy hand trowel for potting and planting.",
   "price": "24.90", "freight": "4.50", "stock": 40, "lead_time_days": 3,
   "attributes": {"material": "steel", "tool_type": "hand tool"}, "photo": "steel-hand-trowel.jpg"}
]
```

- **Merchant:** you choose the shop name. The username is `demo-seller-4` (more merchants: `-5`, `-6`).
- **Products:** at most 12, with believable names (no invented brand names), a description of 10 to 5,000 characters,
  `price` and `freight` in S$ as text, `stock` at most 99,999, and a `photo` file name of your choice.
- **Sneakers** go under the existing `fashion-shoes` category (attributes `colour: black, white, blue, grey` and
  `collection: classic, everyday, modern`) and count toward the 12.
- **Categories:** use existing ones where you can; `attributes` are optional, so give only the ones that fit. Propose at
  most 2 new categories, and only if nothing existing fits. A new category needs `slug`, `name_en`, an `icon` (one of:
  factory, apple, cup, palette, scissors, gift, headphones, car, baby, heart, puzzle, bed, house, hammer, music, camera,
  fan, gamepad, lamp, leaf, shield, star, tent, bag, shoe, shirt, monitor, pot, book, storefront, chair, paw, clock,
  printer, phone, plug, package) and `attributes`.
- **No reviews and no orders** for new products.

Main categories and their allowed attribute values:

| Slug | Name | Attributes (allowed values) |
|---|---|---|
| `bed-bath-table` | Bed bath table | material: cotton, linen, microfibre; size: single, queen, king; pattern: plain, striped, geometric |
| `health-beauty` | Health beauty | format: cream, gel, lotion; skin_type: dry, normal, combination; volume_ml: 50, 100, 200 |
| `sports-leisure` | Sports leisure | activity: fitness, camping, running; material: nylon, polyester, steel; outdoor: true, false |
| `furniture-decor` | Furniture decor | material: wood, metal, fabric; style: minimal, classic, industrial; room: bedroom, living room, study |
| `computers-accessories` | Computers accessories | connection: USB, Bluetooth, wired; compatibility: Windows, Linux, universal; wireless: true, false |
| `housewares` | Housewares | material: steel, glass, silicone; capacity_ml: 250, 500, 1000; dishwasher_safe: true, false |
| `watches-gifts` | Watches gifts | strap: leather, steel, silicone; display: analogue, digital; case_colour: silver, black, gold |
| `telephony` | Telephony | accessory: case, charger, cable; connector: USB-C, micro-USB, universal; colour: black, white, blue |
| `garden-tools` | Garden tools | tool_type: hand tool, watering, pruning; material: steel, aluminium, plastic; handle: wood, rubber, plastic |
| `auto` | Auto | use: interior, maintenance, storage; material: rubber, plastic, metal; fit: compact, standard, universal |
| `toys` | Toys | age_years: 3, 6, 9; play_type: building, puzzle, pretend; material: wood, plastic, fabric |
| `cool-stuff` | Cool stuff | theme: travel, desk, hobby; material: metal, plastic, wood; portable: true, false |
| `perfumery` | Perfumery | scent: citrus, floral, woody; volume_ml: 30, 50, 100; concentration: eau de toilette, eau de parfum |
| `baby` | Baby | age_months: 0, 6, 12; material: cotton, silicone, polyester; care: hand wash, machine wash |
| `electronics` | Electronics | power: USB, battery, mains; connection: wired, Bluetooth, Wi-Fi; portable: true, false |

Other categories (for example `stationery`, `pet-shop`, `fashion-shoes`) only have `colour: black, white, blue, grey` and
`collection: classic, everyday, modern`. Their slugs are the lowercase English names joined by hyphens.

### Photo rules (both jobs)

- Free-to-use sources only (Pexels, Unsplash, Pixabay, CC0 or public domain).
- JPEG, PNG or WebP, at most 2 MB; aim for about 1200 px wide and under 500 KB so the repository and the submission stay
  small.
- One row per photo in `data/demo_photos/licences.csv`, columns `file,author,source_url,licence`; the link must start with
  `https://`. The loader refuses any photo with an incomplete row.

### Optional: sneaker 3D models (do not commit yet)

Shortlist 1 to 3 sneaker `.glb` models you could use (CC0 or CC BY only; note the licence, author, source link and file
size, ideally under 3 MB). Send the list to Erfan. Do not add the files to the repository: the loader does not support
models yet, and it will only be built if the schedule allows (see the stretch section above).

### Optional QA (no files from this)

As `demo-seller-4` (or any demo seller), create and edit a product, upload a photo and deactivate it. As `demo-operator`,
take a product down with a reason, restore it, and add a product option to a category. Send Erfan a short list of anything
odd or confusing.

### When you are done

Run `seed_showcase` once more and confirm it prints no problems and no "Photos not supplied yet" line. Push
`improvements/photos` and message Erfan.

## Review notes

Planned 8 November 2026 with Erfan. Loader reviewed by tests (12 tests: creation, rerun, login, error listing, limits,
non-image, missing password, name mismatch, ordering) and the full suite. Merge checks above.
