# Tender Scout Workers

Background jobs for syncing and processing tender data.

---

## SIMAP Sync Worker

Daily scheduled job that fetches public procurement tenders from the Swiss SIMAP API and syncs them to the Supabase database.

### Quick Start

```bash
# 1. Install dependencies
cd workers
pip install -r requirements.txt

# 2. Run with credentials (test mode)
python simap_sync.py \
  --supabase-url "https://xxx.supabase.co" \
  --supabase-key "sb_secret_xxx" \
  --limit 50 \
  --dry-run
```

---

### SIMAP API Reference

**Official Documentation:** https://www.simap.ch/api-doc/#/publications/getPublicProjectSearch

SIMAP (Système d'information sur les marchés publics) is the official Swiss public procurement platform. The API provides access to all public tenders published in Switzerland.

**API Endpoint:**
```
GET https://www.simap.ch/api/publications/v2/project/project-search
```

**Key Points:**
- The API is **public** and requires no authentication for read access
- At least one filter parameter is required (e.g., `projectSubTypes` or `orderAddressCountryOnlySwitzerland`)
- Uses **rolling pagination** with a `lastItem` cursor (format: `YYYYMMDD|projectNumber`)
- Returns multilingual data (German, French, Italian, English)
- Default page size is 20 items

---

### Setup

#### 1. Install Dependencies

```bash
cd workers
pip install -r requirements.txt
```

#### 2. Get Supabase Credentials

1. Go to your [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project
3. Navigate to **Project Settings** → **API**
4. Copy the **Secret key** (`sb_secret_...`)

> **Important:** Use the **secret key** (not the publishable key) for server-side operations.

#### 3. Run the Worker

**Option A: Pass credentials directly (recommended for testing)**
```bash
python simap_sync.py \
  --supabase-url "https://xxx.supabase.co" \
  --supabase-key "sb_secret_xxx" \
  --limit 50 \
  --dry-run
```

**Option B: Use environment variables**
```bash
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="sb_secret_xxx"
python simap_sync.py --limit 50 --dry-run
```

---

### Command Line Options

| Option | Description |
|--------|-------------|
| `--supabase-url URL` | Supabase project URL (or use `SUPABASE_URL` env var) |
| `--supabase-key KEY` | Supabase secret key (or use `SUPABASE_KEY` env var) |
| `--days N` | Only fetch publications from last N days |
| `--type TYPE` | Filter by project type (can be repeated) |
| `--limit N` | Maximum number of tenders to fetch (for testing) |
| `--dry-run` | Preview mode - fetch from API but don't write to database |

### Usage Examples

```bash
# Test run - fetch 50 tenders, don't write to DB
python simap_sync.py --supabase-url URL --supabase-key KEY --limit 50 --dry-run

# Production - sync last 7 days
python simap_sync.py --days 7

# Sync only construction tenders
python simap_sync.py --type construction

# Sync multiple types
python simap_sync.py --type construction --type service

# Full sync - all project types, all available data
python simap_sync.py
```

---

### Project Types

The worker supports all SIMAP project sub-types:

| Type | Description |
|------|-------------|
| `construction` | Construction works (Bauaufträge) |
| `service` | Service contracts (Dienstleistungen) |
| `supply` | Supply/goods contracts (Lieferungen) |
| `project_competition` | Project competition |
| `idea_competition` | Idea competition |
| `overall_performance_competition` | Overall performance competition |
| `project_study` | Project study |
| `idea_study` | Idea study |
| `overall_performance_study` | Overall performance study |
| `request_for_information` | Request for information (RFI) |

---

### SIMAP API Filter Parameters

**Available Filters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Free text search (3-1000 chars) |
| `lang` | array | Languages to search in (see values below) |
| `projectSubTypes` | array | Project sub-types to filter (see values below) |
| `processTypes` | array | Procurement process types (see values below) |
| `newestPubTypes` | array | Publication types (see values below) |
| `cpvCodes` | array | CPV classification codes |
| `npkCodes` | array | NPK codes (Swiss construction standards) |
| `bkpCodes` | array | BKP codes (Swiss construction cost codes) |
| `orderAddressCantons` | array | Canton codes: `BE`, `ZH`, `VD`, etc. |
| `orderAddressCountryOnlySwitzerland` | boolean | Filter to Swiss projects only |
| `newestPublicationFrom` | date | Publication date from (YYYY-MM-DD) |
| `newestPublicationUntil` | date | Publication date until (YYYY-MM-DD) |
| `lastItem` | string | Pagination cursor from previous response |

**Parameter Values:**

`lang` - Languages to search:
```
de, en, fr, it
```

`projectSubTypes` - Project sub-types:
```
construction, service, supply, project_competition, idea_competition,
overall_performance_competition, project_study, idea_study,
overall_performance_study, request_for_information
```

`processTypes` - Procurement process types:
```
open, selective, invitation, direct, no_process
```

`newestPubTypes` - Publication types:
```
advance_notice, request_for_information, tender, competition, study_contract,
award_tender, award_study_contract, award_competition, direct_award,
participant_selection, revocation, abandonment, selective_offering_phase
```

**Date Filters (for incremental sync):**

For daily update jobs, use these date filters to fetch only recent publications:

| Parameter | Format | Description |
|-----------|--------|-------------|
| `newestPublicationFrom` | `YYYY-MM-DD` | Filter projects with newest publication date >= this date |
| `newestPublicationUntil` | `YYYY-MM-DD` | Filter projects with newest publication date <= this date |
| `lastItem` | `YYYYMMDD\|projectNumber` | Pagination cursor (from previous response's `pagination.lastItem`) |

**Example API Request:**
```bash
# Get Swiss construction tenders
curl -X GET "https://www.simap.ch/api/publications/v2/project/project-search?projectSubTypes=construction&lang=de&orderAddressCountryOnlySwitzerland=true" \
  -H "accept: application/json"

# Get publications from the last week
curl -X GET "https://www.simap.ch/api/publications/v2/project/project-search?orderAddressCountryOnlySwitzerland=true&newestPublicationFrom=2026-01-12" \
  -H "accept: application/json"
```

For the complete API specification, visit the [SIMAP API Documentation](https://www.simap.ch/api-doc/).

---

### Scheduling

#### Option 1: Cron (Linux/macOS)

Add to crontab (`crontab -e`):

```cron
# Run daily at 6:00 AM
0 6 * * * cd /path/to/tender-scout/workers && /usr/bin/python3 simap_sync.py --days 7 >> /var/log/simap-sync.log 2>&1
```

#### Option 2: GitHub Actions

Create `.github/workflows/simap-sync.yml`:

```yaml
name: SIMAP Sync

on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6:00 AM UTC
  workflow_dispatch:      # Manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r workers/requirements.txt

      - name: Run sync
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python workers/simap_sync.py --days 7
```

#### Option 3: Supabase Edge Functions (with pg_cron)

Use Supabase's built-in cron scheduling to trigger an Edge Function that calls this worker.

---

### What the Worker Does

1. **Fetches tenders** from SIMAP API for all project types (with pagination)
2. **Transforms data** to match our database schema (see `documentation/DATABASE.md`)
3. **Upserts records** to the `tenders` table (insert new, update existing)
4. **Updates statuses** based on deadlines:
   - `open` → `closing_soon` (7 days before deadline)
   - `closing_soon` → `closed` (after deadline)

---

### Monitoring

The worker logs to stdout with timestamps:

```
2026-01-19 06:00:00 [INFO] ============================================================
2026-01-19 06:00:00 [INFO] SIMAP Tender Sync Worker
2026-01-19 06:00:00 [INFO] ============================================================
2026-01-19 06:00:00 [INFO] Project types: construction, service, supply, ...
2026-01-19 06:00:01 [INFO] Fetching page 1...
2026-01-19 06:00:02 [INFO] Fetched 20 projects (total: 20)
...
2026-01-19 06:01:30 [INFO] ------------------------------------------------------------
2026-01-19 06:01:30 [INFO] Sync Statistics:
2026-01-19 06:01:30 [INFO]   Fetched:  1250
2026-01-19 06:01:30 [INFO]   Inserted: 45
2026-01-19 06:01:30 [INFO]   Updated:  1205
2026-01-19 06:01:30 [INFO]   Errors:   0
2026-01-19 06:01:30 [INFO] ============================================================
```

**For production, consider:**
- Redirecting logs to a file or log aggregation service
- Setting up alerts for non-zero error counts
- Using the exit code (non-zero if errors occurred) for CI/CD pipelines

---

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `Missing Supabase URL` | Pass `--supabase-url` or set `SUPABASE_URL` env var |
| `Missing Supabase key` | Pass `--supabase-key` or set `SUPABASE_KEY` env var |
| `HTTP 403 from SIMAP` | The API may block requests from certain IPs/hosts |
| `HTTP 400 Bad Request` | At least one filter parameter is required |
| `Connection timeout` | Check network connectivity, increase timeout in code |

---

### API Rate Limits

The SIMAP API doesn't document specific rate limits, but the worker:
- Uses pagination (20 items per page by default)
- Has a safety limit of 1000 pages per run
- Includes proper error handling for failed requests
