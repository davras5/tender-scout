# Tender Scout

Intelligent tender matching platform for Swiss SMEs. Aggregates public contracts from SIMAP, TED, and cantonal portals, using AI-powered matching to deliver personalized recommendations.

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
- **Planned Backend:** Supabase (PostgreSQL + Auth), Stripe payments

## Project Structure

```
tender-scout/
├── index.html              # Single-page application (8 views)
├── README.md
├── css/
│   ├── styles.css          # Core styles (~2,600 lines)
│   └── tokens.css          # Design system tokens
├── js/
│   └── script.js           # Application logic (~1,370 lines)
├── data/
│   ├── test_data.json      # Mock companies, tenders, AI recommendations
│   ├── cpv_codes.json      # EU Common Procurement Vocabulary (8,000+ codes)
│   └── npk_codes.json      # Swiss construction standards (500+ codes)
├── documentation/
│   ├── VISION.md           # Product vision & roadmap
│   ├── REQUIREMENTS.md     # User stories, wireframes, functional specs
│   ├── DATABASE.md         # Data model (conceptual, logical, physical)
│   └── DESIGNGUIDE.md      # Design system & component library
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

### Planned
- Supabase backend integration
- Real Zefix API connection
- SIMAP/TED tender aggregation
- Stripe payment processing
- Email notifications
- i18n (actual language switching)

## Documentation

| Document | Description |
|----------|-------------|
| [VISION.md](documentation/VISION.md) | Product vision, target users, success metrics |
| [REQUIREMENTS.md](documentation/REQUIREMENTS.md) | Detailed user stories and wireframes |
| [DATABASE.md](documentation/DATABASE.md) | Complete data model with SQL schema |
| [DESIGNGUIDE.md](documentation/DESIGNGUIDE.md) | Design tokens, components, accessibility |
| [MARKET.md](research/MARKET.md) | Swiss procurement market research |

## License

MIT
