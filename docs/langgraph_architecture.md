# LangGraph Architecture (Silver Land Concierge)

```mermaid
flowchart TD
    UI[Frontend\nindex.html] -->|POST /api/agents/chat\nconversation_id| API
    subgraph Django/Ninja
        API[agents/api.py\nNinja endpoint] -->|thread_id config| Graph
        API -->|guard if no tools| Guard
    end

    subgraph LangGraph Agent (deterministic)
        Intent(Intent node\nextract_intent_filters\n+ lead capture) -->|booking intent| Book
        Intent -->|greeting/off-topic| Guard
        Intent --> SQL(SQL node\nexecute_sql_query)

        SQL -->|detail ask + project/shortlist| Detail
        SQL -->|investment intent| Invest
        SQL -->|comparison intent| Compare
        SQL -->|otherwise| UIshort

        Detail -->|booking intent| Book
        Detail --> UIshort

        UIshort(UI sync\nupdate_ui_context\nshortlist + preview) --> Respond
        Invest(analyze_investment) --> Respond
        Compare(compare_properties) --> Respond
        Book(book_viewing\nlead upsert) --> END
        Respond --> END
    end
```

## Per-turn flow
1. **Intent**: extracts project/developer/city/price/beds/type/features, detail-vs-listing flag (LLM+heuristics), greeting/off-topic, investment/comparison, lead name/email. Non-detail queries clear stale detail/selection. Lead is upserted immediately when an email is present.
2. **Routing after intent**:
   - Booking intent → **Book** (direct, no LLM).
   - Greeting/off-topic → **Guard** (polite nudge).
   - Else → **SQL**.
3. **SQL node**: Vanna text-to-SQL with like-search for project/dev/features. Builds rows/project_ids/preview, shortlist, and name sample logging.
4. **Routing after SQL**:
   - Detail ask + project/shortlist → **Detail**.
   - Investment intent → **Invest**.
   - Comparison intent → **Compare**.
   - Else → **UI** (sync shortlist/preview to frontend).
5. **Detail node**: best-match row by project name (normalized) from current SQL rows; else direct fetch; skips “project name not available”; if no match, stays listing.
6. **Investment/Comparison nodes**: call tools with selected/shortlist ids.
7. **Respond**:
   - If booking payload exists, returns confirmation directly.
   - Detail mode: uses only the selected project row (all columns) for amenity/column answers.
   - Listing: concise top samples; full rows go via `data_sync` for UI “Show all rows”.
8. **API extraction**: always returns `data` (rows/detail/preview/shortlist) when `data_sync` is sent; preview/citations/tools_used surfaced for UI.

## Tool roles
- `extract_intent_filters`: filters + intent flags + lead parsing.
- `execute_sql_query`: Vanna SQL rows + preview + project_ids.
- `fetch_project_row`: for semntic serach queries RAG alternative no cost involved ,single project with all columns (amenities/description).
- `update_ui_context`: sync shortlist to UI.
- `book_viewing`: upserts lead and creates visit_bookings; confirmation returned directly.
- `analyze_investment`: computes price-per-sqm, yield heuristic, score for 1–3 projects.
- `compare_properties`: compares selected ids with key metrics + preview table.

## UX notes
- Booking confirmations bypass the LLM; missing project/email prompts are shown as plain text.
- Detail questions route to detail node via LLM intent `question_type`/`is_detail` or heuristics.
- Listing answers stay small; UI renders full tables via `data_sync` with “Show all rows” toggle.
