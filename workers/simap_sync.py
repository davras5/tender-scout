#!/usr/bin/env python3
"""
SIMAP Tender Sync Worker
========================

Daily scheduled job that fetches public procurement tenders from the Swiss SIMAP API
and syncs them to the Supabase database.

Architecture:
    1. Fetch projects from SIMAP API (with pagination)
    2. Transform SIMAP data to match our database schema
    3. Upsert to Supabase 'tenders' table (insert new, update existing)
    4. Update tender statuses based on deadlines

SIMAP API Documentation:
    https://www.simap.ch/api-doc/#/publications/getPublicProjectSearch

Usage:
    python simap_sync.py --supabase-url URL --supabase-key KEY
    python simap_sync.py --days 7           # Only fetch last 7 days
    python simap_sync.py --type construction # Only fetch construction tenders
    python simap_sync.py --limit 100        # Limit to first 100 tenders (for testing)
    python simap_sync.py --dry-run          # Preview without database writes

Required (via args or environment variables):
    --supabase-url / SUPABASE_URL  - Supabase project URL
    --supabase-key / SUPABASE_KEY  - Supabase service role key (or sb_secret_... key)

Author: Tender Scout Team
Last Updated: 2026-01-19
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import httpx
from supabase import create_client, Client

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
# Default logging to stdout - file logging added in main() if needed
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """
    Configure logging with optional file output.

    Args:
        verbose: Enable debug level logging
        log_file: Path to log file (errors and above go here)
    """
    # Set log level
    log_level = logging.DEBUG if verbose else logging.INFO

    # Console handler - shows INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    handlers = [console_handler]

    # File handler - captures all logs (especially errors for debugging)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Capture everything in file
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,  # Allow all levels, handlers filter
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

# =============================================================================
# SIMAP API CONFIGURATION
# =============================================================================
# SIMAP (Système d'information sur les marchés publics) is the official
# Swiss public procurement platform. The API is public and requires no auth.
# API Docs: https://www.simap.ch/api-doc/

SIMAP_API_BASE = "https://www.simap.ch/api/publications/v2/project"
SIMAP_SEARCH_ENDPOINT = f"{SIMAP_API_BASE}/project-search"

# All project sub-types supported by SIMAP API
# These are used as filter parameters in the API request
# See: https://www.simap.ch/api-doc/#/publications/getPublicProjectSearch
PROJECT_SUB_TYPES = [
    "construction",                      # Construction works (Bauaufträge)
    "service",                           # Service contracts (Dienstleistungen)
    "supply",                            # Supply/goods contracts (Lieferungen)
    "project_competition",               # Project competition
    "idea_competition",                  # Idea competition
    "overall_performance_competition",   # Overall performance competition
    "project_study",                     # Project study
    "idea_study",                        # Idea study
    "overall_performance_study",         # Overall performance study
    "request_for_information",           # Request for information (RFI)
]

# Default page size for API requests (SIMAP default is 20)
DEFAULT_PAGE_SIZE = 100


# =============================================================================
# SIMAP SYNC WORKER CLASS
# =============================================================================
class SimapSyncWorker:
    """
    Worker class for syncing SIMAP tenders to Supabase.

    This class handles:
    - Fetching projects from SIMAP API with pagination
    - Transforming SIMAP data to match our database schema
    - Upserting records to Supabase (insert new, update existing)
    - Updating tender statuses based on deadlines

    Example:
        worker = SimapSyncWorker(supabase_url, supabase_key)
        stats = worker.run(days_back=7, limit=100)
        worker.close()
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        dry_run: bool = False,
    ):
        """
        Initialize the sync worker.

        Args:
            supabase_url: Supabase project URL (e.g., https://xxx.supabase.co)
            supabase_key: Supabase service role key (sb_secret_... or legacy JWT)
            dry_run: If True, fetch from API but don't write to database
        """
        self.dry_run = dry_run

        # Initialize Supabase client
        # Uses service role key to bypass RLS for server-side operations
        self.supabase: Client = create_client(supabase_url, supabase_key)

        # Initialize HTTP client for SIMAP API requests
        # 30 second timeout should be sufficient for API responses
        self.http_client = httpx.Client(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

        # Statistics for logging and monitoring
        self.stats = {
            "fetched": 0,   # Total projects fetched from SIMAP
            "inserted": 0,  # New tenders inserted
            "updated": 0,   # Existing tenders updated
            "errors": 0,    # Errors encountered
        }

    # -------------------------------------------------------------------------
    # FETCH PROJECTS FROM SIMAP API
    # -------------------------------------------------------------------------
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

        SIMAP uses "rolling pagination" with a lastItem cursor.
        The cursor format is: YYYYMMDD|projectNumber

        Args:
            project_sub_types: List of project sub-types to fetch (default: all)
            publication_from: Filter by publication date from (YYYY-MM-DD)
            publication_until: Filter by publication date until (YYYY-MM-DD)
            swiss_only: Only fetch Swiss projects (recommended)
            limit: Maximum number of projects to fetch (for testing)

        Returns:
            List of project dictionaries from SIMAP API
        """
        all_projects = []
        last_item = None  # Pagination cursor

        # Build query parameters
        # Note: SIMAP API requires at least one filter parameter
        params = {
            "lang": "de",  # Search in German (primary language in Switzerland)
        }

        # Add project type filter (required by API)
        if project_sub_types:
            params["projectSubTypes"] = ",".join(project_sub_types)

        # Filter to Swiss projects only (recommended to avoid irrelevant results)
        if swiss_only:
            params["orderAddressCountryOnlySwitzerland"] = "true"

        # Date range filters for incremental sync
        if publication_from:
            params["newestPublicationFrom"] = publication_from

        if publication_until:
            params["newestPublicationUntil"] = publication_until

        # Pagination loop
        page = 1
        while True:
            # Add pagination cursor for subsequent pages
            if last_item:
                params["lastItem"] = last_item

            logger.info(f"Fetching page {page}...")

            # Make API request
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

            # Extract projects and pagination info from response
            projects = data.get("projects", [])
            pagination = data.get("pagination", {})

            # No more projects to fetch
            if not projects:
                logger.info("No more projects to fetch")
                break

            # Add projects to result list
            all_projects.extend(projects)
            self.stats["fetched"] += len(projects)
            logger.info(f"Fetched {len(projects)} projects (total: {len(all_projects)})")

            # Check if we've reached the limit (for testing)
            if limit and len(all_projects) >= limit:
                all_projects = all_projects[:limit]  # Trim to exact limit
                logger.info(f"Reached limit of {limit} projects")
                break

            # Get pagination cursor for next page
            # Format: YYYYMMDD|projectNumber (e.g., "20260119|26624")
            last_item = pagination.get("lastItem")
            if not last_item:
                break  # No more pages

            page += 1

            # Safety limit to prevent infinite loops
            if page > 1000:
                logger.warning("Reached maximum page limit (1000)")
                break

        return all_projects

    # -------------------------------------------------------------------------
    # TRANSFORM SIMAP DATA TO DATABASE SCHEMA
    # -------------------------------------------------------------------------
    def transform_project(self, project: dict) -> dict:
        """
        Transform SIMAP project data to our database schema.

        SIMAP API returns multilingual fields as objects:
            {"de": "...", "en": null, "fr": "...", "it": null}

        We store these directly as JSONB in the database.

        Args:
            project: Raw project data from SIMAP API

        Returns:
            Transformed data matching tenders table schema
        """
        # Extract order address (may be null)
        order_address = project.get("orderAddress") or {}

        # Determine primary language based on which title field has content
        # Priority: de > fr > it > en (Swiss language preference)
        title = project.get("title", {})
        language = "de"  # Default to German
        for lang in ["de", "fr", "it", "en"]:
            if title.get(lang):
                language = lang
                break

        # Map SIMAP fields to our database schema
        # See documentation/DATABASE.md for schema details
        return {
            # Identifiers
            "external_id": project.get("id"),           # SIMAP project UUID
            "source": "simap",                          # Data source identifier
            "source_url": f"https://www.simap.ch/project/{project.get('projectNumber')}",

            # Project info (multilingual fields stored as JSONB)
            "title": project.get("title"),              # {"de": "...", "fr": "...", ...}
            "project_number": project.get("projectNumber"),
            "publication_number": project.get("publicationNumber"),
            "project_type": project.get("projectType"),         # tender, competition, study
            "project_sub_type": project.get("projectSubType"),  # construction, service, supply
            "process_type": project.get("processType"),         # open, selective, invitation, direct
            "lots_type": project.get("lotsType"),               # with, without

            # Authority info (multilingual)
            "authority": project.get("procOfficeName"),  # {"de": "...", "fr": "...", ...}

            # Publication info
            "publication_date": project.get("publicationDate"),
            "pub_type": project.get("pubType"),          # tender, award, revocation, etc.
            "corrected": project.get("corrected", False),

            # Location info
            "region": order_address.get("cantonId"),     # Canton code: BE, ZH, etc.
            "country": order_address.get("countryId", "CH"),
            "order_address": order_address if order_address else None,

            # Metadata
            "language": language,
            "raw_data": project,                         # Store original for debugging
            "updated_at": datetime.utcnow().isoformat(),
        }

    # -------------------------------------------------------------------------
    # UPSERT TENDERS TO DATABASE
    # -------------------------------------------------------------------------
    def upsert_tenders(self, projects: list[dict]) -> None:
        """
        Upsert projects to the tenders table.

        Uses Supabase upsert with conflict handling on (external_id, source).
        This ensures:
        - New tenders are inserted
        - Existing tenders are updated with latest data
        - No duplicates are created

        Args:
            projects: List of raw project data from SIMAP API
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would upsert {len(projects)} tenders")
            return

        for project in projects:
            try:
                # Transform SIMAP data to our schema
                tender_data = self.transform_project(project)

                # Upsert to database
                # on_conflict specifies the unique constraint columns
                result = (
                    self.supabase.table("tenders")
                    .upsert(
                        tender_data,
                        on_conflict="external_id,source",
                    )
                    .execute()
                )

                # Track statistics
                if result.data:
                    self.stats["updated"] += 1
                else:
                    self.stats["inserted"] += 1

            except Exception as e:
                # Log detailed error information for debugging
                project_id = project.get('id', 'unknown')
                project_number = project.get('projectNumber', 'unknown')
                logger.error(f"Error upserting tender {project_number} (ID: {project_id}): {type(e).__name__}: {e}")

                # Log the tender data that failed (truncated for readability)
                try:
                    tender_data = self.transform_project(project)
                    logger.debug(f"Failed tender data: {tender_data}")
                except Exception:
                    pass

                self.stats["errors"] += 1

    # -------------------------------------------------------------------------
    # UPDATE TENDER STATUSES
    # -------------------------------------------------------------------------
    def update_tender_statuses(self) -> None:
        """
        Update tender statuses based on deadlines.

        Status transitions:
        - open -> closing_soon (7 days before deadline)
        - closing_soon -> closed (after deadline)

        Note: This only updates tenders that have a deadline set.
        Many SIMAP tenders don't include deadline in the search results.
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would update tender statuses")
            return

        now = datetime.utcnow()
        closing_soon_threshold = now + timedelta(days=7)

        try:
            # Mark as closing_soon (deadline within 7 days but not yet passed)
            self.supabase.table("tenders").update({
                "status": "closing_soon",
                "status_changed_at": now.isoformat(),
            }).eq("status", "open").lt(
                "deadline", closing_soon_threshold.isoformat()
            ).gte("deadline", now.isoformat()).execute()

            # Mark as closed (deadline has passed)
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

    # -------------------------------------------------------------------------
    # MAIN RUN METHOD
    # -------------------------------------------------------------------------
    def run(
        self,
        project_sub_types: Optional[list[str]] = None,
        days_back: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        Run the complete sync process.

        Steps:
        1. Fetch projects from SIMAP API
        2. Upsert to database
        3. Update tender statuses

        Args:
            project_sub_types: Specific types to sync (default: all types)
            days_back: Only fetch publications from last N days
            limit: Maximum number of projects to fetch (for testing)

        Returns:
            Statistics dictionary with fetched/inserted/updated/errors counts
        """
        # Log start
        logger.info("=" * 60)
        logger.info("SIMAP Tender Sync Worker")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("DRY RUN MODE - No database writes will be performed")

        if limit:
            logger.info(f"LIMIT MODE - Will fetch maximum {limit} projects")

        # Calculate date range for incremental sync
        publication_from = None
        publication_until = None

        if days_back:
            publication_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            logger.info(f"Fetching publications from {publication_from}")

        # Use all types if not specified
        types_to_fetch = project_sub_types or PROJECT_SUB_TYPES
        logger.info(f"Project types: {', '.join(types_to_fetch)}")

        # Step 1: Fetch projects from SIMAP API
        projects = self.fetch_projects(
            project_sub_types=types_to_fetch,
            publication_from=publication_from,
            publication_until=publication_until,
            limit=limit,
        )

        if projects:
            logger.info(f"Total projects fetched: {len(projects)}")

            # Step 2: Upsert to database
            self.upsert_tenders(projects)

            # Step 3: Update statuses based on deadlines
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
        """Clean up resources (HTTP client)."""
        self.http_client.close()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def main():
    """
    Main entry point for CLI usage.

    Parses command line arguments and runs the sync worker.
    Credentials can be passed via args or environment variables.
    """
    parser = argparse.ArgumentParser(
        description="Sync SIMAP tenders to Supabase database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simap_sync.py --supabase-url URL --supabase-key KEY --limit 50 --dry-run
  python simap_sync.py --days 7 --type construction
  python simap_sync.py --limit 100
        """,
    )

    # Supabase credentials (can also use env vars)
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

    # Sync options
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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="simap_sync.log",
        help="Log file path (default: simap_sync.log)",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Disable file logging (only log to console)",
    )

    args = parser.parse_args()

    # Setup logging (file + console)
    log_file = None if args.no_log_file else args.log_file
    setup_logging(verbose=args.verbose, log_file=log_file)

    if log_file:
        logger.info(f"Logging to file: {log_file}")

    # Get Supabase credentials from args or environment variables
    # Args take precedence over env vars
    supabase_url = args.supabase_url or os.environ.get("SUPABASE_URL")
    supabase_key = args.supabase_key or os.environ.get("SUPABASE_KEY")

    # Validate required credentials
    if not supabase_url:
        logger.error("Missing Supabase URL. Use --supabase-url or set SUPABASE_URL env var")
        sys.exit(1)

    if not supabase_key:
        logger.error("Missing Supabase key. Use --supabase-key or set SUPABASE_KEY env var")
        sys.exit(1)

    # Initialize worker
    worker = SimapSyncWorker(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        dry_run=args.dry_run,
    )

    try:
        # Run sync
        stats = worker.run(
            project_sub_types=args.types,
            days_back=args.days,
            limit=args.limit,
        )

        # Exit with error code if there were errors
        # This allows CI/CD pipelines to detect failures
        if stats["errors"] > 0:
            sys.exit(1)

    finally:
        # Always clean up resources
        worker.close()


if __name__ == "__main__":
    main()
