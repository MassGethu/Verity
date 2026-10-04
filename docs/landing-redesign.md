# Landing-page implementation report

The root now presents Verity’s fourteen-section product story. The recruiter overview lives at `/dashboard/`, with real database counts, recent jobs, a session-dismissible configuration notice, and clearly labelled synthetic demo data. Existing job, application and feedback routes remain intact. Candidate-facing interviews have since been replaced by recruiter interview guides; the retired routes return 404.

The landing document has isolated styles and scripts. Candidate cards, source disclosures, the ranking toggle, interview-guide playback, feedback editing playback, and future-feature labels are illustrative. They never create records, call providers, change scores, or launch an email composer. The optional demo CTA resolves a real job containing `demo-fixture` applications; empty installations omit it.

## Motion integration

Motion 12.23.24 is vendored as an 81 KB vanilla browser bundle with its MIT license and source notice. Deferred loading orders Motion before `landing.js`. No npm installation, build step, or runtime CDN is needed. Google Fonts remain optional, with system fallbacks.

The page uses `animate`, `inView`, `scroll`, `stagger`, `spring`, `hover`, and `press`: a bounded hero entrance, viewport reveals, SVG connectors, natural-scroll workflow progress, score/row entrances, and transform-based ranking reordering. Guide and feedback demonstrations finish on viewport exit or tab hiding, stop playback scheduling, preserve complete text, and allow explicit replay. Reduced motion skips choreography and a runtime preference change cancels ongoing animation. Content is visible by default when scripts are missing.

## Files

Created:

- `templates/recruitment/landing.html` — separate document, SEO metadata, all fourteen sections, accessible navigation and native source disclosures.
- `static/css/landing.css` — independent palette, typography, illustrations, responsive layouts, focus and reduced-motion styles.
- `static/js/landing.js` — mobile menu, illustrative sorting, Motion choreography and bounded replay.
- `static/vendor/motion/motion-12.23.24.js` — pinned local browser bundle.
- `static/vendor/motion/LICENSE.md` — upstream MIT license.
- `static/vendor/motion/README.md` — version, source URLs and download date.
- `recruitment/tests/test_landing.py` — routing, templates, counts, fixture links, preserved titles and read-only behavior.
- `recruitment/tests/test_landing_js.cjs` — fallback, ranking, menu, timing, viewport-exit cleanup and changing reduced-motion preferences.
- `docs/landing-redesign.md` — this implementation report.
- `docs/screenshots/landing-desktop.jpg` — desktop hero.
- `docs/screenshots/landing-full.jpg` — complete desktop page.
- `docs/screenshots/landing-mobile.jpg` — mobile hero.
- `docs/screenshots/landing-mobile-full.jpg` — complete mobile page.
- `docs/screenshots/workspace-redesign.jpg` — operational dashboard.

Modified:

- `recruitment/urls.py` — root landing and named dashboard route.
- `recruitment/views.py` — read-only landing context and dashboard counts/display metadata.
- `templates/base.html` — internal navigation returns to dashboard; explicit public-site link.
- `templates/recruitment/create.html` — cancellation returns to dashboard.
- `templates/recruitment/home.html` — operational overview, actual counts, compact notice and synthetic badge.
- `static/css/app.css` — small scoped notice/public-link styles.
- `static/js/app.js` — session-dismissible configuration notice.
- `README.md` — entry URLs, Motion/fallback documentation and JavaScript test command.

## Verification

- The current Django suite includes replacement guide tests and migration coverage; see `interview-guide-implementation.md` for the latest verification.
- Django system check passes; migration-drift check reports no changes.
- Existing feedback JavaScript check and new landing JavaScript checks pass; edited scripts pass syntax checks.
- Browser checks cover widths 375, 768, 1280 and 1440 with no horizontal overflow.
- Browser interaction checks cover mobile menu, Escape/focus restoration, ranking order with unchanged scores and retained focus, source disclosure, guide replay and recruiter follow-up editing, feedback playback, notice persistence and dashboard entry.
- Browser console inspected without application errors; desktop and mobile screenshots captured and reviewed.
- Missing Motion and reduced-motion behavior are exercised by the dependency-free JavaScript harness. JavaScript-free readability and offline portability are also supported by visible HTML, local assets and font fallbacks; browser network-disconnection and browser-level JavaScript disabling were not emulated.

## Run

No additional dependencies or migrations are required for the existing installation.

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/ for the landing page or http://127.0.0.1:8000/dashboard/ for the recruiter workspace.

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
node recruitment/tests/test_feedback_js.cjs
node recruitment/tests/test_landing_js.cjs
node recruitment/tests/test_interview_guide_js.cjs
```

## Deliberate simplifications

The marketing guide demonstrates shortlist → source-linked question → accountability scenario → recruiter edit. The feedback/Gmail panel remains a labelled preview. Actual guide preparation/editing and Gmail handoff remain in the workspace. This avoids side effects during product exploration and is the behavior specified in the plan. Offscreen playback resolves to its complete state instead of pausing midway. No requested section was dropped.
