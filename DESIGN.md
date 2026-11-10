# Mercer

Mercer is a multi-seller marketplace: customers browse independent shops, sellers manage their own catalogue and
orders, and an operator manages the marketplace. Its visual system adapts VoiceBox into square, flat shopping
surfaces: clear product information, restrained red marks, readable tables and consistent forms. This is the single
design specification; [site.css](src/static/css/site.css) implements it.

## Foundations and tokens

The page uses an ink-and-paper palette, square corners, structural 2px borders and no elevation shadows. Focus rings
are the deliberate exception. Light cards share the page ground and use borders to establish their edge; dark cards
use the next surface step. Existing token names are retained. The table gives base declarations, before responsive
overrides; dark values apply both to an explicit theme and the system preference when no light override is stored.

| CSS token | Light | Dark |
|---|---|---|
| `--color-primary` | `#0a0a0a` | `#fafafa` |
| `--color-secondary` | `#ef4444` | `#ef4444` |
| `--color-tertiary` | `#fafafa` | `#0a0a0a` |
| `--color-background` | `#fafafa` | `#0a0a0a` |
| `--color-surface` | `#fafafa` | `#141414` |
| `--color-surface-raised` | `#f5f5f5` | `#1c1c1c` |
| `--color-text-primary` | `#0a0a0a` | `#fafafa` |
| `--color-text-secondary` | `#525252` | `#a3a3a3` |
| `--color-border-subtle` | `#e5e5e5` | `#2e2e2e` |
| `--color-border-medium` | `#d4d4d4` | `#3d3d3d` |
| `--color-border-strong` | `#0a0a0a` | `#fafafa` |
| `--color-secondary-strong` | `#dc2626` | `#f87171` |
| `--color-secondary-ink` | `#b91c1c` | `#f87171` |
| `--color-error` | `#b91c1c` | `#f87171` |
| `--color-error-tint` | `#fef2f2` | `#2a1213` |
| `--color-warning` | `#a16207` | `#facc15` |
| `--color-warning-tint` | `#fefce8` | `#231d05` |
| `--color-success` | `#15803d` | `#4ade80` |
| `--color-success-tint` | `#f0fdf4` | `#0c2216` |
| `--surface-header` | `rgba(250, 250, 250, 0.96)` | `rgba(10, 10, 10, 0.94)` |
| `--band-fill` | `#0a0a0a` | `#000000` |
| `--band-ink` | `#fafafa` | `#fafafa` |
| `--band-ink-soft` | `#a3a3a3` | `#a3a3a3` |
| `--band-border` | `rgba(250, 250, 250, 0.4)` | `rgba(250, 250, 250, 0.28)` |
| `--band-wash` | `rgba(250, 250, 250, 0.08)` | `rgba(250, 250, 250, 0.06)` |
| `--action-fill` | `#0a0a0a` | `#fafafa` |
| `--action-fill-hover` | `var(--color-secondary)` | `var(--color-secondary)` |
| `--on-action` | `#fafafa` | `#0a0a0a` |
| `--on-red` | `#0a0a0a` | `#0a0a0a` |
| `--on-brand` | `#fafafa` | `#0a0a0a` |
| `--card-border` | `#e5e5e5` | `#2e2e2e` |
| `--tile-glyph` | `rgba(10, 10, 10, 0.14)` | `rgba(250, 250, 250, 0.16)` |
| `--tile-ink` | `#0a0a0a` | `#fafafa` |
| `--focus-inner` | `var(--color-tertiary)` | `var(--color-tertiary)` |
| `--focus-outer` | `var(--color-border-strong)` | `var(--color-border-strong)` |
| `--skeleton` | `rgba(10, 10, 10, 0.08)` | `rgba(250, 250, 250, 0.1)` |
| `--font-sans` | `"Work Sans", -apple-system, "Segoe UI", Helvetica, Arial, sans-serif` | `"Work Sans", -apple-system, "Segoe UI", Helvetica, Arial, sans-serif` |
| `--font-display` | `"Archivo Black", Impact, "Arial Black", sans-serif` | `"Archivo Black", Impact, "Arial Black", sans-serif` |
| `--font-mono` | `"Space Mono", "Courier New", Consolas, monospace` | `"Space Mono", "Courier New", Consolas, monospace` |
| `--tracking-tight` | `0` | `0` |
| `--tracking-caps` | `0.12em` | `0.12em` |
| `--line-normal` | `1.6` | `1.6` |
| `--line-compact` | `1.1` | `1.1` |
| `--text-page-title` | `clamp(3rem, 3.6vw, 3.8rem)` | `clamp(3rem, 3.6vw, 3.8rem)` |
| `--space-1` | `0.4rem` | `0.4rem` |
| `--space-2` | `0.8rem` | `0.8rem` |
| `--space-3` | `1.6rem` | `1.6rem` |
| `--space-4` | `2.4rem` | `2.4rem` |
| `--space-5` | `3.2rem` | `3.2rem` |
| `--space-6` | `4rem` | `4rem` |
| `--space-7` | `4.8rem` | `4.8rem` |
| `--space-8` | `5.6rem` | `5.6rem` |
| `--space-9` | `6.4rem` | `6.4rem` |
| `--gutter` | `1.6rem` | `1.6rem` |
| `--anchor-offset` | `7.2rem` | `7.2rem` |
| `--content-max` | `144rem` | `144rem` |
| `--card-radius` | `0` | `0` |
| `--panel-radius` | `0` | `0` |
| `--chip-radius` | `0` | `0` |
| `--pill-radius` | `0` | `0` |
| `--border-structural` | `0.2rem` | `0.2rem` |
| `--rule-accent` | `0.4rem` | `0.4rem` |
| `--card-shadow` | `none` | `none` |
| `--panel-shadow` | `none` | `none` |
| `--nav-shadow` | `none` | `none` |
| `--button-active-scale` | `0.97` | `0.97` |
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | `cubic-bezier(0.23, 1, 0.32, 1)` |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` | `cubic-bezier(0.77, 0, 0.175, 1)` |
| `--dur-press` | `120ms` | `120ms` |
| `--dur-fast` | `160ms` | `160ms` |
| `--dur-enter` | `220ms` | `220ms` |
| `--focus-ring` | `0 0 0 0.2rem var(--focus-inner), 0 0 0 0.4rem var(--focus-outer)` | `0 0 0 0.2rem var(--focus-inner), 0 0 0 0.4rem var(--focus-outer)` |

Responsive token overrides: `--gutter` is `1.6rem` below 768px, `2.4rem` from 768px and `4rem` from 1024px.
`--anchor-offset` is `13.6rem` below 768px, `12rem` from 768px through 1279px, and `9.9rem` from 1280px.
The content maximum is `144rem`. Layouts use `minmax(0, 1fr)` so long names can wrap without widening the page.

### Colour and accessibility

Normal text requires WCAG AA contrast of at least 4.5:1; large text and meaningful non-text boundaries require 3:1.
Secondary prose and generated labels use the secondary text token, never a low-opacity foreground.
Inputs use secondary ink for their boundary; decorative separators can use subtle borders. Focus is a two-colour
ring built from the inner and outer focus tokens, visible on either ground. Errors include words as well as colour.

The accent remains `#EF4444`. On light paper it is a rule, mark or fill; readable red uses `#B91C1C`. Dark mode lifts
red ink to `#F87171`. Text on a red button hover or selection uses the dark `--on-red` ink in both themes. Status
labels use the contrast-corrected success, warning and error colours in the token table, with their own tints.

Red has eleven permitted placements: primary-button hover, brand mark, cart badge when present, section overlines,
active-navigation underline, order-summary top rule, callout/error left rules, current checkout step, footer wordmark
rule, destructive hover and text selection. Category labels, focus rings, stock and successful/completed states do
not acquire a red accent. These are component placements, not a quota per viewport.

### Type and spacing

Archivo Black sets headings and product names; Work Sans sets body copy, forms and labels; Space Mono sets money,
quantities and compact figures. Pixelify Sans is restricted to the two-glyph "67" brand mark. Page headings scale
from 30px to 38px; section headings are about 24px, card names 16–17px, body copy 16px, supporting copy 14px and
small labels 12px. Use uppercase for navigation, short headings and category labels, with the tracking tokens.
Long product names wrap; they are not clipped or shortened to fit a card.

The spacing tokens form the implementation scale: 4, 8, 16, 24, 32, 40, 48, 56 and 64px. Cards use 16px body padding;
panels use 24–32px where space allows and 16px on phones. Forms and actions share their section's left edge.
Borders, empty space and font weight provide hierarchy; gradients, decorative textures and elevation do not.
There are no blog bylines, pull quotes, author avatars or 56px display-heading component.

## Shared shell and controls

The utility strip explains that payment is simulated. The header holds the Mercer wordmark, role-appropriate
navigation, theme switch and login/logout action. On phones the Menu button exposes the navigation, updates
`aria-expanded`, and supports Escape and focus return. The skip link remains the first keyboard action. The footer
retains storefront, project-evidence and system-status links; always-dark bands stay dark in either theme.

Buttons have a square 2px boundary, a minimum 44px regular touch target, Work Sans bold labels and visible focus.
Primary actions invert ink and ground, then use the red hover fill with dark text. Secondary actions are outlined;
destructive actions use an explicit label and the permitted destructive state. Compact table actions retain adequate
spacing. Disabled controls have no active hover state.

Each form control has a visible label, an ink boundary, at least 44px height and the page's surface and text tokens.
Helper text sits beneath its field; validation errors use error ink, an explicit message and `aria-invalid` where
provided by the shared field include. Native selects, checkboxes and radios retain their familiar interaction.
Chips are square, wrapping inline controls. Active filter chips invert ink and paper and contain a visible removal
mark plus an accessible "Remove …" name. Removing one preserves the other filters and resets pagination.

Messages use the existing status/alert roles and structural borders. Empty states explain the next useful action.
In-flight HTMX fragments dim; a changed subtotal can invert briefly. No interface relies on animation alone.

## Catalogue

### Grid and product card

All public catalogue grids use four columns at 1280px and wider, three from 768px through 1279px, and two below
768px, including phones. Rows stretch to align the cards; card names and labels remain readable without truncation.
Grid gaps are 24px on larger screens and 16px on phones. The facet column is separate from these product columns.

Each card has a 4:3 media well, category link, wrapping product name, a muted mono SKU line (imported products), linked shop name, mono price, stock label and
generated-content label when applicable. Category media uses the existing Phosphor sprite mapping. Seller uploads
are contained within the same media well, with no cropping or enlargement interaction. The photo, name and category
links remain keyboard-accessible. Hover changes the border only.

Generated-name/stock labels remain readable on both themes. Stock is
written as "In stock" or "Sold out" and does not rely on a coloured dot.

### Facets and results

At desktop widths the filter panel sits beside the results; below 1024px it stacks above them with compact paired
form fields. Controls cover name, category, exact price bounds, rating, ordering and the current category's attributes.
Counts align beside their values, and applied filters appear above results as removable chips. "Clear" resets the
search. Counts describe purchasable results, as defined by the catalogue contract; presentation adds no second source
for price, stock or eligibility. The result heading, broad-search notice, empty state and pagination use the same
spacing as the grid.

### Product detail

Desktop detail pages place media on the left and purchase information on the right; phones stack them. The media
shows the category icon unless the seller uploaded a photo, served through the existing GridFS view. Contain uploaded
photos without cropping, and keep product-name alternative text. Featured stock photos were dropped (catalogue amendment k).

The information column holds category, product name, shop, mono price, shipping, stock, lead time, quantity/add action,
description, attribute definition list, rating summary and the generated-content notice. Latest reviews follow below;
machine-translated text keeps its label and offers Portuguese originals. A native meter histogram pairs each score with its written count; the same review block paginates newest first. Historical orders carry a written label. Review forms and moderation reuse the bounded form panel and explicit reason field. Long titles and attribute values wrap inside their column.

Wishlist controls use the same outlined button on cards and product details, with a written save/remove state and
aria-pressed. Wishlist reuses the public product grid. The header's neutral alert badge includes a written unseen
count; restock history uses the standard bordered panel and pager. Sold-out state remains text, not a colour cue.

## Seller centre and operator console

Seller products and operator lists share the page header, filter bar, bordered table region and pagination. Filters
and their action buttons align at the bottom of the same row, then wrap on narrow screens. Product and shop names can
wrap; prices and counts use mono/tabular figures. Sellers' edit links stay within their own catalogue and taken-down
products expose their reason. Generated shop/product names keep their tag.

Wide tables scroll inside a labelled, keyboard-focusable region; the page itself does not scroll horizontally.
Header and body rows use identical column tracks. The audit list has five columns: time, decision, shop, actor and
reason; long decisions and reasons wrap within the row. Operator product, seller and category lists reuse this layout.

Seller create/edit uses a bounded form panel with a separate category/options step. Price, stock, freight, lead time,
description, attributes and the optional photo share the standard field treatment. File inputs fit the panel width.
Save and deactivate remain distinct, clearly labelled actions. Operator actions and category-attribute forms use the
same panels, labels, validation messages and explicit reason fields.

## Cart, checkout and orders

Cart items are grouped by shop. Each group shows product links, exact unit price and shipping, labelled quantity and
update/remove controls, line totals and a shop total. The final total and "Review and pay" action align across the
page; phone line items stack before their controls. Availability/stock problems include an explicit message.

Checkout retains the same shop groups, makes item and shipping totals visible and presents simulated payment controls
in a bounded panel. The final amount and payment action form one row on desktop and stack on phones. Labels and money
wrap sensibly without hiding values. No card-number field is introduced. Order and checkout histories reuse contained
table regions and visible state labels.

Order-status chips retain text labels: placed/cancelled use neutral ink and raised ground, paid/shipped use warning
ink and tint, and delivered uses success ink and tint. Refunded/error states use error ink and tint where that state
is explicitly named. The border uses the label colour; status is never communicated by colour alone.

The operator dashboard reuses bordered panels and contained, keyboard-focusable table regions. Every panel names
its reporting date and sources. Replenishment and risk use written amber badges. The revenue chart uses the current
theme's ink and grid colours, has no animation, and retains exact values in the adjacent table. Wide tables scroll
inside their region; the canvas stays inside its panel on phones. Filters and refresh are separate labelled controls.
When the delivery, category and review panels come from the Redis cache, one written line under the lead says so and
how long ago they were computed, and that stock is always live; nothing else on the page changes.

The "too many attempts" page (429) is a standalone error card like the 503 page: a `429 · too many attempts` eyebrow,
one sentence saying how long to wait, and one dark button back to sign in, the order or the shop. It never echoes the
form, and it renders without touching the user or session, so it works during an outage.

The other errors a visitor can reach use the same standalone card (`_standalone_error.html`, which `400`, `403_csrf`,
`413` and `500` extend): a `<code> · <short reason>` eyebrow, one heading in plain words, one or two sentences saying what to
do, and a dark button back to the shop. The form-not-submitted page (a missing or expired CSRF token) and the 500 page also
carry the "check your order history before trying again" warning of the 503 page. None of them shows a stack trace, a path, a
query or a setting.

Trending fills the catalogue's existing panel and uses the same product grid, with written rank/view counts and a
generated-activity label where applicable. Recently viewed uses the same grid on home and product pages. Seller
Insights reuses the contained dashboard table and pager; missing view counts are written as unavailable, and the
units-per-view label explains what the comparison means.

## Motion, themes and interaction

Motion is crisp and mechanical. Use the easing/duration tokens; do not introduce springs, bounce, blur or stagger.
Button press uses `scale(0.97)` and 120ms; icon controls use `scale(0.95)`. Navigation underlines scale from their left
edge. Hover border changes and theme-icon cross-fades use 160ms. New fragments/messages can fade with a 4px rise over
220ms through `@starting-style`; changed figures invert immediately and release over 420ms.

There are no page-enter animations, product-grid stagger, statistic count-ups or theme-toggle spins. Repeated changes
use transitions so they retarget smoothly. Under `prefers-reduced-motion: reduce`, movement and press transforms are
removed; opacity and colour feedback remain at the fast duration. Under `(hover: none)`, hover treatments are
neutralised so a tap does not leave a persistent state.

The theme switch stores the user's explicit light/dark choice before first paint; otherwise system preference wins.
Every new text/background pair must pass AA in both themes. Verify desktop and 375px views, including long generated
names, seller-uploaded media, forms, cart/checkout, seller tables and the operator audit. Inspect the rendered pages
for document overflow as well as checking computed styles.

## Attribution

- **Design reference:** [VoiceBox v1 by Chef (@chef)](https://designmd.ai/chef/voicebox), published under MIT. Jun Keat
  Lim introduced the VoiceBox reference on 23 September 2026 (`d147c9d`); its source was verified on 11 October 2026.
- **Typefaces:** Archivo Black, Work Sans and Space Mono are SIL Open Font License and loaded from Google Fonts.
  Pixelify Sans is also SIL Open Font License and loads only the "67" brand-mark subset.
- **Icons:** Phosphor Icons regular weight, MIT, vendored in [icons.svg](src/static/img/icons.svg), with its licence in
  the sprite header. Existing category mappings remain the default product media.
See [AI use](docs/AI_USE.md) for the implementation/review record.
