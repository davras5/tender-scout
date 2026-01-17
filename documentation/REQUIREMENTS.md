# Tender Scout - Requirements Document

## Overview

**Product Vision:** Tender Scout is an intelligent tender matching platform that automatically connects Swiss SMEs with relevant public procurement opportunities through AI-powered smart matching.

**Core Differentiator:** Unlike traditional tender portals that require manual search and filtering, Tender Scout delivers personalized tender recommendations from minimal user input. Users enter their company name, and AI does the rest.

**Target Users:** Swiss SMEs (1-50 employees) across construction, IT, consulting, healthcare, and other industries seeking public procurement opportunities.

---

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Smart Match, Not Search** | AI-powered recommendations replace manual filtering |
| **Minimal Input, Maximum Output** | Company name triggers automatic profile generation |
| **Mobile-First** | Designed for mobile, scales beautifully to desktop |
| **Unified Experience** | Same wizard for all industries, conditional elements toggled as needed |
| **User Control** | AI suggests, user can always adjust |

---

## User Journey

### Overview Flow

```
Landing Page → Sign Up → Company Identification → AI Recommendations → Dashboard
```

### Detailed Journey

#### 1. Landing Page
- Value proposition and feature overview
- Pricing tiers (Free/Pro/Enterprise)
- Call-to-action to sign up
- Language selector (DE/FR/IT/EN)
- Dark/light theme toggle

#### 2. Authentication
- **Sign Up:** Email/password registration
- **Sign In:** Email/password login
- **Password Recovery:** Email-based reset flow
- Future consideration: Social login, Enterprise SSO

#### 3. Company Identification

Two paths to identify the user's company:

**Path A: Zefix Search (Recommended)**
- User searches by company name or UID
- System queries Zefix (Swiss Commercial Registry)
- User selects from matching results
- Auto-populated data:
  - Legal company name
  - UID (Unternehmens-Identifikationsnummer)
  - Registered address
  - Legal form (AG, GmbH, etc.)

**Path B: Manual Entry (Fallback)**
- User manually enters:
  - Company name (required)
  - Address (required)
  - Industry (required)
  - Company size (required)
  - UID (optional)
- Use cases: Non-Swiss companies, new companies, user preference

#### 4. AI-Powered Recommendations

Based on company data (from Zefix or manual entry), AI generates:

| Recommendation | Description |
|----------------|-------------|
| **Industry Classification** | Detected industry category |
| **CPV Codes** | Suggested Common Procurement Vocabulary codes |
| **NPK Codes** | Swiss construction standards (construction industry only) |
| **Company Size** | Employee range classification |
| **Regional Focus** | Suggested geographic scope for tenders |

**User Actions:**
- Review AI suggestions
- Accept recommendations as-is, OR
- Adjust any/all recommendations manually
- Proceed to dashboard

#### 5. Dashboard

Primary interface after onboarding - see Dashboard section below.

---

## Functional Requirements

### F1: Smart Matching Engine

**Description:** AI-powered system that matches company profiles to relevant tenders.

**Matching Criteria:**
| Criterion | Description | Applies To |
|-----------|-------------|------------|
| Industry | Primary business sector | All |
| CPV Codes | EU procurement vocabulary categories | All |
| NPK Codes | Swiss construction work categories | Construction only |
| Company Size | Employee count / capacity | All |
| Region | Canton / geographic area | All |
| Contract Value | Tender value ranges | All (Pro+) |

**Requirements:**
- F1.1: System shall match tenders based on user's profile attributes
- F1.2: System shall calculate and display a relevance score per tender
- F1.3: System shall prioritize tenders by relevance score (highest first)
- F1.4: System shall update matches when new tenders are published
- F1.5: System shall re-calculate matches when user updates profile

---

### F2: Dashboard

**Description:** Central hub displaying matched tenders and user analytics.

#### F2.1: Matched Tenders Feed

**Requirements:**
- F2.1.1: Display list of AI-matched tenders sorted by relevance
- F2.1.2: Show key tender info in list view:
  - Title
  - Contracting authority
  - Relevance score / match percentage
  - Deadline date
  - Estimated value (if available)
  - Status badge (Open, Closing Soon, Closed)
- F2.1.3: Support filtering matched tenders by:
  - Status (Open / Closing Soon / All)
  - Region
  - Value range
  - CPV category
- F2.1.4: Support sorting by: Relevance, Deadline, Value, Date Published
- F2.1.5: Paginate results for performance

#### F2.2: Tender Detail View

**Requirements:**
- F2.2.1: Display full tender information:
  - Title and description
  - Contracting authority with contact info
  - Submission deadline (with countdown)
  - Contract value / estimated range
  - CPV / NPK codes
  - Eligibility requirements
  - Required documents
  - Lot information (if applicable)
- F2.2.2: Link to original source (SIMAP, TED, etc.)
- F2.2.3: Show why this tender matched (matching criteria breakdown)
- F2.2.4: Actions: Save, Dismiss, Mark as Applied

#### F2.3: Tender Management

**Requirements:**
- F2.3.1: Save tenders to a "Saved" list for later review
- F2.3.2: Dismiss tenders to hide from feed (with undo option)
- F2.3.3: Mark tenders as "Applied" to track submissions
- F2.3.4: Add private notes to any tender
- F2.3.5: View history of all interactions with tenders

**Tender States:**
| State | Description |
|-------|-------------|
| New | Matched but not yet viewed |
| Viewed | User has opened detail view |
| Saved | User saved for later |
| Dismissed | User chose to hide |
| Applied | User marked as submitted |

#### F2.4: Analytics & Insights

**Requirements:**
- F2.4.1: Display total matched tenders (current period)
- F2.4.2: Show tenders by status breakdown (pie/bar chart)
- F2.4.3: Display upcoming deadlines calendar view
- F2.4.4: Show match trends over time (line chart)
- F2.4.5: Display industry/category distribution of matches

---

### F3: Alerts & Notifications

**Description:** Proactive communication to keep users informed of relevant opportunities.

#### F3.1: New Match Alerts

**Requirements:**
- F3.1.1: Notify user when new tenders match their profile
- F3.1.2: Support notification channels: Email, In-app
- F3.1.3: Allow user to configure alert frequency:
  - Instant (as they arrive)
  - Daily digest
  - Weekly digest
- F3.1.4: Include tender summary in notification with link to details

#### F3.2: Deadline Reminders

**Requirements:**
- F3.2.1: Send reminders for saved tenders approaching deadline
- F3.2.2: Default reminder schedule: 7 days, 3 days, 1 day before
- F3.2.3: Allow user to customize reminder timing
- F3.2.4: Allow user to disable reminders per tender

#### F3.3: Tender Updates

**Requirements:**
- F3.3.1: Notify when saved tender is amended/updated
- F3.3.2: Notify when Q&A is published for saved tender
- F3.3.3: Notify when tender is cancelled or awarded

---

### F4: Company Profile Management

**Description:** Allow users to view and modify their company profile and matching preferences.

**Requirements:**
- F4.1: View current company information
- F4.2: Edit company details (name, address, size)
- F4.3: Modify industry classification
- F4.4: Add/remove CPV codes
- F4.5: Add/remove NPK codes (construction companies)
- F4.6: Adjust regional preferences
- F4.7: Re-run AI recommendations at any time
- F4.8: View profile completeness indicator

---

### F5: Subscription & Billing

**Description:** Freemium model with tiered feature access.

#### F5.1: Subscription Tiers

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| Matched tenders | 10/month | Unlimited | Unlimited |
| Saved tenders | 5 | Unlimited | Unlimited |
| Email alerts | Weekly digest | Real-time | Real-time |
| Deadline reminders | - | Yes | Yes |
| Analytics | Basic | Full | Full |
| Team members | 1 | 5 | Unlimited |
| API access | - | - | Yes |
| Custom integrations | - | - | Yes |
| Priority support | - | - | Yes |

#### F5.2: Billing Management

**Requirements:**
- F5.2.1: Display current subscription plan and status
- F5.2.2: Show next billing date and amount
- F5.2.3: Allow plan upgrade/downgrade
- F5.2.4: Support payment methods: Credit card, Invoice (Enterprise)
- F5.2.5: View and download invoice history
- F5.2.6: Update payment method
- F5.2.7: Cancel subscription with confirmation flow

#### F5.3: Trial & Conversion

**Requirements:**
- F5.3.1: Free tier available without payment method
- F5.3.2: Show upgrade prompts when hitting Free tier limits
- F5.3.3: Provide clear feature comparison during upgrade flow

---

### F6: Team Management

**Description:** Allow multiple users to collaborate under one company account.

**Requirements:**
- F6.1: Invite team members via email
- F6.2: Assign roles: Admin, Member
- F6.3: Admin can manage billing and team settings
- F6.4: Member can view/manage tenders
- F6.5: Share saved tenders with team members
- F6.6: Remove team members
- F6.7: Transfer admin role to another member

**Role Permissions:**
| Permission | Admin | Member |
|------------|-------|--------|
| View matched tenders | Yes | Yes |
| Save/manage tenders | Yes | Yes |
| Edit company profile | Yes | No |
| Manage team members | Yes | No |
| Manage billing | Yes | No |
| View analytics | Yes | Yes |

---

### F7: Account Settings

**Description:** Personal account and notification preferences.

**Requirements:**
- F7.1: Update email address (with verification)
- F7.2: Change password
- F7.3: Set display language (DE/FR/IT/EN)
- F7.4: Set theme preference (Light/Dark/System)
- F7.5: Configure notification preferences:
  - Email notifications on/off
  - In-app notifications on/off
  - Alert frequency
  - Reminder timing
- F7.6: Download personal data (GDPR)
- F7.7: Delete account (with confirmation)

---

## Industry-Specific Configuration

The onboarding wizard maintains a consistent UI across all industries. Specific elements are conditionally displayed based on detected/selected industry.

### Element Visibility Matrix

| UI Element | Construction | IT & Digital | Consulting | Healthcare | Other |
|------------|--------------|--------------|------------|------------|-------|
| CPV Code Selector | Yes | Yes | Yes | Yes | Yes |
| NPK Code Selector | Yes | No | No | No | No |
| Regional Focus (Strong) | Yes | No | No | No | No |
| Certification Input | Optional | Optional | Optional | Yes | Optional |
| Framework Agreement Filter | Optional | Yes | Yes | Optional | Optional |

### Industry Categories

| ID | Name (DE) | Name (EN) | Special Attributes |
|----|-----------|-----------|-------------------|
| construction | Baugewerbe | Construction | NPK codes, strong regional focus |
| trades | Handwerk | Trades | NPK codes, certification tracking |
| it | IT & Digital | IT & Digital | Framework agreements, lot tracking |
| consulting | Beratung | Consulting | Qualification-based matching |
| engineering | Ingenieurwesen | Engineering | Technical certifications |
| health | Gesundheit | Healthcare | Regulatory compliance |
| education | Bildung | Education | Public sector focus |
| energy | Energie & Umwelt | Energy & Environment | Sustainability criteria |
| facilities | Facility Management | Facility Management | Service-level agreements |

---

## Localization

### Supported Languages

| Code | Language | Coverage |
|------|----------|----------|
| de | German | Full (Primary) |
| fr | French | Full |
| it | Italian | Full |
| en | English | Full |

### Localization Requirements

- L1: All UI text shall be available in all supported languages
- L2: User can switch language at any time
- L3: Language preference persists across sessions
- L4: Tender content displayed in original language (from source)
- L5: Dates formatted per locale (e.g., DD.MM.YYYY for DE/FR/IT)
- L6: Numbers formatted per locale (e.g., 1'000 for CH)

---

## Responsive Design

### Breakpoints

| Breakpoint | Width | Target |
|------------|-------|--------|
| Base | < 640px | Mobile phones |
| sm | 640px+ | Large phones |
| md | 768px+ | Tablets |
| lg | 1024px+ | Desktop |
| xl | 1280px+ | Wide desktop |

### Mobile-First Requirements

- R1: All features fully functional on mobile
- R2: Touch targets minimum 44x44px
- R3: Bottom navigation for primary actions on mobile
- R4: Swipe gestures for tender actions (save, dismiss)
- R5: Responsive data tables (card view on mobile)
- R6: Collapsible filters on mobile

---

## Data Sources

### Tender Sources

| Source | Coverage | Priority |
|--------|----------|----------|
| SIMAP | Swiss federal & cantonal tenders | Phase 1 |
| TED | EU-wide tenders | Phase 2 |
| National Portals | EU member state portals | Phase 3 |

### Company Data Sources

| Source | Data Provided |
|--------|---------------|
| Zefix | Company name, UID, address, legal form |
| AI Enhancement | Industry classification, CPV/NPK suggestions, size estimation |

---

## Non-Functional Requirements

### Performance

- NFR1: Dashboard shall load within 2 seconds on 4G connection
- NFR2: Search results shall return within 1 second
- NFR3: System shall support 10,000 concurrent users

### Security

- NFR4: All data transmitted via HTTPS
- NFR5: Passwords hashed using industry-standard algorithms
- NFR6: Session tokens expire after 24 hours of inactivity
- NFR7: GDPR compliant data handling

### Availability

- NFR8: 99.5% uptime SLA
- NFR9: Scheduled maintenance windows communicated 48h in advance

### Accessibility

- NFR10: WCAG 2.1 AA compliance
- NFR11: Keyboard navigation support
- NFR12: Screen reader compatible

---

## Glossary

| Term | Definition |
|------|------------|
| **CPV** | Common Procurement Vocabulary - EU standard classification for public contracts |
| **NPK** | Normpositionen-Katalog - Swiss standard for construction work items |
| **SIMAP** | Système d'information sur les marchés publics - Swiss procurement portal |
| **TED** | Tenders Electronic Daily - EU procurement portal |
| **Zefix** | Zentraler Firmenindex - Swiss central business registry |
| **UID** | Unternehmens-Identifikationsnummer - Swiss company identification number |
| **SME** | Small and Medium-sized Enterprise |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-01-17 | - | Initial draft |
