# Database Design - Tender Scout

## Overview

This document defines the conceptual data model for Tender Scout, designed for implementation with **Supabase** (PostgreSQL + Auth + Storage + Realtime).

---

## Conceptual Data Model

### Entity Relationship Diagram

```mermaid
erDiagram
    %% Core Entities
    users {
        uuid id PK
        varchar email UK
        timestamptz created_at
        timestamptz updated_at
    }

    companies {
        uuid id PK
        varchar name
        varchar uid UK "nullable"
        varchar city
        varchar address "nullable"
        varchar company_type
        jsonb zefix_data "nullable"
        timestamptz created_at
    }

    user_profiles {
        uuid id PK
        uuid user_id FK
        uuid company_id FK
        varchar name
        varchar role
        boolean is_default
        timestamptz created_at
    }

    search_profiles {
        uuid id PK
        uuid user_profile_id FK
        varchar industry
        varchar company_size
        text[] keywords
        text[] exclude_keywords
        text[] regions
        jsonb cpv_codes "array of codes"
        jsonb npk_codes "array of codes"
        boolean ai_generated
        timestamptz created_at
        timestamptz updated_at
    }

    tenders {
        uuid id PK
        varchar external_id
        varchar source
        varchar source_url
        varchar title
        varchar authority
        varchar authority_type
        text description
        decimal price_min
        decimal price_max
        varchar currency
        timestamptz deadline
        timestamptz publication_date
        varchar status
        varchar region
        varchar language
        jsonb cpv_codes "array of codes"
        jsonb raw_data
        timestamptz created_at
        timestamptz updated_at
    }

    user_tender_actions {
        uuid id PK
        uuid user_profile_id FK
        uuid tender_id FK
        boolean bookmarked
        boolean applied
        boolean hidden
        integer match_score
        text notes
        timestamptz created_at
        timestamptz updated_at
    }

    %% Classification Tables
    cpv_codes {
        varchar code PK
        varchar label_de
        varchar label_fr
        varchar label_it
        varchar label_en
        varchar parent_code FK "nullable"
    }

    npk_codes {
        varchar code PK
        varchar name_de
        varchar name_fr
        varchar name_it
        varchar parent_code FK "nullable"
    }

    %% Relationships
    users ||--o{ user_profiles : "has many"
    companies ||--o{ user_profiles : "has many"
    user_profiles ||--|| search_profiles : "has one"
    user_profiles ||--o{ user_tender_actions : "tracks"
    tenders ||--o{ user_tender_actions : "receives"
```

---

### Entity Overview

| Entity | Type | Description |
|--------|------|-------------|
| **users** | Core | User accounts managed by Supabase Auth |
| **companies** | Core | Swiss companies identified via Zefix or manual entry |
| **user_profiles** | Core | Links users to companies with role information |
| **search_profiles** | Core | AI-generated or user-defined tender matching criteria (includes CPV/NPK codes as JSONB) |
| **tenders** | Core | Public procurement opportunities from SIMAP/TED (includes CPV codes as JSONB) |
| **user_tender_actions** | Core | Tracks user interactions and match scores |
| **cpv_codes** | Lookup | EU Common Procurement Vocabulary (hierarchical) |
| **npk_codes** | Lookup | Swiss construction standards (hierarchical) |

---

## Entities

### 1. users

Managed by **Supabase Auth**. Extended with a profiles table if additional user metadata is needed.

| Attribute    | Type        | Description                          |
|--------------|-------------|--------------------------------------|
| id           | UUID (PK)   | Supabase Auth user ID                |
| email        | VARCHAR     | User's email (unique)                |
| created_at   | TIMESTAMPTZ | Account creation timestamp           |
| updated_at   | TIMESTAMPTZ | Last update timestamp                |

**Notes:**
- Authentication handled by Supabase Auth (email/password, OAuth)
- Additional profile data (name, avatar) can be stored in a separate `user_metadata` table or Supabase's built-in `raw_user_meta_data`

---

### 2. companies

Swiss companies identified via Zefix or manually entered.

| Attribute    | Type        | Description                          |
|--------------|-------------|--------------------------------------|
| id           | UUID (PK)   | Unique identifier                    |
| name         | VARCHAR     | Company name                         |
| uid          | VARCHAR     | Swiss UID (CHE-xxx.xxx.xxx), nullable|
| city         | VARCHAR     | City/location                        |
| address      | VARCHAR     | Street address, nullable             |
| company_type | VARCHAR     | Legal form (AG, GmbH, etc.)          |
| zefix_data   | JSONB       | Raw Zefix API response, nullable     |
| created_at   | TIMESTAMPTZ | Record creation timestamp            |

**Notes:**
- `uid` is unique when present but nullable for manually entered companies
- `zefix_data` stores the complete API response for reference

---

### 3. user_profiles

Links users to companies with role information. A user can have multiple profiles (e.g., consultant working with multiple companies).

| Attribute    | Type        | Description                          |
|--------------|-------------|--------------------------------------|
| id           | UUID (PK)   | Unique identifier                    |
| user_id      | UUID (FK)   | Reference to users                   |
| company_id   | UUID (FK)   | Reference to companies               |
| name         | VARCHAR     | Profile display name                 |
| role         | VARCHAR     | User's role at company               |
| is_default   | BOOLEAN     | Default profile for this user        |
| created_at   | TIMESTAMPTZ | Record creation timestamp            |

**Constraints:**
- Unique constraint on (user_id, company_id)
- Only one `is_default = true` per user_id

---

### 4. search_profiles

AI-generated or user-defined search criteria for tender matching.

| Attribute        | Type        | Description                          |
|------------------|-------------|--------------------------------------|
| id               | UUID (PK)   | Unique identifier                    |
| user_profile_id  | UUID (FK)   | Reference to user_profiles           |
| industry         | VARCHAR     | Industry category                    |
| company_size     | VARCHAR     | Size range (1-9, 10-49, 50-249)      |
| keywords         | TEXT[]      | Positive matching keywords           |
| exclude_keywords | TEXT[]      | Negative/exclusion keywords          |
| regions          | TEXT[]      | Target regions (cantons/countries)   |
| cpv_codes        | JSONB       | Selected CPV codes `["45210000", ...]` |
| npk_codes        | JSONB       | Selected NPK codes `["211", ...]`    |
| ai_generated     | BOOLEAN     | Whether AI created this profile      |
| created_at       | TIMESTAMPTZ | Record creation timestamp            |
| updated_at       | TIMESTAMPTZ | Last modification timestamp          |

**Notes:**
- One-to-one relationship with user_profiles (each profile has one search configuration)
- CPV/NPK codes stored as JSONB arrays for simpler reads and atomic updates

---

### 5. tenders

Public procurement opportunities from SIMAP, TED, and other sources.

| Attribute      | Type        | Description                          |
|----------------|-------------|--------------------------------------|
| id             | UUID (PK)   | Unique identifier                    |
| external_id    | VARCHAR     | Source system ID (SIMAP/TED ref)     |
| source         | VARCHAR     | Origin: 'simap', 'ted', 'eu'         |
| source_url     | VARCHAR     | Link to original tender              |
| title          | VARCHAR     | Tender title                         |
| authority      | VARCHAR     | Contracting authority name           |
| authority_type | VARCHAR     | Type: municipal, cantonal, federal   |
| description    | TEXT        | Full tender description              |
| price_min      | DECIMAL     | Minimum estimated value (CHF)        |
| price_max      | DECIMAL     | Maximum estimated value (CHF)        |
| currency       | VARCHAR     | Currency code (CHF, EUR)             |
| deadline       | TIMESTAMPTZ | Submission deadline                  |
| publication_date| TIMESTAMPTZ| When tender was published            |
| status         | VARCHAR     | 'open', 'closing_soon', 'closed'     |
| region         | VARCHAR     | Primary region/canton                |
| language       | VARCHAR     | Primary language (de, fr, it, en)    |
| cpv_codes      | JSONB       | CPV classification codes `["45210000", ...]` |
| raw_data       | JSONB       | Original API response                |
| created_at     | TIMESTAMPTZ | Record creation timestamp            |
| updated_at     | TIMESTAMPTZ | Last sync timestamp                  |

**Notes:**
- `external_id` + `source` should be unique (prevents duplicate imports)
- `raw_data` preserves original data for debugging and future parsing improvements
- CPV codes stored as JSONB array for simpler matching queries

---

### 6. user_tender_actions

Tracks user interactions with tenders (bookmark, apply, hide).

| Attribute       | Type        | Description                          |
|-----------------|-------------|--------------------------------------|
| id              | UUID (PK)   | Unique identifier                    |
| user_profile_id | UUID (FK)   | Reference to user_profiles           |
| tender_id       | UUID (FK)   | Reference to tenders                 |
| bookmarked      | BOOLEAN     | User bookmarked this tender          |
| applied         | BOOLEAN     | User marked as applied               |
| hidden          | BOOLEAN     | User hid this tender                 |
| match_score     | INTEGER     | Calculated match percentage (0-100)  |
| notes           | TEXT        | User's private notes                 |
| created_at      | TIMESTAMPTZ | First interaction timestamp          |
| updated_at      | TIMESTAMPTZ | Last action timestamp                |

**Constraints:**
- Unique constraint on (user_profile_id, tender_id)

---

### 7. cpv_codes

EU Common Procurement Vocabulary - hierarchical classification system.

| Attribute   | Type        | Description                          |
|-------------|-------------|--------------------------------------|
| code        | VARCHAR (PK)| CPV code (e.g., '45210000')          |
| label_de    | VARCHAR     | German label                         |
| label_fr    | VARCHAR     | French label                         |
| label_it    | VARCHAR     | Italian label                        |
| label_en    | VARCHAR     | English label                        |
| parent_code | VARCHAR (FK)| Parent CPV code for hierarchy        |

**Notes:**
- Self-referencing for hierarchical structure
- Codes are standardized EU-wide

---

### 8. npk_codes

Swiss construction standards (Normpositionen-Katalog).

| Attribute   | Type        | Description                          |
|-------------|-------------|--------------------------------------|
| code        | VARCHAR (PK)| NPK code (e.g., '211')               |
| name_de     | VARCHAR     | German name                          |
| name_fr     | VARCHAR     | French name                          |
| name_it     | VARCHAR     | Italian name                         |
| parent_code | VARCHAR (FK)| Parent code for hierarchy            |

---

## Relationships Summary

| Relationship                      | Type        | Description                              |
|-----------------------------------|-------------|------------------------------------------|
| users → user_profiles             | 1:N         | User can have multiple company profiles  |
| companies → user_profiles         | 1:N         | Company can have multiple users          |
| user_profiles → search_profiles   | 1:1         | Each profile has one search config       |
| user_profiles → user_tender_actions| 1:N        | Profile tracks many tender interactions  |
| tenders → user_tender_actions     | 1:N         | Tender can be acted on by many profiles  |

**Note:** CPV/NPK codes are stored as JSONB arrays within `search_profiles` and `tenders` rather than via junction tables. This simplifies reads and enables atomic updates. The lookup tables (`cpv_codes`, `npk_codes`) are used for code validation and label display.

---

## Supabase-Specific Considerations

### Authentication
- Use Supabase Auth for user management
- Support email/password + OAuth providers (Google, Microsoft)
- Row Level Security (RLS) policies based on `auth.uid()`

### Row Level Security (RLS) Policies

```
-- Users can only see their own profiles
user_profiles: auth.uid() = user_id

-- Users can only see/modify their own search profiles
search_profiles: user_profile_id IN (SELECT id FROM user_profiles WHERE user_id = auth.uid())

-- Users can only see/modify their own tender actions
user_tender_actions: user_profile_id IN (SELECT id FROM user_profiles WHERE user_id = auth.uid())

-- Tenders are readable by all authenticated users
tenders: auth.role() = 'authenticated'

-- Code tables are readable by all
cpv_codes, npk_codes: true (public read)
```

### Realtime Subscriptions
- Subscribe to `tenders` for new tender notifications
- Subscribe to `user_tender_actions` for cross-device sync

### Storage
- User avatars in `avatars` bucket
- Company logos in `company-logos` bucket
- Tender attachments in `tender-documents` bucket (future)

### Edge Functions
- `sync-simap`: Fetch new tenders from SIMAP API
- `sync-ted`: Fetch new tenders from TED API

---

## Matching Algorithm

### Overview

Match scores are calculated by a **Python batch job** that runs:
1. **On-demand:** When a user completes or updates their search profile
2. **Scheduled:** Daily, when new tenders are synced from SIMAP/TED

### Architecture

```mermaid
flowchart TB
    subgraph Triggers
        T1[/"Daily Schedule (cron)"/]
        T2[/"Profile Created/Updated"/]
        T3[/"New Tenders Synced"/]
    end

    subgraph Python["Python Matching Job"]
        direction TB
        Start([Start]) --> FetchTenders
        FetchTenders[Fetch tenders from Supabase<br/>filter: status = 'open'] --> FetchProfiles
        FetchProfiles[Fetch all active<br/>search_profiles] --> Loop

        Loop{For each<br/>profile × tender} --> Calculate
        Calculate[Calculate match_score] --> Threshold
        Threshold{score >= 50?}
        Threshold -->|Yes| Upsert[Upsert to<br/>user_tender_actions]
        Threshold -->|No| Skip[Skip low matches]
        Upsert --> More
        Skip --> More
        More{More pairs?}
        More -->|Yes| Loop
        More -->|No| Notify
        Notify[Trigger notifications<br/>for high matches] --> End([End])
    end

    subgraph Supabase["Supabase PostgreSQL"]
        DB_Tenders[(tenders)]
        DB_Profiles[(search_profiles)]
        DB_Actions[(user_tender_actions)]
    end

    T1 --> Start
    T2 --> Start
    T3 --> Start

    FetchTenders -.->|SELECT| DB_Tenders
    FetchProfiles -.->|SELECT| DB_Profiles
    Upsert -.->|UPSERT| DB_Actions
```

### Score Calculation Flow

```mermaid
flowchart LR
    subgraph Inputs
        P[Search Profile]
        T[Tender]
    end

    subgraph Scoring["Score Components"]
        direction TB
        CPV[CPV Overlap<br/>weight: 40%]
        KW[Keyword Match<br/>weight: 25%]
        REG[Region Match<br/>weight: 20%]
        NPK[NPK Overlap<br/>weight: 15%]
        EX[Exclusion Check<br/>penalty: -20%]
    end

    subgraph Output
        Score[Final Score<br/>0-100]
    end

    P --> CPV
    P --> KW
    P --> REG
    P --> NPK
    P --> EX
    T --> CPV
    T --> KW
    T --> REG
    T --> NPK
    T --> EX

    CPV --> Score
    KW --> Score
    REG --> Score
    NPK --> Score
    EX --> Score
```

### Matching Criteria

| Criterion | Weight | Logic | Example |
|-----------|--------|-------|---------|
| **CPV overlap** | 40% | `len(profile ∩ tender) / len(profile)` | Profile has 5 CPV, tender matches 3 → 60% × 40 = 24 pts |
| **Keyword match** | 25% | Keywords found in title/description | 4 of 6 keywords found → 67% × 25 = 17 pts |
| **Region match** | 20% | Tender region in profile regions | Exact match → 100% × 20 = 20 pts |
| **NPK overlap** | 15% | Same as CPV, for construction | 2 of 4 NPK match → 50% × 15 = 8 pts |
| **Exclusion penalty** | -20% | Any exclude_keyword found | 1 exclusion found → -20 pts |

**Score formula:**
```
score = (cpv_score × 0.40) + (keyword_score × 0.25) + (region_score × 0.20) + (npk_score × 0.15) - exclusion_penalty
score = max(0, min(100, score))
```

### Pseudocode

```python
def calculate_match_score(profile: SearchProfile, tender: Tender) -> int:
    score = 0

    # CPV overlap (40%)
    if profile.cpv_codes and tender.cpv_codes:
        overlap = set(profile.cpv_codes) & set(tender.cpv_codes)
        cpv_ratio = len(overlap) / len(profile.cpv_codes)
        score += cpv_ratio * 40

    # Keyword matching (25%)
    text = f"{tender.title} {tender.description}".lower()
    if profile.keywords:
        matches = sum(1 for kw in profile.keywords if kw.lower() in text)
        kw_ratio = matches / len(profile.keywords)
        score += kw_ratio * 25

    # Region match (20%)
    if tender.region in profile.regions:
        score += 20

    # NPK overlap (15%) - construction tenders only
    if profile.npk_codes and tender.cpv_codes:
        # Map CPV to NPK or check NPK directly
        npk_overlap = calculate_npk_overlap(profile, tender)
        score += npk_overlap * 15

    # Exclusion penalty (-20%)
    if profile.exclude_keywords:
        for ex in profile.exclude_keywords:
            if ex.lower() in text:
                score -= 20
                break

    return max(0, min(100, int(score)))
```

### Execution Modes

| Mode | Trigger | Scope | Frequency |
|------|---------|-------|-----------|
| **Full sync** | Daily cron | All profiles × all open tenders | Once per day |
| **Incremental** | New tender webhook | All profiles × new tender | Per tender |
| **Profile update** | User saves profile | Single profile × all open tenders | On demand |

### Why Python?

- **Experimentation:** Easy to tweak scoring weights and logic
- **NLP potential:** spaCy, scikit-learn for smarter keyword matching
- **Local testing:** Run against test data without deployment
- **Scheduling:** cron, GitHub Actions, or cloud scheduler (Cloud Run, Lambda)
- **Supabase integration:** `supabase-py` client for database access

---

## Data Flow

```
1. User Registration
   Supabase Auth → users (automatic)

2. Company Selection
   Zefix API → companies (if new)
   User selects → user_profiles created

3. AI Profile Generation
   Company data → AI analysis → search_profiles (with cpv_codes, npk_codes)

4. Tender Sync (Daily Job)
   SIMAP/TED APIs → tenders (with cpv_codes)

5. Tender Matching (Daily Job)
   Python script: search_profiles × tenders → user_tender_actions.match_score

6. User Actions
   Bookmark/Apply/Hide → user_tender_actions
```

---

## Future Considerations

### Phase 2 Additions
- `applications` table - Track actual bid submissions
- `tender_updates` table - Version history for tender changes
- `notifications` table - User notification preferences and history

### Phase 3 Additions
- `competitors` table - Competitor tracking
- `bid_history` table - Historical bid outcomes for win probability
- `tender_analytics` table - Aggregated statistics

---

## Revision History

| Date       | Version | Changes                    |
|------------|---------|----------------------------|
| 2026-01-18 | 0.3     | Add detailed Mermaid flowcharts for matching algorithm |
| 2026-01-18 | 0.2     | Replace junction tables with JSONB arrays; add matching algorithm section |
| 2026-01-18 | 0.1     | Initial conceptual model   |
