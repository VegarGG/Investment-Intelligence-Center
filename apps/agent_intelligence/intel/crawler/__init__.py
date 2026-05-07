"""Crawler protocol + per-source implementations (workflow 10 §5.2)."""

from .protocol import CrawlerProtocol, InMemoryCrawler

__all__ = ["CrawlerProtocol", "InMemoryCrawler"]
