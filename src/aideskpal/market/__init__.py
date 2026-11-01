"""Client for the companion market at sickcc.online."""

from __future__ import annotations

from aideskpal.market.client import MarketClient, MarketError
from aideskpal.market.installer import BundleInstaller, InstalledBundle

__all__ = ["MarketClient", "MarketError", "BundleInstaller", "InstalledBundle"]
