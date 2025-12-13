import json
import urllib.parse
import urllib.request
from langchain_core.tools import tool


def _duckduckgo_search(query: str, max_results: int = 5):
    """
    Query DuckDuckGo Instant Answer API (no API key needed).
    Returns a list of (text, url) tuples.
    """
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_redirect=1&no_html=1"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return [], f"Web search failed: {e}"

    results = []
    # Abstract/Heading first
    abstract = data.get("AbstractText") or ""
    abstract_url = data.get("AbstractURL") or data.get("Redirect") or ""
    if abstract:
        results.append((abstract, abstract_url))

    # Related topics
    related = data.get("RelatedTopics") or []
    for item in related:
        if isinstance(item, dict) and item.get("Text"):
            results.append((item.get("Text", ""), item.get("FirstURL", "")))
        elif isinstance(item, dict) and item.get("Topics"):
            for sub in item.get("Topics", []):
                if sub.get("Text"):
                    results.append((sub.get("Text", ""), sub.get("FirstURL", "")))
        if len(results) >= max_results:
            break

    return results[:max_results], None


@tool
def web_search(query: str):
    """
    Real web search via DuckDuckGo (no API key).
    Use this for questions about nearby amenities (schools/hospitals/transport), or anything not in the DB.
    """
    results, err = _duckduckgo_search(query, max_results=5)
    if err:
        return f"Could not search the web: {err}"
    if not results:
        return "No web results found."

    summary_lines = ["🌐 Web findings:"]
    for i, (text, url) in enumerate(results, 1):
        summary_lines.append(f"{i}. {text} ({url})")
    summary_lines.append("\nTip: If you need nearest schools/airports/metro with distance, include the city or project name in the query.")
    return "\n".join(summary_lines)
