# Proton 10.0 + PR #9608

Proton 10.0 with [PR #9608](https://github.com/ValveSoftware/Proton/pull/9608) applied.

## What this fixes

Fixes `ISteamHTMLSurface` callback ordering where `HTML_NeedsPaint_t` arrives before `HTML_URLChanged_t` on Linux, causing games to see stale page content and abort embedded browser sessions (e.g. Xbox Live authentication in Halo Infinite).

## How to build

Go to **Actions** tab → **Build Proton 10.0 + PR #9608** → **Run workflow**

## How to install (after build completes)

1. Download the `proton-10.0-pr9608` artifact from the Actions run
2. Extract the tar: `tar xf proton-pr9608-redist.tar`
3. Copy to Steam compatibility tools:
   ```bash
   mkdir -p ~/.steam/root/compatibilitytools.d/
   cp -r redist/Proton-10.0-PR9608 ~/.steam/root/compatibilitytools.d/
   ```
4. Restart Steam
5. In Steam → Settings → Compatibility, select "Proton-10.0-PR9608" for your game

## Patch source

- **File changed:** `lsteamclient/unixlib.cpp`
- **PR author:** diegoalejandrogomez
- **Based on:** `proton_10.0` branch