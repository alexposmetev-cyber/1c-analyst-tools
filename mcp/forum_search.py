"""Поиск по форумам и публичным сайтам 1С через DuckDuckGo HTML."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup


def search_forums(
    config: dict[str, Any],
    query: str,
    configuration_name: str = "",
    configuration_version: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("Параметр query не может быть пустым.")

    if limit < 1:
        limit = 1
    if limit > 10:
        limit = 10

    sites = config.get("forum_sites", [])
    if not isinstance(sites, list) or not sites:
        sites = ["infostart.ru", "forum.mista.ru"]

    enriched_query = _build_query(query, configuration_name, configuration_version, sites)
    try:
        raw_results = _duckduckgo_search(config, enriched_query, limit=limit * 2)
    except httpx.HTTPError as exc:
        return {
            "source": "forums",
            "sourceType": "forum",
            "reliability": "indicative",
            "query": query,
            "searchQuery": enriched_query,
            "configurationName": configuration_name.strip(),
            "configurationVersion": configuration_version.strip(),
            "guidance": _forum_guidance(configuration_name, configuration_version),
            "error": f"Ошибка сети при поиске: {exc}",
            "results": [],
        }

    filtered = _filter_forum_results(raw_results, sites, limit=limit)

    return {
        "source": "forums",
        "sourceType": "forum",
        "reliability": "indicative",
        "query": query,
        "searchQuery": enriched_query,
        "configurationName": configuration_name.strip(),
        "configurationVersion": configuration_version.strip(),
        "guidance": _forum_guidance(configuration_name, configuration_version),
        "results": filtered,
    }


def _build_query(
    query: str,
    configuration_name: str,
    configuration_version: str,
    sites: list[Any],
) -> str:
    site_filter = " OR ".join(f"site:{site}" for site in sites[:4])
    parts = [query, "1С"]
    if configuration_name.strip():
        parts.append(configuration_name.strip())
    if configuration_version.strip():
        parts.append(configuration_version.strip())

    return f"({' '.join(parts)}) ({site_filter})"


def _duckduckgo_search(config: dict[str, Any], query: str, limit: int) -> list[dict[str, str]]:
    timeout = float(config.get("timeout_seconds", 30))
    verify = bool(config.get("verify_ssl", True))
    user_agent = str(config.get("user_agent", "onec-analyst-mcp/1.0"))

    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        verify=verify,
        headers={"User-Agent": user_agent},
    ) as client:
        response = client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "b": "", "kl": "ru-ru"},
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []

    for block in soup.select(".result"):
        link = block.select_one("a.result__a")
        if not link or not link.get("href"):
            continue

        url = _normalize_ddg_url(link["href"])
        title = " ".join(link.get_text(" ", strip=True).split())
        snippet_node = block.select_one(".result__snippet")
        snippet = " ".join(snippet_node.get_text(" ", strip=True).split()) if snippet_node else ""

        if not url or not title:
            continue

        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break

    return results


def _normalize_ddg_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href

    if "duckduckgo.com/l/?" in href:
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)

    return href


def _filter_forum_results(
    raw_results: list[dict[str, str]],
    sites: list[Any],
    limit: int,
) -> list[dict[str, str]]:
    allowed = [str(site).lower() for site in sites]
    filtered: list[dict[str, str]] = []

    for item in raw_results:
        url = item.get("url", "")
        host = urllib.parse.urlparse(url).netloc.lower()
        if not any(site in host for site in allowed):
            continue

        filtered.append(
            {
                "title": item.get("title", ""),
                "url": url,
                "snippet": item.get("snippet", ""),
                "sourceType": "forum",
                "reliability": "indicative",
                "caveats": [
                    "Форум — неофициальный источник; решение может относиться к другой конфигурации или релиза.",
                    "Сверяй с ИТС, метаданными текущей базы (onec_metadata_*) и данными запросов.",
                ],
            }
        )

        if len(filtered) >= limit:
            break

    return filtered


def _forum_guidance(configuration_name: str, configuration_version: str) -> str:
    context = ""
    if configuration_name.strip() or configuration_version.strip():
        context = (
            f" Текущий контекст: {configuration_name.strip()} "
            f"{configuration_version.strip()}.".strip()
        )

    return (
        "Результаты форумов используй как гипотезы, не как инструкцию к действию."
        f"{context} "
        "Если в обсуждении другая конфигурация/версия — явно укажи риск неактуальности. "
        "Для методологии и стандартов предпочитай onec_its_search / onec_its_fetch."
    )
