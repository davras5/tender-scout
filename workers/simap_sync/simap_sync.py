#!/usr/bin/env python3
"""
SIMAP Tender Sync Worker
========================

Daily scheduled job that fetches public procurement tenders from the Swiss SIMAP API
and syncs them to the Supabase database.

Architecture:
    1. Fetch projects from SIMAP API v2 search endpoint (with pagination)
    2. Transform SIMAP data to match our database schema
    3. Upsert to Supabase 'tenders' table (insert new, update existing)
    4. Update tender statuses based on deadlines
    5. Optionally fetch detailed information from SIMAP API v1 publication-details endpoint

SIMAP API Documentation:
    Search: https://www.simap.ch/api-doc/#/publications/getPublicProjectSearch
    Details: https://www.simap.ch/api/publications/v1/project/{projectId}/publication-details/{publicationId}

Usage Examples:
    # === Setup (choose one method) ===

    # Method 1: Environment variables (recommended for scripts/cron)
    export SUPABASE_URL="https://xxx.supabase.co"
    export SUPABASE_KEY="your-service-role-key"
    python simap_sync.py --days 7

    # Method 2: Command line arguments
    python simap_sync.py --supabase-url URL --supabase-key KEY --days 7

    # === Examples below assume env vars are set ===

    # Daily incremental sync (recommended for scheduled jobs)
    python simap_sync.py --days 1

    # Weekly sync with specific project types
    python simap_sync.py --days 7 --type construction --type service

    # Test run: limited records, no database writes
    python simap_sync.py --limit 10 --details-limit 5 --dry-run

    # Fast sync without details (search data only)
    python simap_sync.py --days 7 --skip-details

    # Backfill details for existing tenders
    python simap_sync.py --details-only --details-limit 100

    # Slow rate limit for API-sensitive operations
    python simap_sync.py --days 7 --rate-limit 2.0

    # Verbose logging with file output
    python simap_sync.py --days 7 --verbose --log-file sync.log

Command Line Options:
    Required (via args or environment variables):
        --supabase-url      Supabase project URL (or SUPABASE_URL env var)
        --supabase-key      Supabase service role key (or SUPABASE_KEY env var)

    Optional - Filtering:
        --days N            Only fetch publications from last N days (default: all)
        --type TYPE         Project type filter, can repeat (default: all types)
                            Values: construction, service, supply, project_competition,
                            idea_competition, overall_performance_competition,
                            project_study, idea_study, overall_performance_study,
                            request_for_information

    Optional - Limits:
        --limit N           Max tenders to fetch from search API (default: unlimited)
        --details-limit N   Max details to fetch from detail API (default: unlimited)

    Optional - Modes:
        --dry-run           Preview without database writes
        --skip-details      Skip fetching publication details (details on by default)
        --details-only      Only fetch details, skip project search

    Optional - Performance:
        --rate-limit N      Delay between detail API calls in seconds (default: 0.5)

    Optional - Logging:
        --verbose, -v       Enable debug logging
        --log-file PATH     Log file path (default: simap_sync.log)
        --no-log-file       Disable file logging (console only)

Author: Tender Scout Team
Last Updated: 2026-01-19
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
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
        log_file: Path to log file (warnings and errors only)
    """
    # Set log level
    log_level = logging.DEBUG if verbose else logging.INFO

    # Console handler - shows INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    handlers = [console_handler]

    # File handler - captures only warnings and errors to keep file size small
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.WARNING)  # Only warnings and errors in file
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

SIMAP_API_BASE_V2 = "https://www.simap.ch/api/publications/v2/project"
SIMAP_API_BASE_V1 = "https://www.simap.ch/api/publications/v1/project"
SIMAP_SEARCH_ENDPOINT = f"{SIMAP_API_BASE_V2}/project-search"

# Detail endpoint uses v1 API: /project/{projectId}/publication-details/{publicationId}
# Example: https://www.simap.ch/api/publications/v1/project/f95391ed-581e-43be-b044-ff7aba5e4b56/publication-details/31194cfe-5d92-4c53-97f0-831447c00c1d

# Rate limiting and retry configuration
DETAIL_API_DELAY_SECONDS = 0.5  # Delay between detail API calls to avoid rate limiting
DETAIL_API_MAX_RETRIES = 3     # Maximum retries for transient failures
DETAIL_API_RETRY_DELAY = 2.0   # Delay between retries (seconds)
DATABASE_BATCH_SIZE = 100       # Batch size for paginated database queries

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
        # Using context manager (recommended)
        with SimapSyncWorker(supabase_url, supabase_key) as worker:
            stats = worker.run(days_back=7, limit=100)

        # Or manual cleanup
        worker = SimapSyncWorker(supabase_url, supabase_key)
        try:
            stats = worker.run(days_back=7, limit=100)
        finally:
            worker.close()
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        dry_run: bool = False,
        detail_api_delay: float = DETAIL_API_DELAY_SECONDS,
    ):
        """
        Initialize the sync worker.

        Args:
            supabase_url: Supabase project URL (e.g., https://xxx.supabase.co)
            supabase_key: Supabase service role key (sb_secret_... or legacy JWT)
            dry_run: If True, fetch from API but don't write to database
            detail_api_delay: Delay in seconds between detail API calls
        """
        self.dry_run = dry_run
        self.detail_api_delay = detail_api_delay

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
            "fetched": 0,           # Total projects fetched from SIMAP search
            "inserted": 0,          # New tenders inserted
            "updated": 0,           # Existing tenders updated
            "details_fetched": 0,   # Details fetched from detail API
            "details_errors": 0,    # Errors fetching details
            "errors": 0,            # General errors encountered
        }

    def __enter__(self):
        """Context manager entry - returns self for use in with statements."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures resources are cleaned up."""
        self.close()
        return False  # Don't suppress exceptions

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
            "updated_at": datetime.now(timezone.utc).isoformat(),

            # Publication ID needed for fetching details
            "publication_id": project.get("publicationId"),
        }

    # -------------------------------------------------------------------------
    # FETCH PUBLICATION DETAILS FROM SIMAP API
    # -------------------------------------------------------------------------
    def fetch_publication_details(self, project_id: str, publication_id: str) -> Optional[dict]:
        """
        Fetch detailed publication information from SIMAP API v1 with retry logic.

        The detail endpoint provides much more information than the search endpoint,
        including: procurement details, terms, dates, criteria, addresses, etc.

        API endpoint:
            GET /api/publications/v1/project/{projectId}/publication-details/{publicationId}

        Args:
            project_id: SIMAP project UUID (e.g., "f95391ed-581e-43be-b044-ff7aba5e4b56")
            publication_id: SIMAP publication UUID (e.g., "31194cfe-5d92-4c53-97f0-831447c00c1d")

        Returns:
            Detail data dictionary if successful, None if failed after retries
        """
        url = f"{SIMAP_API_BASE_V1}/{project_id}/publication-details/{publication_id}"

        for attempt in range(1, DETAIL_API_MAX_RETRIES + 1):
            try:
                response = self.http_client.get(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                # Don't retry on 4xx errors (client errors) except 429 (rate limit)
                if 400 <= status_code < 500 and status_code != 429:
                    logger.warning(f"HTTP {status_code} fetching details for {project_id}/{publication_id}")
                    return None
                # Retry on 429 (rate limit) or 5xx (server errors)
                if attempt < DETAIL_API_MAX_RETRIES:
                    logger.warning(f"HTTP {status_code} fetching details, retrying in {DETAIL_API_RETRY_DELAY}s (attempt {attempt}/{DETAIL_API_MAX_RETRIES})")
                    time.sleep(DETAIL_API_RETRY_DELAY)
                else:
                    logger.warning(f"HTTP {status_code} fetching details for {project_id}/{publication_id} after {attempt} attempts")
                    return None
            except httpx.TimeoutException:
                if attempt < DETAIL_API_MAX_RETRIES:
                    logger.warning(f"Timeout fetching details, retrying in {DETAIL_API_RETRY_DELAY}s (attempt {attempt}/{DETAIL_API_MAX_RETRIES})")
                    time.sleep(DETAIL_API_RETRY_DELAY)
                else:
                    logger.warning(f"Timeout fetching details for {project_id}/{publication_id} after {attempt} attempts")
                    return None
            except Exception as e:
                logger.warning(f"Error fetching details for {project_id}/{publication_id}: {e}")
                return None

        return None

    def transform_publication_details(self, details: dict) -> dict:
        """
        Transform SIMAP publication details to database schema.

        Maps the detailed API response to our extended tenders table columns.
        See documentation/DATABASE.md for full schema details.

        Args:
            details: Raw detail data from SIMAP publication-details API

        Returns:
            Transformed data with detail fields for updating tenders table
        """
        # Extract main sections from detail response
        project_info = details.get("project-info", {})
        procurement = details.get("procurement", {})
        terms = details.get("terms", {})
        dates = details.get("dates", {})
        criteria = details.get("criteria", {})

        # Extract description from procurement section (multilingual)
        description = procurement.get("orderDescription")

        # Extract deadline from dates section
        deadline = dates.get("offerDeadline")

        # Extract offer opening datetime
        offer_opening_data = dates.get("offerOpening", {})
        offer_opening = offer_opening_data.get("dateTime") if offer_opening_data else None

        # Extract Q&A deadlines (array of objects with date and note)
        qna_deadlines = dates.get("qnas", [])

        # Extract offer validity period
        offer_validity_days = dates.get("offerValidityDeadlineDays")

        # Extract classification codes (arrays of {code, label} objects)
        bkp_codes = procurement.get("bkpCodes", [])
        npk_codes = procurement.get("npkCodes", [])
        oag_codes = procurement.get("oagCodes", [])
        additional_cpv_codes = procurement.get("additionalCpvCodes", [])

        # Extract main CPV code if present and not already set
        cpv_code = procurement.get("cpvCode")
        cpv_codes = [cpv_code] if cpv_code else []

        # Extract addresses
        proc_office_address = project_info.get("procOfficeAddress")
        procurement_recipient_address = project_info.get("procurementRecipientAddress")
        offer_address = project_info.get("offerAddress")

        # Extract order address description (multilingual)
        order_address_description = procurement.get("orderAddressDescription")

        # Extract order address for region extraction
        order_address = procurement.get("orderAddress", {})

        # Extract language arrays
        documents_languages = project_info.get("documentsLanguages", [])
        offer_languages = project_info.get("offerLanguages", [])
        publication_languages = project_info.get("publicationLanguages", [])
        offer_types = project_info.get("offerTypes", [])

        # Extract yes/no/not_specified fields
        variants_allowed = procurement.get("variants")
        partial_offers_allowed = procurement.get("partialOffers")
        consortium_allowed = terms.get("consortiumAllowed")
        subcontractor_allowed = terms.get("subContractorAllowed")

        # Extract execution timeline
        execution_deadline_type = procurement.get("executionDeadlineType")
        execution_period = procurement.get("executionPeriod")
        execution_days = procurement.get("executionDays")

        # Extract criteria arrays
        qualification_criteria = criteria.get("qualificationCriteria", [])
        award_criteria = criteria.get("awardCriteria", [])

        # Extract lots array
        lots = details.get("lots", [])

        return {
            # Dates
            "deadline": deadline,
            "offer_opening": offer_opening,
            "qna_deadlines": qna_deadlines if qna_deadlines else [],
            "offer_validity_days": offer_validity_days,

            # Description
            "description": description,

            # Classification codes
            "cpv_codes": cpv_codes if cpv_codes else [],
            "bkp_codes": bkp_codes if bkp_codes else [],
            "npk_codes": npk_codes if npk_codes else [],
            "oag_codes": oag_codes if oag_codes else [],
            "additional_cpv_codes": additional_cpv_codes if additional_cpv_codes else [],

            # Addresses
            "proc_office_address": proc_office_address,
            "procurement_recipient_address": procurement_recipient_address,
            "offer_address": offer_address,
            "order_address_description": order_address_description,

            # Update region from detail if available
            "region": order_address.get("cantonId") if order_address else None,
            "country": order_address.get("countryId") if order_address else None,

            # Languages and offer types
            "documents_languages": documents_languages if documents_languages else [],
            "offer_languages": offer_languages if offer_languages else [],
            "publication_languages": publication_languages if publication_languages else [],
            "offer_types": offer_types if offer_types else [],
            "documents_source_type": project_info.get("documentsSourceType"),

            # Project info flags
            "state_contract_area": project_info.get("stateContractArea", False),
            "publication_ted": project_info.get("publicationTed", False),

            # Procurement details
            "construction_type": procurement.get("constructionType"),
            "construction_category": procurement.get("constructionCategory"),
            "variants_allowed": variants_allowed,
            "partial_offers_allowed": partial_offers_allowed,
            "execution_deadline_type": execution_deadline_type,
            "execution_period": execution_period,
            "execution_days": execution_days,

            # Terms
            "consortium_allowed": consortium_allowed,
            "subcontractor_allowed": subcontractor_allowed,
            "terms_type": terms.get("termsType"),
            "remedies_notice": terms.get("remediesNotice"),

            # Criteria
            "qualification_criteria": qualification_criteria if qualification_criteria else [],
            "award_criteria": award_criteria if award_criteria else [],

            # Lots
            "lots": lots if lots else [],

            # Documents
            "has_project_documents": details.get("hasProjectDocuments", False),

            # Raw detail data for debugging
            "raw_detail_data": details,

            # Track when details were fetched
            "details_fetched_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_and_update_details(
        self,
        tender_id: str,
        external_id: str,
        publication_id: str,
    ) -> bool:
        """
        Fetch publication details and update the tender record.

        Args:
            tender_id: Database tender UUID
            external_id: SIMAP project UUID (used as external_id)
            publication_id: SIMAP publication UUID

        Returns:
            True if details were successfully fetched and updated, False otherwise
        """
        if not external_id or not publication_id:
            logger.debug(f"Missing project_id or publication_id for tender {tender_id}")
            return False

        # Fetch details from SIMAP API
        details = self.fetch_publication_details(external_id, publication_id)
        if not details:
            self.stats["details_errors"] += 1
            return False

        # Transform to database format
        detail_data = self.transform_publication_details(details)

        # Filter out None values to avoid overwriting existing data with nulls
        detail_data = {k: v for k, v in detail_data.items() if v is not None}

        try:
            # Update tender with detail data
            self.supabase.table("tenders").update(detail_data).eq("id", tender_id).execute()
            self.stats["details_fetched"] += 1
            return True
        except Exception as e:
            logger.error(f"Error updating tender {tender_id} with details: {e}")
            self.stats["details_errors"] += 1
            return False

    def fetch_details_for_tenders(
        self,
        limit: Optional[int] = None,
        only_missing: bool = True,
    ) -> None:
        """
        Fetch publication details for tenders that don't have them yet.

        This method queries the database for tenders missing details in batches
        and fetches them from the SIMAP API with rate limiting.

        Args:
            limit: Maximum number of tenders to fetch details for
            only_missing: If True, only fetch for tenders without details_fetched_at
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would fetch tender details")
            return

        logger.info("Fetching publication details for tenders...")

        total_processed = 0
        offset = 0

        try:
            while True:
                # Calculate batch size respecting overall limit
                batch_size = DATABASE_BATCH_SIZE
                if limit:
                    remaining = limit - total_processed
                    if remaining <= 0:
                        logger.info(f"Reached limit of {limit} tenders")
                        break
                    batch_size = min(batch_size, remaining)

                # Build query for tenders needing details with pagination
                query = self.supabase.table("tenders").select(
                    "id, external_id, publication_id, project_number"
                ).eq("source", "simap").is_("deleted_at", "null")

                if only_missing:
                    query = query.is_("details_fetched_at", "null")

                # Add pagination
                query = query.range(offset, offset + batch_size - 1)

                result = query.execute()
                tenders = result.data if result.data else []

                if not tenders:
                    if offset == 0:
                        logger.info("No tenders found needing details")
                    else:
                        logger.info("No more tenders to process")
                    break

                logger.info(f"Processing batch of {len(tenders)} tenders (offset: {offset})")

                for i, tender in enumerate(tenders, 1):
                    tender_id = tender.get("id")
                    external_id = tender.get("external_id")
                    publication_id = tender.get("publication_id")
                    project_number = tender.get("project_number", "unknown")

                    if not publication_id:
                        logger.debug(f"Skipping tender {project_number}: no publication_id")
                        continue

                    logger.info(f"Fetching details {total_processed + i}: {project_number}")

                    success = self.fetch_and_update_details(
                        tender_id=tender_id,
                        external_id=external_id,
                        publication_id=publication_id,
                    )

                    if not success:
                        logger.warning(f"Failed to fetch details for {project_number}")

                    # Rate limiting: wait between API calls to avoid hitting rate limits
                    if self.detail_api_delay > 0:
                        time.sleep(self.detail_api_delay)

                total_processed += len(tenders)

                # If we got fewer results than batch size, we've reached the end
                if len(tenders) < batch_size:
                    break

                # Move to next batch
                # Note: Since we're processing missing details and marking them as fetched,
                # the offset should stay at 0 for subsequent batches (new records will appear)
                # unless we're not in only_missing mode
                if not only_missing:
                    offset += batch_size

            logger.info(f"Total tenders processed: {total_processed}")

        except Exception as e:
            logger.error(f"Error fetching tender details: {e}")
            self.stats["errors"] += 1

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

        now = datetime.now(timezone.utc)
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
        fetch_details: bool = True,
        details_limit: Optional[int] = None,
    ) -> dict:
        """
        Run the complete sync process.

        Steps:
        1. Fetch projects from SIMAP API (search endpoint)
        2. Upsert to database
        3. Update tender statuses
        4. Fetch publication details for tenders missing them (default: enabled)

        Args:
            project_sub_types: Specific types to sync (default: all types)
            days_back: Only fetch publications from last N days
            limit: Maximum number of projects to fetch (for testing)
            fetch_details: Whether to fetch publication details (default: True)
            details_limit: Maximum number of details to fetch (for testing)

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

        if not fetch_details:
            logger.info("SKIP DETAILS MODE - Will skip publication details")

        # Calculate date range for incremental sync
        publication_from = None
        publication_until = None

        if days_back:
            publication_from = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
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

        # Step 4: Optionally fetch publication details
        if fetch_details:
            logger.info("-" * 60)
            logger.info("Fetching publication details...")
            self.fetch_details_for_tenders(
                limit=details_limit,
                only_missing=True,
            )

        # Log statistics
        logger.info("-" * 60)
        logger.info("Sync Statistics:")
        logger.info(f"  Fetched:         {self.stats['fetched']}")
        logger.info(f"  Inserted:        {self.stats['inserted']}")
        logger.info(f"  Updated:         {self.stats['updated']}")
        logger.info(f"  Details fetched: {self.stats['details_fetched']}")
        logger.info(f"  Details errors:  {self.stats['details_errors']}")
        logger.info(f"  Errors:          {self.stats['errors']}")
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
Prerequisites (choose one):
  # Option 1: Environment variables (recommended)
  export SUPABASE_URL="https://xxx.supabase.co"
  export SUPABASE_KEY="your-service-role-key"

  # Option 2: Command line arguments
  python simap_sync.py --supabase-url URL --supabase-key KEY --days 7

Examples (assuming env vars are set):
  # === Daily Operations ===
  python simap_sync.py --days 1                    # Daily incremental sync (recommended)
  python simap_sync.py --days 7                    # Weekly sync

  # === Filtered Sync ===
  python simap_sync.py --days 7 --type construction              # Construction only
  python simap_sync.py --days 7 --type service --type supply     # Multiple types

  # === Testing & Debugging ===
  python simap_sync.py --limit 10 --dry-run                      # Preview 10 records
  python simap_sync.py --limit 5 --details-limit 3 --verbose     # Debug with limited data
  python simap_sync.py --days 1 --verbose --log-file debug.log   # Full logging

  # === Performance Options ===
  python simap_sync.py --days 7 --skip-details                   # Fast: search only
  python simap_sync.py --days 7 --rate-limit 2.0                 # Slow: 2s between API calls

  # === Backfill Operations ===
  python simap_sync.py --details-only --details-limit 100        # Fetch missing details
  python simap_sync.py --details-only                            # All missing details
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
        "--skip-details",
        action="store_true",
        help="Skip fetching publication details (details are fetched by default)",
    )
    parser.add_argument(
        "--details-limit",
        type=int,
        default=None,
        help="Maximum number of tender details to fetch (for testing)",
    )
    parser.add_argument(
        "--details-only",
        action="store_true",
        help="Only fetch details for existing tenders, skip project search",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DETAIL_API_DELAY_SECONDS,
        help=f"Delay between detail API calls in seconds (default: {DETAIL_API_DELAY_SECONDS})",
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

    # Initialize and run worker using context manager for automatic cleanup
    with SimapSyncWorker(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        dry_run=args.dry_run,
        detail_api_delay=args.rate_limit,
    ) as worker:
        # Handle details-only mode
        if args.details_only:
            if args.skip_details:
                logger.warning("--details-only conflicts with --skip-details, ignoring --skip-details")
            logger.info("Details-only mode - skipping project search")
            worker.fetch_details_for_tenders(
                limit=args.details_limit,
                only_missing=True,
            )
            stats = worker.stats
        else:
            # Run full sync (details fetched by default unless --skip-details)
            stats = worker.run(
                project_sub_types=args.types,
                days_back=args.days,
                limit=args.limit,
                fetch_details=not args.skip_details,
                details_limit=args.details_limit,
            )

        # Exit with error code if there were errors
        # This allows CI/CD pipelines to detect failures
        if stats["errors"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
