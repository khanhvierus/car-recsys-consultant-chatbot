# Profile + Favorites Wiring + Header Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the orphaned Favorites page, add a read-only Profile page, and make the header auth-aware (Login when logged out; avatar dropdown with Profile/Favorites/Logout when logged in) — frontend-only, all backend endpoints already exist.

**Architecture:** Register `/favorites` (page already coded) and a new `/profile` route in App.tsx; create `ProfilePage.tsx` mirroring FavoritesPage's pattern (Helmet + Header + auth-guard redirect + Footer), reading the user from `getCurrentUser()`/`authApi.getMe()`; replace the header's logged-in "Explore" button with a shadcn DropdownMenu+Avatar. No backend changes.

**Tech Stack:** React + TypeScript + Vite, react-router-dom, shadcn/ui (DropdownMenu, Avatar, Button), lucide-react, existing `authApi`/`isAuthenticated`/`getCurrentUser` in `src/lib/api.ts`.

**Reference spec:** `docs/superpowers/specs/2026-06-01-profile-favorites-wiring-design.md`

**Working dir:** `/home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend`

**Verification reality:** This env cannot `npm install`/build (EACCES). Each task is verified by `python3 -c`/grep static checks here; the real `npm run build` + browser check is run by the USER (same as prior frontend work). No test runner exists.

**Verified facts (don't re-derive):**
- App.tsx imports pages and has a routes block with a `{/* ... above the catch-all */}` comment before `<Route path="*" .../>`.
- `FavoritesPage.tsx` is `export default`, self-guards (`if(!isAuthenticated()) navigate('/login')`), uses `useFavorites`. It just needs a route.
- shadcn exports: `DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator` from `@/components/ui/dropdown-menu`; `Avatar, AvatarFallback` from `@/components/ui/avatar`.
- `src/lib/api.ts`: `isAuthenticated()`, `getCurrentUser(): User|null`, `authApi.getMe(): Promise<User>`, `authApi.logout(): void`. `User` = {id, username, email, full_name?, phone?, is_active, created_at}.

---

## File Structure
- `src/App.tsx` (MODIFY) — import FavoritesPage + ProfilePage, register `/favorites` + `/profile`.
- `src/pages/ProfilePage.tsx` (CREATE) — read-only profile, auth-guarded.
- `src/components/Header.tsx` (MODIFY) — avatar dropdown when logged in.

Order: routes (Task 1, unblocks Favorites immediately) → ProfilePage (Task 2) → Header (Task 3, links to both).

---

## Task 1: Register `/favorites` and `/profile` routes

**Files:** Modify `src/App.tsx`

- [ ] **Step 1: Add the imports**

After the existing page imports (the block ending `import ChatPage from "./pages/ChatPage";`), add:
```tsx
import ChatPage from "./pages/ChatPage";
import FavoritesPage from "./pages/FavoritesPage";
import ProfilePage from "./pages/ProfilePage";
```
(ProfilePage is created in Task 2; the import is fine to add now — the build runs after Task 2.)

- [ ] **Step 2: Register the routes**

In the `<Routes>` block, add the two routes immediately before the catch-all comment line:
```tsx
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/favorites" element={<FavoritesPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
```

- [ ] **Step 3: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
grep -n "FavoritesPage\|ProfilePage\|/favorites\|/profile" src/App.tsx
```
Expected: both imports present and both `<Route path="/favorites"...>` / `<Route path="/profile"...>` registered above the catch-all.

- [ ] **Step 4: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/frontend/src/App.tsx
git commit -m "feat(frontend): register /favorites + /profile routes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Create read-only ProfilePage

**Files:** Create `src/pages/ProfilePage.tsx`

- [ ] **Step 1: Create the file**

Create `src/pages/ProfilePage.tsx` with:
```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Heart, LogOut, Mail, Phone, User as UserIcon, CalendarDays } from "lucide-react";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { isAuthenticated, getCurrentUser, authApi, type User } from "@/lib/api";

export default function ProfilePage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(getCurrentUser());

  useEffect(() => {
    if (!isAuthenticated()) {
      navigate("/login");
      return;
    }
    // Refresh from the server; fall back to the cached user on failure.
    authApi.getMe().then(setUser).catch(() => setUser(getCurrentUser()));
  }, [navigate]);

  const handleLogout = () => {
    authApi.logout();
    navigate("/");
  };

  const memberSince = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined,
        { year: "numeric", month: "long", day: "numeric" })
    : null;

  const initial = (user?.username?.[0] ?? "?").toUpperCase();

  return (
    <>
      <Helmet>
        <title>My Profile - Car Recommendation System</title>
        <meta name="description" content="Your account profile" />
      </Helmet>

      <div className="min-h-screen bg-background">
        <Header />
        <main className="container mx-auto max-w-3xl px-4 pt-28 pb-16">
          <h1 className="mb-6 text-3xl font-extrabold text-foreground">My Profile</h1>

          {!user ? (
            <p className="text-muted-foreground">Loading your profile…</p>
          ) : (
            <div className="space-y-6">
              {/* Identity card */}
              <div className="flex items-center gap-4 rounded-xl border border-border bg-card p-6">
                <Avatar className="h-16 w-16">
                  <AvatarFallback className="bg-primary text-primary-foreground text-xl font-bold">
                    {initial}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <div className="truncate text-xl font-bold text-foreground">
                    {user.full_name || user.username}
                  </div>
                  <div className="text-sm text-muted-foreground">@{user.username}</div>
                </div>
              </div>

              {/* Details */}
              <div className="space-y-3 rounded-xl border border-border bg-card p-6 text-sm">
                <div className="flex items-center gap-3 text-foreground">
                  <Mail className="h-4 w-4 text-muted-foreground" /> {user.email}
                </div>
                {user.phone && (
                  <div className="flex items-center gap-3 text-foreground">
                    <Phone className="h-4 w-4 text-muted-foreground" /> {user.phone}
                  </div>
                )}
                {user.full_name && (
                  <div className="flex items-center gap-3 text-foreground">
                    <UserIcon className="h-4 w-4 text-muted-foreground" /> {user.full_name}
                  </div>
                )}
                {memberSince && (
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <CalendarDays className="h-4 w-4" /> Member since {memberSince}
                  </div>
                )}
              </div>

              {/* Quick actions */}
              <div className="flex flex-wrap gap-3">
                <Button asChild variant="outline">
                  <Link to="/favorites">
                    <Heart className="mr-2 h-4 w-4" /> My Favorites
                  </Link>
                </Button>
                <Button variant="destructive" onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" /> Logout
                </Button>
              </div>
            </div>
          )}
        </main>
        <Footer />
      </div>
    </>
  );
}
```
Note: imports `type User` from `@/lib/api` — confirm api.ts `export interface User` exists (it does). `pt-28` clears the fixed header (h-20). Mirrors FavoritesPage's Helmet+Header+Footer+auth-guard pattern.

- [ ] **Step 2: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
grep -n "export default function ProfilePage\|authApi.getMe\|authApi.logout\|AvatarFallback\|isAuthenticated" src/pages/ProfilePage.tsx
# confirm the symbols it imports actually exist in api.ts:
grep -nE "export interface User|export function getCurrentUser|export function isAuthenticated|getMe|logout" src/lib/api.ts | head
```
Expected: ProfilePage uses getMe/logout/AvatarFallback/auth-guard; api.ts exposes `User`, `getCurrentUser`, `isAuthenticated`, `getMe`, `logout`.

- [ ] **Step 3: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/frontend/src/pages/ProfilePage.tsx
git commit -m "feat(frontend): read-only ProfilePage (/auth/me + logout)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Header — avatar dropdown when logged in

**Files:** Modify `src/components/Header.tsx`

- [ ] **Step 1: Add imports**

At the top of Header.tsx, add the dropdown/avatar + helpers + icons + navigation. The current imports are:
```tsx
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { NavLink } from "@/components/NavLink";
import ThemeToggle from "@/components/ThemeToggle";
import { isAuthenticated } from "@/lib/api";
```
Replace with:
```tsx
import { Link, useNavigate } from "react-router-dom";
import { User as UserIcon, Heart, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NavLink } from "@/components/NavLink";
import ThemeToggle from "@/components/ThemeToggle";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { isAuthenticated, getCurrentUser, authApi } from "@/lib/api";
```

- [ ] **Step 2: Add navigate + logout, replace the logged-in branch**

The component currently is `const Header = () => { const loggedIn = isAuthenticated(); return (...)`. Add a navigate + logout handler at the top of the body:
```tsx
const Header = () => {
  const navigate = useNavigate();
  const loggedIn = isAuthenticated();
  const user = loggedIn ? getCurrentUser() : null;
  const initial = (user?.username?.[0] ?? "?").toUpperCase();

  const handleLogout = () => {
    authApi.logout();
    navigate("/");
    // force the header to re-read auth state after clearing localStorage
    window.location.assign("/");
  };
```
Then replace the right-cluster auth block. Current:
```tsx
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {loggedIn ? (
              <Button asChild size="sm" className="rounded-lg">
                <Link to="/search">Explore</Link>
              </Button>
            ) : (
              <Link
                to="/login"
                className="relative text-base font-semibold text-foreground/70 transition-all duration-200 hover:text-primary hover:scale-105 group px-1"
              >
                Login
                <span className="absolute left-0 -bottom-0.5 h-[2px] w-0 bg-primary transition-all duration-200 group-hover:w-full rounded-full" />
              </Link>
            )}
          </div>
```
Replace with:
```tsx
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {loggedIn ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button aria-label="Account menu" className="rounded-full outline-none focus:ring-2 focus:ring-primary">
                    <Avatar className="h-9 w-9">
                      <AvatarFallback className="bg-primary text-primary-foreground font-bold">
                        {initial}
                      </AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel className="truncate">
                    {user?.full_name || user?.username || "Account"}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/profile")}>
                    <UserIcon className="mr-2 h-4 w-4" /> Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/favorites")}>
                    <Heart className="mr-2 h-4 w-4" /> Favorites
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="mr-2 h-4 w-4" /> Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link
                to="/login"
                className="relative text-base font-semibold text-foreground/70 transition-all duration-200 hover:text-primary hover:scale-105 group px-1"
              >
                Login
                <span className="absolute left-0 -bottom-0.5 h-[2px] w-0 bg-primary transition-all duration-200 group-hover:w-full rounded-full" />
              </Link>
            )}
          </div>
```
Note on logout: `window.location.assign("/")` after `authApi.logout()` does a full reload so the header re-evaluates `isAuthenticated()` from the now-cleared localStorage (the `navigate("/")` alone wouldn't re-run the module-level `loggedIn`). The `navigate` line is harmless before the reload; keep both, or drop `navigate` — the reload is the load-bearing part. Implementer may keep just the `window.location.assign("/")`.

- [ ] **Step 3: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
grep -n "DropdownMenu\|AvatarFallback\|getCurrentUser\|authApi.logout\|/profile\|/favorites" src/components/Header.tsx
```
Expected: dropdown + avatar used, getCurrentUser + authApi.logout imported/used, navigation to /profile and /favorites present. (The old "Explore" button is gone, replaced by the dropdown.)

- [ ] **Step 4: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/frontend/src/components/Header.tsx
git commit -m "feat(frontend): header avatar dropdown (Profile/Favorites/Logout) when logged in

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: User build + visual verification (USER runs)

**Files:** none.

- [ ] **Step 1: Build + dev (user, this env can't)**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
npm run build    # must PASS (TS gate — catches any import/type issue across the 3 files)
npm run dev      # http://localhost:3000
```

- [ ] **Step 2: Visual checklist**
- Logged out: header shows **Login**; visiting `/favorites` or `/profile` redirects to `/login`.
- Log in (via /login), then: header shows an **avatar** (username initial) → dropdown with **Profile / Favorites / Logout**.
- **Profile** (`/profile`) shows username/email/full_name/phone/member-since from `/auth/me`; "My Favorites" link works.
- **Favorites** (`/favorites`) shows the user's saved vehicles (or an empty state).
- **Logout** from the dropdown (or Profile page) clears auth → header flips back to **Login**.
- Works in dark (default) + light; mobile header still usable.

- [ ] **Step 3: Report build result**
If `npm run build` fails, paste the error (controller fixes). If it passes and the flows work, the feature is done. (This frontend change ships to Cloud Run on the next frontend deploy, alongside the GA4 + CompareModal fix already committed.)

---

## Self-Review Notes
- **Spec coverage:** Favorites route → Task 1; ProfilePage (read-only, /auth/me, logout, member-since, favorites link) → Task 2; header avatar dropdown (Profile/Favorites/Logout, Login when logged out) → Task 3; build/visual verify → Task 4. No backend change anywhere. All spec sections mapped.
- **Placeholder scan:** No TBD. The one judgment note (logout re-eval) is resolved concretely — `window.location.assign("/")` forces re-read; implementer may drop the redundant `navigate`. Full file content for the new page; exact replace blocks for the edits.
- **Type consistency:** `getCurrentUser()`/`authApi.getMe()` return `User`; ProfilePage + Header read `user.username/full_name/email/phone/created_at` — all real `User` fields. shadcn import names match the verified exports (`DropdownMenu*`, `Avatar/AvatarFallback`). `authApi.logout()` (void) used in both ProfilePage and Header. `ProfilePage` is `export default` matching the App.tsx import.
- **No test runner** — verification is grep + static here, real `npm run build` + browser flow by the user (Task 4); appropriate for a wiring/UI change.
