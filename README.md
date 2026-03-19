# Notifier

A generic, config-driven web scraper that monitors websites for changes and sends email notifications. Define what to scrape using CSS selectors in a JSON config file, and format notifications with Mustache templates.

Designed to run as a cron job. Each rule has its own schedule (cron expression), so the script can be invoked frequently (e.g. every hour) and each rule runs only when its schedule is due.

## Installation

### Dependencies

```bash
pip install requests beautifulsoup4 pystache croniter numexpr jsonschema
```

### First run

On the first run, the tool creates `~/.notifier/` with a skeleton config and an example Hacker News rule:

```bash
python3 index.py
# Config not found at /home/user/.notifier/config.json
# Creating skeleton configuration in /home/user/.notifier...
# Done. Edit /home/user/.notifier/config.json to configure your scraping rules.
```

Edit `~/.notifier/config.json` with your SMTP credentials and scraping rules, then run again.

## Usage

```bash
python3 index.py                  # process rules whose schedule is due
python3 index.py --force          # ignore schedules, run all rules now
python3 index.py --save-email     # save emails to files instead of sending
python3 index.py --dry-run        # fetch and display data, no emails, no state changes
```

### Cron example

Run the script periodically via system cron. Each rule's `schedule` field controls when it actually executes:

```cron
# Every hour (matches schedules with minute=0)
0 * * * * bash -l -c 'python3 /path/to/index.py' >> ~/.notifier/notifier.log 2>&1

# Every 5 minutes (matches any minute-level schedule)
*/5 * * * * bash -l -c 'python3 /path/to/index.py' >> ~/.notifier/notifier.log 2>&1
```

## File structure

```
~/.notifier/
  config.json              # main configuration
  templates/               # Mustache email templates
    hackernews
  data/                    # state files (tracked items per rule)
    hackernews
    .lastrun_hackernews    # last run timestamp for schedule tracking
    emails/                # saved copies of sent emails
```

## Configuration

A [JSON Schema](config.schema.json) is provided for editor autocompletion and validation. Add `"$schema": "./config.schema.json"` to your config file, or point to the raw URL if hosted on GitHub.

The config is validated against the schema on every run. If the config is invalid, an error email with all validation errors is sent to all rule recipients and the script exits.

The config file (`~/.notifier/config.json`) has three sections:

### `email` -- SMTP server

```json
"email": {
  "server": {
    "host": "smtp.example.com",
    "port": 587,
    "password": "your-password",
    "email": "you@example.com"
  }
}
```

### `defs` -- Reusable scraping definitions

Each definition describes how to fetch and parse data from a website.

```json
"hackernews": {
  "url": "https://news.ycombinator.com",
  "pagination": { ... },
  "query": {
    "type": "list",
    "selector": "tr.athing.submission",
    "id": { ... },
    "filter": { ... },
    "variables": { ... }
  }
}
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `url` | yes | URL to fetch. Supports Mustache variables from rule params, e.g. `https://example.com?q={{query}}` |
| `params` | no | List of parameter names used in the URL template |
| `pagination` | no | Pagination config (see below) |
| `query.type` | yes | `"list"` (multiple items) or `"single"` (one item) |
| `query.selector` | yes | CSS selector for item container(s) |
| `query.id` | no | How to extract a unique ID per item (see below) |
| `query.filter` | no | Filter to exclude items (see below) |
| `query.variables` | yes | Named fields to extract (see below) |

### `rules` -- What to run

Each rule references a definition and can override params, email recipient, template, etc.

```json
{
  "ref": "hackernews",
  "name": "hackernews",
  "schedule": "0 */6 * * *",
  "subject": "Hacker News: {{count}} new stories",
  "template": "./templates/hackernews",
  "email": "you@example.com"
}
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `ref` | yes | Name of the definition in `defs` |
| `name` | yes | Unique rule name. Used for state file (`~/.notifier/data/<name>`) |
| `schedule` | no | Cron expression for when to run (see [Schedule](#schedule)). If omitted, runs every time. |
| `subject` | yes | Mustache template for the email subject line |
| `template` | yes | Path to the Mustache template file (relative to `~/.notifier/`) |
| `email` | yes | Recipient email address |
| `params` | no | Values for the definition's URL template variables |

## Variable extraction

Each variable in `query.variables` defines how to extract a value from a matched element:

```json
"title": {
  "selector": ".titleline > a",
  "value": {
    "type": "text"
  }
}
```

### Value types

| Type | Description | Extra fields |
|------|-------------|--------------|
| `text` | Inner text of the element | |
| `attribute` | HTML attribute value | `name` -- attribute name (e.g. `"href"`) |

### Optional value modifiers

| Field | Description |
|-------|-------------|
| `regex` | Extract a capture group from the raw value. Uses group(1) if available. |
| `prefix` | String prepended to the final value. Useful for turning relative URLs into absolute. |
| `parse` | Convert the extracted string to a typed value. Currently supports `"number"` -- strips currency symbols, spaces, percent signs, and converts European decimal format (comma) to float. Parsed values are used by validators. |

### Optional variable fields

| Field | Description |
|-------|-------------|
| `default` | Fallback value if the selector doesn't match or the value is empty |
| `sibling` | When `true`, search the next sibling element instead of within the matched element. Needed when data is split across adjacent HTML elements (e.g. Hacker News stores title and score in separate `<tr>` rows). |

### Example with all options

```json
"url": {
  "selector": "a.job__title-link",
  "value": {
    "type": "attribute",
    "name": "href",
    "regex": "^(/.*)",
    "prefix": "https://useme.com"
  }
}
```

This selects the `href` attribute from `a.job__title-link`, extracts the path with a regex, then prepends the domain.

## Item identity (deduplication)

The `id` field in the query spec controls how the scraper identifies items it has already seen.

### From a variable with regex

```json
"id": {
  "source": "url",
  "regex": ",(\\d+)/$"
}
```

Takes the `url` variable value and extracts the ID using a regex.

### From an HTML attribute

```json
"id": {
  "type": "attribute",
  "name": "id"
}
```

Reads the `id` attribute directly from the matched element (e.g. `<tr id="47415919">`).

### Fallback

If no `id` spec is provided, the `url` variable is used as the identity. If there's no `url` either, a hash of all variables is used.

## Filtering

The `filter` field excludes items based on CSS class:

```json
"filter": {
  "selector": ".job__header-details--date",
  "exclude_class": "job__header-details--closed"
}
```

This finds `.job__header-details--date` within each item and skips the item if it has the class `job__header-details--closed`.

## Expected structure

The `expect` field on a query spec lists CSS selectors that must exist on the page. If any are missing, the scraper sends an error email about HTML structure changes instead of silently producing empty results.

```json
"query": {
  "expect": [".text-center img[alt='Linux']", ".pagination"],
  "selector": "...",
  ...
}
```

This is checked on the first page only. Useful for detecting when a website redesigns and your selectors break.

## Multiple inputs

The `input` field allows a single rule to scrape multiple pages with different parameters and combine the results into one email. This is useful for monitoring multiple items on the same website (e.g. multiple stock symbols).

`input` can be a single object or an array:

```json
{
  "ref": "bankier",
  "name": "akcje",
  "subject": "[bankier.pl] Zmiany Akcji",
  "template": "./templates/bankier",
  "email": "you@example.com",
  "input": [
    { "params": { "symbol": "BIOMAXIMA" }, "validator": "{{price}} > 10" },
    { "params": { "symbol": "AGORA" }, "validator": "{{price}} > 9.5" },
    { "params": { "symbol": "ASSECOPOL" } },
    { "params": { "symbol": "POLTREG" } }
  ]
}
```

Each entry fetches the URL with its own `params`. If `input` is omitted, the rule's `params` field is used directly (backward compatible).

Params from each input entry are merged into the extracted items, so they're available in templates (e.g. `{{symbol}}`).

## Validators

Each input entry can have a `validator` object that filters extracted items. The validator supports two condition types. If both are present, both must pass (AND logic).

### `test` -- Numeric expression

A [numexpr](https://numexpr.readthedocs.io/) expression with Mustache variable placeholders. Variables should use `"parse": "number"` in the definition so they're available as floats.

```json
"validator": {
  "test": "{{price}} > 9.5"
}
```

Supported operations:

| Operator | Example |
|----------|---------|
| Comparison | `{{price}} > 10`, `{{change_pct}} <= -5` |
| AND | `({{price}} > 10) & ({{change_pct}} < 0)` |
| OR | `({{price}} < 5) \| ({{price}} > 100)` |
| Arithmetic | `{{price}} * {{quantity}} > 1000` |
| Functions | `abs({{change_pct}}) > 3` |

Use parentheses to group compound expressions. See the [numexpr documentation](https://numexpr.readthedocs.io/) for the full list of supported operations.

### `match` -- Regex match

Matches a Mustache-rendered variable value against a regex pattern. Uses `re.search()` so the pattern matches anywhere unless anchored with `^` or `$`.

```json
"validator": {
  "match": {
    "value": "{{title}}",
    "regex": "^Ask HN"
  }
}
```

Set `"negate": true` to invert the match — the condition passes when the regex does **not** match. This is useful for detecting when something disappears from a page:

```json
"validator": {
  "match": {
    "value": "{{status}}",
    "regex": "Coming soon",
    "negate": true
  }
}
```

`match` can also be an array of match objects (AND logic — all must pass):

```json
"validator": {
  "match": [
    { "value": "{{platform}}", "regex": "Linux" },
    { "value": "{{status}}", "regex": "Coming soon", "negate": true }
  ]
}
```

### Combined example

Both conditions must pass (AND logic within a single object):

```json
"validator": {
  "test": "{{price}} > 80",
  "match": {
    "value": "{{company}}",
    "regex": "Asseco"
  }
}
```

### Array of validators (OR logic)

The validator can also be an array. The item is included if **any** validator in the array passes. This is useful for defining price thresholds or notification steps:

```json
"validator": [
  { "test": "{{price}} > 8" },
  { "test": "{{price}} > 9" },
  { "test": "{{price}} > 9.5" }
]
```

Each entry in the array is a full validator object that can use `test`, `match`, or both.

## Pagination

Two pagination types are supported:

### `next_link` -- Follow a "next" link

For sites with a single "More" or "Next" link (e.g. Hacker News):

```json
"pagination": {
  "type": "next_link",
  "selector": "a.morelink",
  "base_url": "https://news.ycombinator.com/",
  "max_pages": 2
}
```

### `numbered` -- Follow numbered page buttons

For sites with numbered pagination (e.g. useme.com):

```json
"pagination": {
  "type": "numbered",
  "selector": ".pagination .pagination__page",
  "active_class": "pagination__page--active",
  "base_url": "https://useme.com/pl/jobs/",
  "max_pages": 5
}
```

Finds the active page button and follows the link of the next one.

### Common fields

| Field | Required | Description |
|-------|----------|-------------|
| `max_pages` | no | Maximum number of pages to fetch (default: 1) |
| `base_url` | no | Base URL for resolving relative `href` values |

## Schedule

Each rule can have a `schedule` field with a standard cron expression. The script is designed to be invoked frequently (e.g. every hour via system cron), and it decides internally which rules are due based on their schedule.

The schedule uses [croniter](https://github.com/kiorky/croniter) to parse standard 5-field cron expressions:

```
 ┌───────────── minute (0-59)
 │ ┌───────────── hour (0-23)
 │ │ ┌───────────── day of month (1-31)
 │ │ │ ┌───────────── month (1-12)
 │ │ │ │ ┌───────────── day of week (0-7, 0 and 7 are Sunday)
 │ │ │ │ │
 * * * * *
```

### Examples

| Expression | Meaning |
|------------|---------|
| `0 8 * * *` | Daily at 8:00 |
| `0 */6 * * *` | Every 6 hours (0:00, 6:00, 12:00, 18:00) |
| `0 9 * * 1` | Every Monday at 9:00 |
| `*/30 * * * *` | Every 30 minutes |
| `0 8,20 * * *` | Twice daily at 8:00 and 20:00 |

### How it works

The script is designed to be invoked periodically by system cron (e.g. every 5 minutes or every hour). On each invocation:

1. The current time is truncated to the start of the minute (e.g. 14:03:27 becomes 14:03:00)
2. Each rule's cron expression is checked against that time using `croniter.match`
3. If it matches and the rule hasn't already run in this minute window, it executes
4. After a successful run, a timestamp is saved to `~/.notifier/data/.lastrun_<rule_name>` to prevent duplicate runs if the script is triggered again within the same minute
5. If no schedule is set, the rule runs every time
6. Use `--force` to bypass all schedules

## Email templates

Templates use [Mustache](https://mustache.github.io/) syntax via [pystache](https://github.com/defunkt/pystache). The following variables are available:

| Variable | Description |
|----------|-------------|
| `{{count}}` | Number of new items |
| `{{now}}` | Current date and time |
| `{{search_url}}` | The rendered URL from the definition |
| `{{#items}}...{{/items}}` | Loop over new items |
| `{{index}}` | 1-based position within the items list |
| Any rule `params` | e.g. `{{query}}` |
| Any extracted variable | e.g. `{{title}}`, `{{url}}`, `{{score}}` |

### Example template

```
Hacker News - New Stories
Checked at: {{now}}

Number of new stories: {{count}}
============================================================
{{#items}}

{{rank}} {{title}}
     Score: {{score}} | {{age}}
     URL:   {{url}}
     HN:    {{comments_url}}
{{/items}}

============================================================
```

The `subject` field in a rule is also a Mustache template with access to the same variables.

## How it works

1. On each run, all rules in the config are processed sequentially
2. For each rule, the scraper fetches the URL (with pagination) and extracts items using CSS selectors
3. Items are compared against the saved state in `~/.notifier/data/<rule_name>`
4. New items (not seen before) trigger an email notification rendered from the Mustache template
5. The current items are saved as the new state for the next run

## License

Copyright (C) 2026 [Jakub T. Jankiewicz](https://jakub.jankiewicz.org)<br/>
Released under [MIT](https://opensource.org/licenses/MIT) license
