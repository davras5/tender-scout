#!/usr/bin/env python3
"""
SIMAP Tender Sync Worker

Daily scheduled job that fetches public procurement tenders from the SIMAP API
and syncs them to the Supabase database.

Usage:
    python simap_sync.py --supabase-url URL --supabase-key KEY
    python simap_sync.py --days 7           # Only fetch last 7 days
    python simap_sync.py --type construction # Only fetch construction tenders
    python simap_sync.py --limit 100        # Limit to first 100 tenders (for testing)
    python simap_sync.py --dry-run          # Preview without database writes

Required (via args or environment variables):
    --supabase-url / SUPABASE_URL  - Supabase project URL
    --supabase-key / SUPABASE_KEY  - Supabase service role key (or sb_secret_... key)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import httpx
from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# SIMAP API Configuration
SIMAP_API_BASE = "https://www.simap.ch/api/publications/v2/project"
SIMAP_SEARCH_ENDPOINT = f"{SIMAP_API_BASE}/project-search"

# All project sub-types from SIMAP API
PROJECT_SUB_TYPES = [
    "construction",
    "service",
    "supply",
    "project_competition",
    "idea_competition",
    "overall_performance_competition",
    "project_study",
    "idea_study",
    "overall_performance_study",
    "request_for_information",
]

# Default page size
DEFAULT_PAGE_SIZE = 100


class SimapSyncWorker:
    """Worker class for syncing SIMAP tenders to Supabase."""

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        dry_run: bool = False,
    ):
        """
        Initialize the sync worker.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase service role key
            dry_run: If True, don't write to database
        """
        self.dry_run = dry_run
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.http_client = httpx.Client(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )
        self.stats = {
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "errors": 0,
        }

    def fetch_projects(
        self,
        project_sub_types: Optional[list[str]] = None,
        publication_from: Optional[str] = None,
        publication_until: Optional[str] = None,
        swiss_only: bool = True,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Fetch projects from SIMAP API with pagination.

        Args:
            project_sub_types: List of project sub-types to fetch
            publication_from: Filter by publication date (YYYY-MM-DD)
            publication_until: Filter by publication date (YYYY-MM-DD)
            swiss_only: Only fetch Swiss projects
            limit: Maximum number of projects to fetch (for testing)

        Returns:
            List of project dictionaries
        """
        all_projects = []
        last_item = None

        # Build query parameters
        params = {
            "lang": "de",  # Search in German (primary language)
        }

        if project_sub_types:
            params["projectSubTypes"] = ",".join(project_sub_types)

        if swiss_only:
            params["orderAddressCountryOnlySwitzerland"] = "true"

        if publication_from:
            params["newestPublicationFrom"] = publication_from

        if publication_until:
            params["newestPublicationUntil"] = publication_until

        page = 1
        while True:
            if last_item:
                params["lastItem"] = last_item

            logger.info(f"Fetching page {page}...")

            try:
                response = self.http_client.get(
                    SIMAP_SEARCH_ENDPOINT,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching projects: {e}")
                self.stats["errors"] += 1
                break
            except Exception as e:
                logger.error(f"Error fetching projects: {e}")
                self.stats["errors"] += 1
                break

            projects = data.get("projects", [])
            pagination = data.get("pagination", {})

            if not projects:
                logger.info("No more projects to fetch")
                break

            all_projects.extend(projects)
            self.stats["fetched"] += len(projects)
            logger.info(f"Fetched {len(projects)} projects (total: {len(all_projects)})")

            # Check if we've reached the limit
            if limit and len(all_projects) >= limit:
                all_projects = all_projects[:limit]  # Trim to exact limit
                logger.info(f"Reached limit of {limit} projects")
                break

            # Check for next page
            last_item = pagination.get("lastItem")
            if not last_item:
                break

            page += 1

            # Safety limit to prevent infinite loops
            if page > 1000:
                logger.warning("Reached maximum page limit (1000)")
                break

        return all_projects

    def transform_project(self, project: dict) -> dict:
        """
        Transform SIMAP project data to database schema.

        Args:
            project: Raw project data from SIMAP API

        Returns:
            Transformed data matching tenders table schema
        """
        order_address = project.get("orderAddress") or {}

        # Determine primary language based on which title field has content
        title = project.get("title", {})
        language = "de"
        for lang in ["de", "fr", "it", "en"]:
            if title.get(lang):
                language = lang
                break

        return {
            "external_id": project.get("id"),
            "source": "simap",
            "source_url": f"https://www.simap.ch/project/{project.get('projectNumber')}",
            "title": project.get("title"),
            "project_number": project.get("projectNumber"),
            "publication_number": project.get("publicationNumber"),
            "project_type": project.get("projectType"),
            "project_sub_type": project.get("projectSubType"),
            "process_type": project.get("processType"),
            "lots_type": project.get("lotsType"),
            "authority": project.get("procOfficeName"),
            "publication_date": project.get("publicationDate"),
            "pub_type": project.get("pubType"),
            "corrected": project.get("corrected", False),
            "region": order_address.get("cantonId"),
            "country": order_address.get("countryId", "CH"),
            "order_address": order_address if order_address else None,
            "language": language,
            "raw_data": project,
            "updated_at": datetime.utcnow().isoformat(),
        }

    def upsert_tenders(self, projects: list[dict]) -> None:
        """
        Upsert projects to the tenders table.

        Args:
            projects: List of transformed project data
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would upsert {len(projects)} tenders")
            return

        for project in projects:
            try:
                tender_data = self.transform_project(project)

                # Upsert based on external_id + source
                result = (
                    self.supabase.table("tenders")
                    .upsert(
                        tender_data,
                        on_conflict="external_id,source",
                    )
                    .execute()
                )

                if result.data:
                    self.stats["updated"] += 1
                else:
                    self.stats["inserted"] += 1

            except Exception as e:
                logger.error(f"Error upserting tender {project.get('id')}: {e}")
                self.stats["errors"] += 1

    def update_tender_statuses(self) -> None:
        """
        Update tender statuses based on deadlines.

        - open -> closing_soon (7 days before deadline)
        - closing_soon -> closed (after deadline)
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would update tender statuses")
            return

        now = datetime.utcnow()
        closing_soon_threshold = now + timedelta(days=7)

        try:
            # Mark as closing_soon (deadline within 7 days)
            self.supabase.table("tenders").update({
                "status": "closing_soon",
                "status_changed_at": now.isoformat(),
            }).eq("status", "open").lt(
                "deadline", closing_soon_threshold.isoformat()
            ).gte("deadline", now.isoformat()).execute()

            # Mark as closed (deadline passed)
            self.supabase.table("tenders").update({
                "status": "closed",
                "status_changed_at": now.isoformat(),
            }).in_("status", ["open", "closing_soon"]).lt(
                "deadline", now.isoformat()
            ).execute()

            logger.info("Updated tender statuses")

        except Exception as e:
            logger.error(f"Error updating tender statuses: {e}")
            self.stats["errors"] += 1

    def run(
        self,
        project_sub_types: Optional[list[str]] = None,
        days_back: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        Run the sync process.

        Args:
            project_sub_types: Specific types to sync (default: all)
            days_back: Only fetch publications from last N days
            limit: Maximum number of projects to fetch (for testing)

        Returns:
            Statistics dictionary
        """
        logger.info("=" * 60)
        logger.info("SIMAP Tender Sync Worker")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("DRY RUN MODE - No database writes will be performed")

        if limit:
            logger.info(f"LIMIT MODE - Will fetch maximum {limit} projects")

        # Calculate date range
        publication_from = None
        publication_until = None

        if days_back:
            publication_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            logger.info(f"Fetching publications from {publication_from}")

        # Use all types if not specified
        types_to_fetch = project_sub_types or PROJECT_SUB_TYPES
        logger.info(f"Project types: {', '.join(types_to_fetch)}")

        # Fetch projects
        projects = self.fetch_projects(
            project_sub_types=types_to_fetch,
            publication_from=publication_from,
            publication_until=publication_until,
            limit=limit,
        )

        if projects:
            logger.info(f"Total projects fetched: {len(projects)}")

            # Upsert to database
            self.upsert_tenders(projects)

            # Update statuses
            self.update_tender_statuses()

        # Log statistics
        logger.info("-" * 60)
        logger.info("Sync Statistics:")
        logger.info(f"  Fetched:  {self.stats['fetched']}")
        logger.info(f"  Inserted: {self.stats['inserted']}")
        logger.info(f"  Updated:  {self.stats['updated']}")
        logger.info(f"  Errors:   {self.stats['errors']}")
        logger.info("=" * 60)

        return self.stats

    def close(self):
        """Clean up resources."""
        self.http_client.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync SIMAP tenders to Supabase database"
    )
    parser.add_argument(
        "--supabase-url",
        type=str,
        default=None,
        help="Supabase project URL (or set SUPABASE_URL env var)",
    )
    parser.add_argument(
        "--supabase-key",
        type=str,
        default=None,
        help="Supabase service role key (or set SUPABASE_KEY env var)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only fetch publications from last N days",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=PROJECT_SUB_TYPES,
        action="append",
        dest="types",
        help="Specific project type(s) to sync (can be repeated)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of tenders to fetch (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without database writes",
    )
    args = parser.parse_args()

    # Get Supabase credentials from args or environment variables
    supabase_url = args.supabase_url or os.environ.get("SUPABASE_URL")
    supabase_key = args.supabase_key or os.environ.get("SUPABASE_KEY")

    if not supabase_url:
        logger.error("Missing Supabase URL. Use --supabase-url or set SUPABASE_URL env var")
        sys.exit(1)

    if not supabase_key:
        logger.error("Missing Supabase key. Use --supabase-key or set SUPABASE_KEY env var")
        sys.exit(1)

    # Initialize and run worker
    worker = SimapSyncWorker(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        dry_run=args.dry_run,
    )

    try:
        stats = worker.run(
            project_sub_types=args.types,
            days_back=args.days,
            limit=args.limit,
        )

        # Exit with error code if there were errors
        if stats["errors"] > 0:
            sys.exit(1)

    finally:
        worker.close()


if __name__ == "__main__":
    main()
