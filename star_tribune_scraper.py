#!/usr/bin/env python3
"""
Star Tribune foreclosure scraper.
Fetches foreclosure notices from classifieds.startribune.com for the past 24 hours.
"""

from __future__ import annotations

import csv
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

from gpt_parser import extract_notice_data_gpt
from mullvad_manager import MullvadManager

logger = logging.getLogger(__name__)


@dataclass
class StarTribuneListing:
    notice_id: str
    url: str
    title: str
    posted_text: str
    posted_at: Optional[datetime]


class StarTribuneScraper:
    def __init__(self):
        self.base_url = "https://classifieds.startribune.com"
        self.search_path = "/default/foreclosures/search"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        self.timezone = ZoneInfo("America/Chicago")
        self.scrape_started_at = datetime.now(self.timezone)
        self.cutoff = self.scrape_started_at - timedelta(hours=24)

        self.records_written = 0
        self.results: List[dict] = []

        self.csv_file = None
        self.csv_writer = None
        self.output_path: Optional[str] = None

        # VPN Management - Disabled by default, controlled by MULLVAD_ENABLED env var
        self.vpn_manager = MullvadManager(enabled=False, auto_connect=False)

    def _ensure_vpn(self):
        if hasattr(self, "vpn_manager") and self.vpn_manager.enabled:
            if not self.vpn_manager.ensure_connected():
                logger.warning("⚠️ Could not establish Mullvad VPN connection.")
                logger.warning(
                    "📝 Continuing without VPN may lead to throttling or IP blocks."
                )
            else:
                logger.info(f"✅ VPN ready: {self.vpn_manager.get_status()}")
        else:
            logger.info("🌐 VPN disabled for Star Tribune scraping.")

    def _build_params(self, page: int) -> dict:
        params = {
            "sort_by": "date",
            "order": "desc",
            "limit": "240",
        }
        if page > 1:
            params["p"] = str(page)
        return params

    def _fetch_search_page(self, page: int) -> BeautifulSoup:
        params = self._build_params(page)
        url = urljoin(self.base_url, self.search_path)
        logger.info(f"🌐 Fetching Star Tribune page {page} ({params})")
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _extract_listings(self, soup: BeautifulSoup) -> List[StarTribuneListing]:
        listings: List[StarTribuneListing] = []
        for wrap in soup.select("div.ap_ad_wrap"):
            notice_id = wrap.get("data-id")
            if not notice_id:
                continue

            link_tag = wrap.find("a", href=True)
            if not link_tag:
                continue
            url = urljoin(self.base_url, link_tag["href"])

            title_node = wrap.select_one(".post-summary-title")
            title = (
                title_node.get_text(separator=" ", strip=True) if title_node else "Notice"
            )

            posted_node = wrap.select_one(".post-summary-date")
            posted_text = posted_node.get_text(strip=True) if posted_node else ""
            posted_at = self._parse_posted_online(posted_text)

            listings.append(
                StarTribuneListing(
                    notice_id=notice_id,
                    url=url,
                    title=title,
                    posted_text=posted_text,
                    posted_at=posted_at,
                )
            )

        return listings

    def _parse_posted_online(self, text: str) -> Optional[datetime]:
        if not text:
            return None

        normalized = text.lower().replace("posted online", "").strip()
        if not normalized:
            return None

        now = datetime.now(self.timezone)

        if normalized in {"just now", "moments ago"}:
            return now

        quantity_match = re.search(r"(\d+)\s+(minute|hour|day|week)", normalized)
        if quantity_match:
            value = int(quantity_match.group(1))
            unit = quantity_match.group(2)
            if unit.startswith("minute"):
                return now - timedelta(minutes=value)
            if unit.startswith("hour"):
                return now - timedelta(hours=value)
            if unit.startswith("day"):
                return now - timedelta(days=value)
            if unit.startswith("week"):
                return now - timedelta(weeks=value)

        # Phrases like "today at 3:00 PM" or "yesterday at 4:30 AM"
        day_offset = 0
        if "today" in normalized:
            day_offset = 0
        elif "yesterday" in normalized:
            day_offset = 1

        time_match = re.search(
            r"(today|yesterday)?\s*at\s*(\d{1,2}:\d{2}\s*(am|pm))", normalized
        )
        if time_match:
            clock = time_match.group(2)
            parsed_time = datetime.strptime(clock.lower(), "%I:%M %p").time()
            candidate = datetime.combine(
                now.date() - timedelta(days=day_offset), parsed_time, tzinfo=self.timezone
            )
            return candidate

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        return soup.select_one(".ap_paginator_next_page a") is not None

    def _fetch_notice_body(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            logger.error(f"❌ Failed to fetch notice detail {url}: {exc}")
            return None

        detail_soup = BeautifulSoup(response.text, "html.parser")
        container = detail_soup.select_one(".details-body")
        if not container:
            logger.warning(f"⚠️ Could not locate details body for {url}")
            return None

        return container.get_text(separator="\n", strip=True)

    def _init_csv_writer(self):
        csvs_dir = "csvs"
        os.makedirs(csvs_dir, exist_ok=True)

        filename = f"startribune_notices_{self.scrape_started_at.strftime('%Y-%m-%d')}.csv"
        full_path = os.path.join(csvs_dir, filename)

        fieldnames = [
            "first_name",
            "last_name",
            "street",
            "city",
            "state",
            "zip",
            "date_of_sale",
            "plaintiff",
            "link",
            "notice_id",
        ]

        self.output_path = full_path
        self.csv_file = open(full_path, "w", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
        self.csv_writer.writeheader()
        logger.info(f"📄 Writing Star Tribune results to {filename}")

    def _write_record(self, data: dict):
        if self.csv_writer is None:
            raise RuntimeError("CSV writer not initialized")

        self.csv_writer.writerow(data)
        self.csv_file.flush()
        self.records_written += 1

    def _close_csv_writer(self):
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
            logger.info(f"📁 CSV closed after writing {self.records_written} records")

    def _human_delay(self):
        time.sleep(random.uniform(0.5, 1.5))

    def scrape_latest_notices(self):
        logger.info("🚀 Starting Star Tribune foreclosure scrape")
        self._ensure_vpn()
        self._init_csv_writer()

        seen_ids = set()
        page = 1
        stop_due_to_cutoff = False

        while True:
            try:
                soup = self._fetch_search_page(page)
            except Exception as exc:
                logger.error(f"❌ Failed to fetch Star Tribune page {page}: {exc}")
                break

            listings = self._extract_listings(soup)
            if not listings:
                logger.info("ℹ️ No listings found on this page; stopping scrape.")
                break

            logger.info(f"📄 Found {len(listings)} listings on page {page}")

            for listing in listings:
                if listing.notice_id in seen_ids:
                    continue

                posted_at = listing.posted_at or self.scrape_started_at
                if posted_at < self.cutoff:
                    stop_due_to_cutoff = True
                    logger.info(
                        f"⏹️ Reached listings older than 24h ({listing.posted_text}); stopping."
                    )
                    break

                notice_text = self._fetch_notice_body(listing.url)
                if not notice_text:
                    continue

                parsed = extract_notice_data_gpt(notice_text, listing.url)
                parsed["notice_id"] = listing.notice_id
                parsed["link"] = listing.url

                try:
                    self._write_record(parsed)
                    self.results.append(parsed)
                    seen_ids.add(listing.notice_id)
                    logger.info(
                        f"✅ Saved Star Tribune notice {listing.notice_id} ({listing.title})"
                    )
                except Exception as exc:
                    logger.error(f"❌ Failed to write notice {listing.notice_id}: {exc}")

                self._human_delay()

            if stop_due_to_cutoff:
                break

            if not self._has_next_page(soup):
                logger.info("ℹ️ No additional pages found.")
                break

            page += 1
            self._human_delay()

        self._close_csv_writer()
        logger.info(
            f"🏁 Star Tribune scrape finished. Total records written: {self.records_written}"
        )
        if self.output_path:
            logger.info(f"📁 CSV path: {self.output_path}")

    def close(self):
        self._close_csv_writer()
        try:
            self.session.close()
        except Exception:
            pass

        if hasattr(self, "vpn_manager"):
            self.vpn_manager.disconnect()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scraper = StarTribuneScraper()
    try:
        scraper.scrape_latest_notices()
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
