from typing import Any, Dict

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

        try:
            preview_markdown = clean_df.to_markdown(index=False)
        except Exception:
            if columns:
                header_line = "| " + " | ".join(columns) + " |"
                separator_line = "| " + " | ".join(["---"] * len(columns)) + " |"
                value_lines = [
                    "| " + " | ".join(
                        [str(row.get(col, "")) if row.get(col) is not None else "" for col in columns]
                    ) + " |"
                    for row in rows
                ]
                preview_markdown = "\n".join([header_line, separator_line] + value_lines)
            else:
                preview_markdown = ""

        payload: Dict[str, Any] = {
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(df),
            "truncated": len(df) > len(rows),
            "preview_markdown": preview_markdown,
            "project_ids": project_ids,
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
