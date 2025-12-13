from typing import Any, Dict
import io
import contextlib

from langchain_core.tools import tool

from helpers.vanna import get_vanna_client

MAX_ROWS_RETURNED = 50


@tool
def execute_sql_query(query: str) -> Dict[str, Any]:
    """
    Execute a natural language query against the property database using Text-to-SQL (Vanna AI).
    Returns structured rows so the supervisor LLM can format tables/streams for the user.

    Examples:
    - "Find 2 bedroom apartments in Dubai"
    - "Show properties under 500000"
    - "List all villas"
    """
    sql = None
    try:
        vn = get_vanna_client()
        # Suppress noisy library prints during generation/execute
        with contextlib.redirect_stdout(io.StringIO()):
            sql = vn.generate_sql(query)

        if not sql:
            return {
                "error": "Could not generate SQL for the query.",
                "sql": sql,
                "rows": [],
                "columns": [],
                "row_count": 0,
                "truncated": False,
                "project_ids": [],
            }

        with contextlib.redirect_stdout(io.StringIO()):
            df = vn.run_sql(sql)
        if df is None:
            return {"sql": sql, "rows": [], "columns": [], "row_count": 0, "truncated": False, "project_ids": []}

        df = df.where(df.notnull(), None)
        columns = list(df.columns)
        if df.empty:
            return {
                "sql": sql,
                "rows": [],
                "columns": columns,
                "row_count": 0,
                "truncated": False,
                "project_ids": [],
            }

        limited_df = df.head(MAX_ROWS_RETURNED)
        clean_df = limited_df.copy()
        if "id" in clean_df.columns:
            clean_df["id"] = clean_df["id"].apply(lambda value: str(value) if value is not None else None)
        rows = clean_df.to_dict(orient="records")
        project_ids = [row["id"] for row in rows if row.get("id")]

        # Build a compact preview table only when we have shortlist/project_ids
        preview_cols = [c for c in ["id", "name", "city", "property_type", "bedrooms", "price", "status"] if c in columns]
        preview_markdown = ""
        if preview_cols and project_ids:
            filtered_df = clean_df[clean_df["id"].isin(project_ids)].copy()
            if not filtered_df.empty:
                # Reorder to match project_ids sequence
                filtered_df["__order"] = filtered_df["id"].apply(lambda x: project_ids.index(x) if x in project_ids else len(project_ids))
                filtered_df = filtered_df.sort_values("__order")
                max_preview_rows = len(project_ids)
                try:
                    preview_df = filtered_df.head(max_preview_rows)[preview_cols]
                    preview_markdown = preview_df.to_markdown(index=False)
                except Exception:
                    header_line = "| " + " | ".join(preview_cols) + " |"
                    separator_line = "| " + " | ".join(["---"] * len(preview_cols)) + " |"
                    value_lines = []
                    subset_rows = filtered_df.head(max_preview_rows).to_dict(orient="records")
                    for row in subset_rows:
                        values = []
                        for col in preview_cols:
                            val = row.get(col)
                            values.append(str(val) if val is not None else "")
                        value_lines.append("| " + " | ".join(values) + " |")
                    preview_markdown = "\n".join([header_line, separator_line] + value_lines)

        payload: Dict[str, Any] = {
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(df),
            "truncated": len(df) > len(rows),
            "preview_markdown": preview_markdown,
            "project_ids": project_ids,
            "source_tool": "execute_sql_query",
        }

        return payload

    except Exception as e:
        return {
            "error": f"Error executing SQL query: {str(e)}",
            "sql": sql,
            "rows": [],
            "columns": [],
            "row_count": 0,
            "truncated": False,
            "project_ids": [],
        }
