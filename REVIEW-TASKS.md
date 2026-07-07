# Code Quality Review — finnbruktbil

## Summary

The core pipeline package (`finnbruktbil/`) is generally well-structured and, in the newer modules (`cli/config.py`, `cli/summarize.py`, `vegvesen.py`, `scraper.py`), thoughtfully documented — the constraint-evaluator registry and the Norwegian↔ASCII column mapping are clean, well-commented designs that match the conventions in CLAUDE.md. The main weaknesses are concentrated in two places: `analysis_app.py`, an 800-line top-level Streamlit script with heavy copy-paste duplication and redundant imports, and `db.py`'s `fetch_ids_for_scraping`, which has a genuine correctness bug plus leftover dead branches. There is no linter/formatter configured, and several legacy artifacts (`scrape-ids.py`, `scrape-articles.py`, `data/ids.json`, scratch markdown) linger at the repo root and inside the package, obscuring the real entry points. Error handling is uniformly `print()`-based with broad `except Exception` catches, which is acceptable for a personal tool but inconsistent enough to be worth noting. Nothing here threatens the canonical `cli-*.py` workflows, but the analysis module and DB query logic are the highest-leverage cleanup targets.

---

## High priority

### 1. Add and configure a linter/formatter (ruff) — ✅ DONE (2026-07-07)
- **Files:** `pyproject.toml` (new `[tool.ruff]` section)
- **Why:** No linter/formatter is configured, so style drift, unused imports, and dead code accumulate silently (this review found several instances a linter would flag automatically).
- **Done:** ruff added as a dev dependency (`[dependency-groups]`), configured with `select = ["E", "F", "I", "UP", "B", "SIM", "PTH", "PLR0913", "PLR2004", "C4", "RUF"]`, `line-length = 120`, and `requires-python = ">=3.11"` (was missing entirely). `ruff check --fix` + `ruff format` baseline applied; `ruff check .` and `ruff format --check .` are clean. Legacy `scrape-ids.py`/`scrape-articles.py` are excluded pending task #4. This also completed #5 and named the `1900`/`10` magic values from #16.
- **Effort:** S

### 2. Fix `fetch_ids_for_scraping` stale-hours logic (correctness bug)
- **Files:** `finnbruktbil/db.py:306-357`
- **Why:** When `stale_hours` is set, the query applies `.limit(limit)` *before* the stale filter runs client-side, so it fetches only `limit` rows ordered null-first and then discards non-stale ones — routinely returning far fewer than `limit` ids (and never the "scraped-but-stale" rows deeper in the table). There is also a dead `pass  # We'll handle this differently` branch (lines 320-321) and `threshold` is computed twice.
- **Approach:** Either push the OR-condition into the Supabase query (`.or_("last_scraped.is.null,last_scraped.lte.<threshold>")`) or fetch without the limit and slice after filtering. Remove the dead branch and dedupe the threshold computation.
- **Effort:** M

### 3. De-duplicate the three scatter-plot builders in `analysis_app.py`
- **Files:** `finnbruktbil/analysis_app.py:399-505, 522-636, 638-759`
- **Why:** The usedness, mileage, and registration plots each repeat the same four-way `if color_column == ...` branch constructing a nearly identical `px.scatter` call — roughly 300 lines of copy-paste. Any change to coloring or hover data must be made in three places and is easy to get wrong.
- **Approach:** Extract one helper, e.g. `make_scatter(df, x, y, color_column, size_column, extra_labels)`, that encapsulates the color-mode branching and returns a figure; call it three times.
- **Effort:** M

### 17. Handle the Supabase 1000-row response cap in `load_ads_dataframe` *(added by follow-up review)*
- **Files:** `finnbruktbil/db.py` (`load_ads_dataframe`, and `fetch_ids_for_scraping` when `limit > 1000`)
- **Why:** `client.table("ad_details").select("*").execute()` is subject to PostgREST's default 1000-row response cap. Once the table grows past that, the dashboard and summarize stage silently analyze a truncated dataset — no error, just missing rows.
- **Approach:** Paginate with `.range(offset, offset + page_size - 1)` in a loop until a short page is returned (or raise the `db_max_rows` setting in the Supabase dashboard and assert `len(result.data)` stays below it).
- **Effort:** S

### 4. Remove or relocate legacy root scripts
- **Files:** `scrape-ids.py`, `scrape-articles.py`
- **Why:** Both are superseded by the package (`cli/fetch_ids.py`, `scraper.py`) and are partly broken (`scrape-articles.py` uses `By.TAG_Name` — wrong casing — and defines an unused `CarListing`/`parse_car_listing`, and the file just ends mid-thought with no `main`). They sit next to the real `cli-*.py` entry points and invite confusion about what to run.
- **Approach:** Delete them, or move to a clearly-marked `misc/legacy/` if kept for reference. `prompt.md` says `scrape-articles` was only ever "inspiration."
- **Effort:** S

---

## Medium priority

### 5. Remove redundant imports and unused availability flags in `analysis_app.py` — ✅ DONE (2026-07-07, part of #1 baseline)
- **Files:** `finnbruktbil/analysis_app.py`
- **Why:** `pandas`, `numpy`, `sklearn`, and `SKLEARN_AVAILABLE` were imported/defined at the top and then re-imported/redefined mid-module. `SCIPY_AVAILABLE` and `from scipy import stats` were set up but `stats` was never used.
- **Done:** Mid-file duplicate block deleted and scipy dropped from the top `try`. Note the subtlety the original task missed: the top block imported sklearn *and* scipy in one `try`, so a missing scipy would have falsely set `SKLEARN_AVAILABLE = False` — the mid-file re-import was silently correcting that. Removing scipy from the `try` (not just deleting the duplicate) preserves behavior.
- **Effort:** S

### 6. Consolidate duplicated import-status categorizers
- **Files:** `finnbruktbil/analysis_app.py:121-127, 272-278`
- **Why:** `categorize_imported` and `map_import_status` are byte-for-byte identical logic (True→"imported", False→"norwegian", else "unknown"), maintained separately.
- **Approach:** Keep one function and reuse it for both the filter category and the numeric-map category columns.
- **Effort:** S

### 7. Batch `upsert_ad_ids` instead of per-id round trips
- **Files:** `finnbruktbil/db.py:127-172`
- **Why:** The function issues a SELECT plus an UPDATE/INSERT for every id in a Python loop — 200 ids means ~400 sequential network calls, slow and fragile if any one fails mid-loop.
- **Approach:** Use a single `.upsert(records)` for the insert/last_seen path; handle the `missing → pending` reset with one targeted update query filtered by `in_("ad_id", ...)` and `eq("scrape_status","missing")`.
- **Effort:** M

### 8. Split `analysis_app.py` into functions with a guarded entry point
- **Files:** `finnbruktbil/analysis_app.py` (whole file, 804 lines)
- **Why:** The module executes everything at import/top level, mixing data loading, filtering, modeling, and three plot sections. It is untestable, hard to navigate, and the OLS logic (which PRICE_MODEL.md documents) is buried among UI code.
- **Approach:** Extract cohesive functions (`load_and_filter`, `perform_ols_analysis` already exists, `render_scatter_section`) and drive them from a `main()`; keep Streamlit top-level calls thin. Can be done incrementally after task #3.
- **Effort:** L

### 9. Fix misleading docstrings referencing a non-existent `api_key` argument
- **Files:** `finnbruktbil/aux_data_parser.py:109-122, 232-248`
- **Why:** `parse_aux_data_with_openai` and `parse_aux_data_from_ad` document an `api_key` parameter, but neither accepts one — the key is read from the module-level `OPENAI_API_KEY`. Misleading docs on the one paid-API path.
- **Approach:** Delete the `api_key` lines from both docstrings (and the "either as argument or" wording in the `ValueError` message).
- **Effort:** S

### 10. Standardize on `logging` instead of `print` for diagnostics
- **Files:** `finnbruktbil/scraper.py`, `finnbruktbil/vegvesen.py`, `finnbruktbil/aux_data_parser.py`, `finnbruktbil/db.py`
- **Why:** All warnings/diagnostics use bare `print()`, so there is no way to adjust verbosity, and scraper "Missing keys"/"Redundant keys" noise is interleaved with genuine warnings on every ad. Inconsistent with a tool meant to run long scraping loops.
- **Approach:** Introduce a module-level `logger = logging.getLogger(__name__)` and replace `print(f"Warning: ...")` with `logger.warning(...)`; configure a basic handler in the CLI entry point. Can be phased in module by module.
- **Effort:** M

---

## Low priority

### 11. Delete dead helper `extract_attribute_values`
- **Files:** `finnbruktbil/browser.py:72-76`
- **Why:** Defined but never referenced anywhere in the codebase.
- **Approach:** Remove the function (and the now-unused `Iterable`/`Iterator` imports if nothing else needs them).
- **Effort:** S

### 12. Reconcile the two trim-level detection strategies
- **Files:** `finnbruktbil/analysis_app.py:81-113` vs. `finnbruktbil/cli/summarize.py:53-57`
- **Why:** The dashboard hardcodes model-specific subtitle parsing ("gt-line"/"exclusive") while `summarize.py` reads a general `trim_level` column populated by the aux-data parser — the same problem solved two incompatible ways. The in-file TODO (lines 94-101) already flags this.
- **Approach:** Have the dashboard prefer the `trim_level` column when present and fall back to subtitle parsing only when it is null; or drop the hardcoded categories in favor of `trim_level`.
- **Effort:** M

### 13. Remove no-op `initialize_schema` calls from CLI paths
- **Files:** `finnbruktbil/db.py:52-124`, `finnbruktbil/cli/download_data.py:44`, `finnbruktbil/cli/fetch_ids.py:107`
- **Why:** `initialize_schema` is intentionally a no-op (schema is managed manually — documented in CLAUDE.md), yet it is still called in two CLI flows, implying an action that never happens.
- **Approach:** Keep the SQL-in-docstring as the schema source of truth, but drop the runtime calls (or add a one-line comment at each call site noting it is deliberately a no-op).
- **Effort:** S

### 14. Remove checked-in scratch/data artifacts
- **Files:** `data/ids.json`, `progress.md`, `finnbruktbil/prompt.md`
- **Why:** `data/ids.json` is stale output from the legacy `scrape-ids.py`; `progress.md` is a note-to-Codex scratchpad; `finnbruktbil/prompt.md` is the original spec. Shipping `prompt.md` inside the installed package (`finnbruktbil/`) is especially odd. *(Correction: there is no root `prompt.md` — only the one inside the package.)*
- **Approach:** Delete `data/ids.json` and add it to `.gitignore`; move the markdown notes under `docs/` or remove. Confirm nothing imports `finnbruktbil/prompt.md` (nothing does).
- **Effort:** S

### 18. Fix the corrupted `.gitignore` *(added by follow-up review)*
- **Files:** `.gitignore`
- **Why:** Midway through the file, a truncated `local_` line is followed by a literal markdown code fence (```` ``` ````) and a second, pasted-in gitignore body — someone committed a markdown-formatted snippet verbatim. It happens to work today (the duplicate half's `*.db` rule is why `data/finn.db` is untracked), but it's fragile and confusing, and #14 wants to add entries to it.
- **Approach:** Rewrite as a single clean gitignore, keeping the union of rules from both halves (notably `.env`, `*.db`, `.venv/`, `__pycache__/`).
- **Effort:** S

### 15. Guard `aux_data_parser.py`'s `__main__` example against accidental API spend
- **Files:** `finnbruktbil/aux_data_parser.py:256-284`
- **Why:** Running the module directly makes a real (billable) OpenAI call from an example block shipped in the package.
- **Approach:** Move the example to a `docs/`/README snippet, or gate it behind an explicit env flag. Low urgency since it only triggers on manual `python -m`.
- **Effort:** S

### 16. Localize scattered magic values
- **Files:** `finnbruktbil/scraper.py` (SOLGT/"ikke lenger tilgjengelig" XPaths), `finnbruktbil/analysis_app.py` (color maps, `year_min > 1900`)
- **Why:** UI color maps and category orders are repeated inline across the three plot blocks; sentinel year `1900` and status strings are hardcoded in multiple spots. *(Partially done 2026-07-07: `1900` → `MODEL_YEAR_SENTINEL` and the OLS `10`-row minimum → `MIN_OLS_SAMPLES` as part of the #1 baseline.)*
- **Approach:** Hoist the shared `color_discrete_map`/`category_orders` dicts to module constants (naturally falls out of task #3) and name the year sentinel.
- **Effort:** S

---

## Quick wins (< 30 minutes each)

- ~~**#5** — Remove duplicate imports and unused `scipy`/`SCIPY_AVAILABLE` in `analysis_app.py`.~~ ✅ Done (part of #1 baseline).
- **#18** — Rewrite the corrupted `.gitignore` (contains a pasted markdown fence and duplicated body).
- **#6** — Merge the identical `categorize_imported` / `map_import_status` functions.
- **#9** — Strip the phantom `api_key` argument from the two aux-parser docstrings.
- **#11** — Delete the unused `extract_attribute_values` helper.
- **#13** — Drop the no-op `initialize_schema` calls (or annotate them).
- **#14** — Remove `data/ids.json` and the scratch markdown; add `data/ids.json` to `.gitignore`.
- **#4** (partial) — Delete/relocate `scrape-ids.py` and `scrape-articles.py`.
