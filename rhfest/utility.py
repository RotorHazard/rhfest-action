"""Utility functions for rhfest."""

import requests
from const import LOGGER


def fetch_categories(url: str) -> list[str]:
    """Fetch the allowed categories from the given URL.

    Args:
    ----
        url (str): The URL to fetch the categories from.

    Returns:
    -------
        list: The allowed categories.

    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        LOGGER.exception("Failed to fetch allowed categories")
        return []
