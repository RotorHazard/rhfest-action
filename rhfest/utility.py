"""Utility functions for rhfest."""

import logging

import requests


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
        logging.exception("Failed to fetch allowed categories")
        return []
