"""Клиент 1С:ИТС — CAS-авторизация, поиск, загрузка страниц."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup

ITS_BASE = "https://its.1c.ru"

ITS_DATABASES: dict[str, str] = {
    "v8std": "Стандарты разработки (v8std)",
    "v8doc": "Документация платформы (v8doc)",
    "methodolog": "Методическая поддержка (methodolog)",
    "bsp311": "Библиотека стандартных подсистем (bsp311)",
    "erp25": "1C:ERP (erp25)",
    "ut115": "1C:УТ 11.5 (ut115)",
    "unf30": "1C:УНФ 3.0 (unf30)",
}


class ItsClient:
    def __init__(self, config: dict[str, Any]) -> None:
        its = config.get("its", {})
        if not isinstance(its, dict):
            its = {}

        self._user = str(its.get("user", "")).strip()
        self._password = str(its.get("password", "")).strip()
        self._login_url = str(its.get("login_url", "https://login.1c.ru/login")).strip()
        self._service_url = str(its.get("service_url", "https://its.1c.ru/login/cas")).strip()
        self._timeout = float(config.get("timeout_seconds", 30))
        self._verify = bool(config.get("verify_ssl", True))
        self._user_agent = str(config.get("user_agent", "onec-analyst-mcp/1.0"))

        self._client = httpx.Client(
            follow_redirects=True,
            timeout=self._timeout,
            verify=self._verify,
            headers={"User-Agent": self._user_agent},
        )
        self._authenticated = False

    @property
    def credentials_configured(self) -> bool:
        return bool(self._user) and bool(self._password)

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def close(self) -> None:
        self._client.close()

    def authenticate(self) -> dict[str, Any]:
        if not self.credentials_configured:
            return {
                "ok": False,
                "message": (
                    "Учётные данные ИТС не заданы. "
                    "AGENT_ACTION: спроси у пользователя логин и пароль портала 1С:ИТС, "
                    "затем onec_its_configure."
                ),
            }

        entry_url = f"{ITS_BASE}/db/v8std"
        response = self._client.get(entry_url)
        login_response = self._submit_login_form(response)

        if not self._looks_authenticated(login_response):
            return {
                "ok": False,
                "message": (
                    "Не удалось авторизоваться на its.1c.ru. "
                    "Проверьте логин/пароль ИТС и доступ к порталу."
                ),
                "final_url": str(login_response.url),
            }

        self._authenticated = True
        return {"ok": True, "message": "Авторизация ИТС успешна."}

    def search(self, query: str, database: str = "v8std", limit: int = 5) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Параметр query не может быть пустым.")

        database = database.strip().lower() or "v8std"
        if database not in ITS_DATABASES:
            allowed = ", ".join(sorted(ITS_DATABASES))
            raise ValueError(f"Неизвестная база ИТС: {database}. Допустимо: {allowed}")

        if not self._authenticated:
            auth = self.authenticate()
            if not auth.get("ok"):
                return {
                    "source": "its",
                    "query": query,
                    "database": database,
                    "databaseTitle": ITS_DATABASES[database],
                    "authenticated": False,
                    "error": auth.get("message", "Ошибка авторизации"),
                    "results": [],
                }

        search_url = f"{ITS_BASE}/db/{database}/search"
        response = self._client.get(search_url, params={"query": query})
        results = self._parse_search_results(response.text, limit=limit)

        if not results:
            fallback_url = f"{ITS_BASE}/search"
            fallback = self._client.get(fallback_url, params={"q": query})
            results = self._parse_search_results(fallback.text, limit=limit, base_url=ITS_BASE)

        return {
            "source": "its",
            "sourceType": "its",
            "reliability": "authoritative",
            "query": query,
            "database": database,
            "databaseTitle": ITS_DATABASES[database],
            "authenticated": True,
            "results": results,
        }

    def fetch(self, url: str, max_chars: int = 12000) -> dict[str, Any]:
        url = url.strip()
        if not url:
            raise ValueError("Параметр url не может быть пустым.")

        if url.startswith("/"):
            url = f"{ITS_BASE}{url}"
        elif not url.lower().startswith("http"):
            url = f"{ITS_BASE}/{url.lstrip('/')}"

        if not self._authenticated and "its.1c.ru" in url.lower():
            auth = self.authenticate()
            if not auth.get("ok"):
                return {
                    "source": "its",
                    "url": url,
                    "authenticated": False,
                    "error": auth.get("message", "Ошибка авторизации"),
                    "text": "",
                }

        response = self._client.get(url)
        title, text = self._extract_page_text(response.text)
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n\n[... обрезано ...]"

        return {
            "source": "its",
            "sourceType": "its",
            "reliability": "authoritative",
            "url": str(response.url),
            "title": title,
            "text": text,
            "truncated": truncated,
            "status_code": response.status_code,
        }

    def _submit_login_form(self, response: httpx.Response) -> httpx.Response:
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        if not form:
            service = urllib.parse.quote(self._service_url, safe="")
            login_page = self._client.get(f"{self._login_url}?service={service}")
            soup = BeautifulSoup(login_page.text, "html.parser")
            form = soup.find("form")
            if not form:
                return response

        action = form.get("action") or self._login_url
        if action.startswith("/"):
            parsed = urllib.parse.urlparse(str(response.url))
            action = f"{parsed.scheme}://{parsed.netloc}{action}"
        elif not action.lower().startswith("http"):
            action = urllib.parse.urljoin(str(response.url), action)

        payload: dict[str, str] = {}
        for field in form.find_all("input"):
            name = field.get("name")
            if not name:
                continue
            payload[name] = field.get("value", "")

        payload["username"] = self._user
        payload["password"] = self._password
        payload["_eventId"] = payload.get("_eventId") or "submit"

        return self._client.post(action, data=payload)

    def _looks_authenticated(self, response: httpx.Response) -> bool:
        url = str(response.url).lower()
        text = response.text.lower()

        if "login.1c.ru" in url and "username" in text and "password" in text:
            return False

        if "its.1c.ru" in url:
            if "logout" in text or "выход" in text or "w_content" in text or "db/" in url:
                return True

        return "its.1c.ru" in url and response.status_code == 200

    def _parse_search_results(
        self,
        html: str,
        limit: int,
        base_url: str = ITS_BASE,
    ) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, str]] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            title = " ".join(link.get_text(" ", strip=True).split())
            if not title or len(title) < 4:
                continue

            if href.startswith("/"):
                url = f"{base_url}{href}"
            elif href.lower().startswith("http"):
                url = href
            else:
                url = urllib.parse.urljoin(base_url + "/", href)

            if "its.1c.ru" not in url.lower():
                continue

            if not re.search(r"/db/|/content/|hdoc", url, re.IGNORECASE):
                continue

            if url in seen:
                continue

            seen.add(url)
            snippet = self._nearest_snippet(link)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "sourceType": "its",
                    "reliability": "authoritative",
                }
            )

            if len(results) >= limit:
                break

        return results

    def _nearest_snippet(self, link) -> str:
        parent = link.find_parent(["li", "div", "p", "td"])
        if not parent:
            return ""

        text = " ".join(parent.get_text(" ", strip=True).split())
        return text[:300]

    def _extract_page_text(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        content = (
            soup.select_one("#w_content")
            or soup.select_one(".content")
            or soup.select_one("article")
            or soup.body
        )
        if not content:
            return title, ""

        text = "\n".join(line.strip() for line in content.get_text("\n", strip=True).splitlines() if line.strip())
        return title, text
