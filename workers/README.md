# Tender Scout Workers

Background jobs for syncing and processing tender data.

## SIMAP Sync Worker

Daily scheduled job that fetches public procurement tenders from the Swiss SIMAP API and syncs them to the Supabase database.

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

**Available Filters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Free text search (3-1000 chars) |
| `lang` | array | Languages to search: `de`, `en`, `fr`, `it` |
| `projectSubTypes` | array | `construction`, `service`, `supply`, etc. |
| `processTypes` | array | `open`, `selective`, `invitation`, `direct`, `no_process` |
| `newestPubTypes` | array | `tender`, `award`, `revocation`, etc. |
| `cpvCodes` | array | CPV classification codes |
| `npkCodes` | array | NPK codes (Swiss construction standards) |
| `bkpCodes` | array | BKP codes (Swiss construction cost codes) |
| `orderAddressCantons` | array | Canton codes: `BE`, `ZH`, `VD`, etc. |
| `orderAddressCountryOnlySwitzerland` | boolean | Filter to Swiss projects only |
| `newestPublicationFrom` | date | Publication date from (YYYY-MM-DD) |
| `newestPublicationUntil` | date | Publication date until (YYYY-MM-DD) |
| `lastItem` | string | Pagination cursor from previous response |

**Example Request:**
```bash
curl -X GET "https://www.simap.ch/api/publications/v2/project/project-search?projectSubTypes=construction&lang=de&orderAddressCountryOnlySwitzerland=true" \
  -H "accept: application/json"
```

For the complete API specification, visit the [SIMAP API Documentation](https://www.simap.ch/api-doc/).

### Setup

1. Install dependencies:

```bash
cd workers
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-service-role-key"
```

> **Important:** Use the **service role key** (not the anon key) for server-side operations.

### Usage

```bash
# Full sync - all project types, all available data
python simap_sync.py

# Sync only last 7 days
python simap_sync.py --days 7

# Sync specific project type(s)
python simap_sync.py --type construction
python simap_sync.py --type construction --type service

# Preview mode (no database writes)
python simap_sync.py --dry-run

# Combine options
python simap_sync.py --days 7 --type construction --dry-run
```

### Project Types

The worker supports all SIMAP project sub-types:

| Type | Description |
|------|-------------|
| `construction` | Construction works |
| `service` | Service contracts |
| `supply` | Supply/goods contracts |
| `project_competition` | Project competition |
| `idea_competition` | Idea competition |
| `overall_performance_competition` | Overall performance competition |
| `project_study` | Project study |
| `idea_study` | Idea study |
| `overall_performance_study` | Overall performance study |
| `request_for_information` | Request for information |

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

### What the Worker Does

1. **Fetches tenders** from SIMAP API for all project types
2. **Transforms data** to match the database schema
3. **Upserts records** to the `tenders` table (insert or update)
4. **Updates statuses** based on deadlines:
   - `open` → `closing_soon` (7 days before deadline)
   - `closing_soon` → `closed` (after deadline)

### API Rate Limits

The SIMAP API doesn't document specific rate limits, but the worker:
- Uses pagination (20 items per page by default)
- Has a safety limit of 1000 pages per run
- Includes proper error handling for failed requests

### Monitoring

The worker logs to stdout with timestamps:

```
2026-01-19 06:00:00 [INFO] SIMAP Tender Sync Worker
2026-01-19 06:00:00 [INFO] Project types: construction, service, supply, ...
2026-01-19 06:00:01 [INFO] Fetching page 1...
2026-01-19 06:00:02 [INFO] Fetched 20 projects (total: 20)
...
2026-01-19 06:01:30 [INFO] Sync Statistics:
2026-01-19 06:01:30 [INFO]   Fetched:  1250
2026-01-19 06:01:30 [INFO]   Inserted: 45
2026-01-19 06:01:30 [INFO]   Updated:  1205
2026-01-19 06:01:30 [INFO]   Errors:   0
```

For production, consider:
- Redirecting logs to a file or log aggregation service
- Setting up alerts for non-zero error counts
- Using the exit code (non-zero if errors occurred)
