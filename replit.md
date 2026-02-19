# LinkedIn Relationship Intelligence Tool

## Overview
Multi-user internal tool for tracking LinkedIn profiles and generating daily relationship intelligence digests. No login required - users just enter their name to access their own separate data space. Uses OpenAI for post analysis and dual notification system (dashboard + optional email).

## Recent Changes
- 2026-02-15: Added CSV upload for bulk-importing LinkedIn profiles
- 2026-02-15: Removed authentication - replaced with simple name-based user entry (no passwords)
- 2026-02-15: Added multi-user support with per-user data isolation
- 2026-02-15: Enhanced posts display with day grouping, avatars, time-ago formatting, and LinkedIn links
- 2026-02-15: Improved notifications with day grouping and clickable post links
- 2026-02-11: Switched to Fresh LinkedIn Scraper API via RapidAPI for fetching posts
- 2026-02-11: Added dashboard notifications panel with unread badge
- 2026-02-11: Made email optional - notifications always saved to dashboard, email sent only if SMTP configured
- 2026-02-11: Initial build with full project structure

## Project Architecture
- **Stack**: Python 3.11, FastAPI, PostgreSQL, SQLAlchemy, APScheduler
- **User Identification**: Name-based entry with cookie tokens (itsdangerous), no passwords
- **AI**: Replit AI Integrations (OpenAI-compatible, gpt-5-mini)
- **LinkedIn**: Fresh LinkedIn Scraper API via RapidAPI (RAPIDAPI_KEY secret)
- **Structure**: `/app` directory with modular files (main.py, database.py, models.py, linkedin.py, ai.py, notify.py, scheduler.py, auth.py)
- **Entry point**: `main.py` runs uvicorn on port 5000
- **Database**: PostgreSQL via DATABASE_URL env var
- **Scheduler**: APScheduler runs daily at 8AM UTC for all users
- **Notifications**: Dual system - always saves to DB (Notification model), optionally sends email if SMTP configured
- **Multi-user**: Each user has their own profiles, posts, notifications, and settings

## Key Files
- `app/main.py` - FastAPI application with API endpoints
- `app/auth.py` - User identification module (cookie tokens, find-or-create user)
- `app/models.py` - SQLAlchemy models (User, Profile, Post, Notification, Settings)
- `app/database.py` - Database connection and session management
- `app/linkedin.py` - LinkedIn API integration via RapidAPI
- `app/ai.py` - OpenAI post analysis (summary, category, suggested reply)
- `app/notify.py` - Notification system (dashboard + optional email), per-user
- `app/scheduler.py` - APScheduler daily cron job, processes all users
- `app/templates/login.html` - Name entry page
- `app/templates/dashboard.html` - Dashboard UI
- `app/static/app.js` - Frontend JavaScript
- `app/static/style.css` - Styles

## API Endpoints
### User Entry
- `GET /` - Name entry page (new visitors) or Dashboard (returning users)
- `POST /enter` - Enter name to access dashboard (form submission)
- `GET /switch-user` - Switch to a different user
- `GET /api/me` - Get current user info

### Data (all scoped to current user)
- `GET /health` - Health check
- `POST /profiles` - Add a LinkedIn profile
- `GET /profiles` - List user's profiles
- `GET /profiles/{id}` - Get single profile
- `DELETE /profiles/{id}` - Remove profile
- `GET /profiles/{id}/posts` - Get posts for profile
- `GET /posts` - List user's posts
- `POST /trigger-job` - Manually trigger daily job for current user
- `GET /settings/email` - Get email settings
- `POST /settings/email` - Save email settings
- `GET /settings/linkedin` - Get LinkedIn API status
- `GET /notifications` - List user's notifications
- `GET /notifications/unread-count` - Get unread notification count
- `POST /notifications/mark-read/{id}` - Mark single notification read
- `POST /notifications/mark-all-read` - Mark all notifications read

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection (auto-provided)
- `SESSION_SECRET` - Secret key for session tokens
- `AI_INTEGRATIONS_OPENAI_*` - Auto-configured by Replit

## LinkedIn Data Source
- Uses Fresh LinkedIn Scraper API on RapidAPI (by saleleadsdotai)
- Requires RAPIDAPI_KEY secret and subscription to: https://rapidapi.com/saleleadsdotai-saleleadsdotai-default/api/fresh-linkedin-scraper-api
- Two-step flow: get user URN via profile endpoint, then fetch posts via posts endpoint
- No LinkedIn login/cookies needed — purely API-based

## User Preferences
- Clean modular code with proper error handling and logging
- Internal tool with multi-user support, no authentication required
- Prefers simple notification methods (dashboard first, email optional)
- No Twilio/SMS integration (user declined)
- Prefers free solutions over paid APIs
