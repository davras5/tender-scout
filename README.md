# Tender Scout

Intelligent tender matching platform for Swiss SMEs. Aggregates public contracts from SIMAP, TED, and cantonal portals, using AI-powered matching to deliver personalized recommendations.

<p align="center">
  <img src="assets/banner2.jpg" width="90%"/>
</p>

<p align="center">
  <img src="assets/preview2.jpg" width="45%" style="vertical-align: top;"/>
  <img src="assets/preview1.jpg" width="45%" style="vertical-align: top;"/>
</p>

## Quick Start

```bash
# Option 1: Use a local server (required for JSON data loading)
npx serve

# Option 2: Python
python -m http.server 8000

# Then open http://localhost:8000 (or the port shown)
```

**Note:** Opening `index.html` directly via `file://` won't work due to CORS restrictions on fetch requests.

## Tech Stack

- **Frontend:** Pure HTML5, CSS3, JavaScript (ES6+)
- **No dependencies:** Zero npm packages, no build step
- **Mobile-first:** Responsive design with dark mode support
- **Worker:** Python 3.9+ for SIMAP tender synchronization
- **External APIs:** SIMAP v1/v2 (Swiss public procurement)
- **Planned Backend:** Supabase (PostgreSQL + Auth), Stripe payments

## Project Structure

```
tender-scout/
├── index.html              # Single-page application (8 views)
├── README.md
├── css/
│   ├── styles.css          # Core styles (~3,500 lines)
│   └── tokens.css          # Design system tokens
├── js/
│   └── script.js           # Application logic (~1,600 lines)
├── data/
│   ├── test_data.json      # Mock companies, tenders, AI recommendations
│   ├── cpv_codes.json      # EU Common Procurement Vocabulary (8,000+ codes)
│   └── npk_codes.json      # Swiss construction standards (500+ codes)
├── documentation/
│   ├── VISION.md           # Product vision & roadmap
│   ├── REQUIREMENTS.md     # User stories, wireframes, functional specs
│   ├── DATABASE.md         # Data model (conceptual, logical, physical)
│   └── DESIGNGUIDE.md      # Design system & component library
├── workers/
│   └── simap_sync/         # SIMAP tender synchronization worker
│       ├── simap_sync.py   # Main sync script
│       ├── requirements.txt
│       └── README.md
├── assets/                 # Banner images and marketing materials
└── research/
    ├── MARKET.md           # Swiss procurement market analysis
    └── Swiss Public Procurement Market.MD
```

## Features

### Implemented (Prototype)
- Landing page with pricing tiers
- Authentication UI (login/register with SSO placeholders)
- Company search via Zefix lookup simulation
- Manual company entry fallback
- AI recommendation review with edit capabilities
- Dashboard with tender feed, filters, and sorting
- Tender detail view with match score breakdown
- Settings (billing, profile, notifications, team, security tabs)
- Dark/light theme toggle with system preference detection
- Language selector UI (DE/FR/IT/EN)
- **SIMAP Sync Worker** - Automated tender synchronization from SIMAP API

### Planned
- Supabase backend integration
- Real Zefix API connection
- TED tender aggregation (EU expansion)
- Stripe payment processing
- Email notifications
- i18n (actual language switching)

## SIMAP Sync Worker

The `workers/simap_sync/` directory contains a Python worker that fetches tender data from the Swiss SIMAP public procurement portal.

### Installation

```bash
cd workers/simap_sync
pip install -r requirements.txt
```

### Usage

```bash
# Dry run (preview without database writes)
python simap_sync.py --dry-run --days 7

# Full sync with Supabase
python simap_sync.py \
  --supabase-url $SUPABASE_URL \
  --supabase-key $SUPABASE_KEY \
  --days 7

# Limit for testing
python simap_sync.py --dry-run --limit 10 --verbose
```

### Key Options

| Option | Description |
|--------|-------------|
| `--days N` | Fetch publications from last N days |
| `--type TYPE` | Filter by project type (construction, service, supply) |
| `--limit N` | Max tenders to fetch (for testing) |
| `--dry-run` | Preview without database writes |
| `--skip-details` | Skip fetching publication details |
| `--verbose` | Enable debug logging |

### Scheduling

```bash
# Cron (daily at 6 AM)
0 6 * * * cd /path/to/workers/simap_sync && python simap_sync.py --days 7
```

See `workers/simap_sync/README.md` for complete documentation.

## Documentation

| Document | Description |
|----------|-------------|
| [VISION.md](documentation/VISION.md) | Product vision, target users, success metrics |
| [REQUIREMENTS.md](documentation/REQUIREMENTS.md) | Detailed user stories and wireframes |
| [DATABASE.md](documentation/DATABASE.md) | Complete data model with SQL schema |
| [DESIGNGUIDE.md](documentation/DESIGNGUIDE.md) | Design tokens, components, accessibility |
| [MARKET.md](research/MARKET.md) | Swiss procurement market research |

## License

Apache 2.0 - See [LICENSE.md](LICENSE.md) for details.
