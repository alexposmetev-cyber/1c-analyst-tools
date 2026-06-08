"""Подсказки по поиску в портале БИТ.Медицина (info.bitmedic.ru)."""

from __future__ import annotations

import re
from typing import Any

BIT_MEDIC_SITE = "https://info.bitmedic.ru/"

BIT_MEDIC_CONFIGURATION_PATTERNS: tuple[str, ...] = (
    r"бит\.?\s*управление\s+медицин",
    r"бит\.?\s*стоматолог",
    r"бит\.?\s*айболит",
    r"бит\.?\s*красот",
    r"бит\.?\s*фитнес",
    r"бит\.?\s*медицин",
    r"bitmedic",
    r"умц",
)


def is_bit_medic_configuration(configuration_name: str) -> bool:
    text = configuration_name.strip().lower()
    if not text:
        return False

    for pattern in BIT_MEDIC_CONFIGURATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def bitmedic_search_guidance(
    query: str,
    *,
    configuration_name: str = "",
) -> dict[str, Any]:
    query = query.strip()
    is_bit = is_bit_medic_configuration(configuration_name)

    guidance_lines = [
        "Порядок: сначала onec_its_search / onec_its_fetch (ИТС).",
    ]

    if is_bit:
        guidance_lines.extend(
            [
                f"Конфигурация отраслевая БИТ — дополнительно ищите на {BIT_MEDIC_SITE}",
                "На info.bitmedic.ru не всегда есть ответы по доработкам; сверяйте с метаданными подключённой базы.",
                f"Рекомендуемый запрос в браузере/поиске: site:info.bitmedic.ru {query}",
            ]
        )
    else:
        guidance_lines.append(
            "Для БИТ.Медицина / Стоматология / Красота / Фитнес — site:info.bitmedic.ru"
        )

    return {
        "source": "bitmedic",
        "configurationName": configuration_name,
        "isBitMedicConfiguration": is_bit,
        "portalUrl": BIT_MEDIC_SITE,
        "query": query,
        "guidance": " ".join(guidance_lines),
        "searchHints": [
            f"{BIT_MEDIC_SITE}",
            f"site:info.bitmedic.ru {query}" if query else "site:info.bitmedic.ru",
        ],
    }
