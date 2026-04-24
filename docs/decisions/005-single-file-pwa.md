# 005 — Single-file PWA frontend (no build step)

**Status**: Accepted  
**Date**: 2026-04

## Context

The frontend needs to work on Mac (desktop browser), iPhone, and iPad without requiring any installation on mobile devices. Options included a React/Vue SPA with a build pipeline, or a plain HTML/JS/CSS single file served directly by FastAPI.

## Decision

All frontend code lives in `frontend/index.html` — one file, no bundler, no npm, no build step. FastAPI serves it as a static file. The page is a PWA (installable via "Add to Home Screen" on iOS).

## Reasoning

- Zero build infrastructure — no Node.js, no `package.json`, no Webpack/Vite
- The file is readable and editable directly; changes are visible immediately on reload
- For a personal tool with one developer, the productivity loss from no hot-reload or TypeScript is negligible
- PWA manifest + service worker give a near-native feel on iOS without an App Store submission

## Consequences

- As the file grows it becomes harder to navigate (currently ~3300 lines)
- No TypeScript — runtime errors instead of compile-time errors
- No component model — HTML structure and JS logic are coupled in template strings
- If the frontend ever needs a component framework or TypeScript, migrating from a single file is a significant rewrite
