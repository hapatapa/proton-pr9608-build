#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to the
native Linux browser via ShellExecuteW.

The forward declaration of ShellExecuteW is placed right before the
navigate_url function, where all Wine headers (and thus HWND, WCHAR,
INT, HINSTANCE, WINAPI) are already defined.
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# --- Step 1: Insert ShellExecuteW forward declaration before navigate_url ---
# Proton 10.0 Wine signature (4 params including IUri *base_uri):
#   HRESULT navigate_url(HTMLOuterWindow *window, const WCHAR *new_url, IUri *base_uri, DWORD flags)
# We match just the start to be robust against future signature changes.
declare_code = """/* Forward declaration for ShellExecuteW (linked from shell32).
 * Cannot #include <shellapi.h> due to type conflicts with mshtml headers.
 * All types (HWND, WCHAR, INT, HINSTANCE, WINAPI) are already defined
 * by Wine headers included earlier in this file. */
#ifndef SW_SHOWNORMAL
#define SW_SHOWNORMAL 1
#endif
extern HINSTANCE WINAPI ShellExecuteW(HWND, const WCHAR *, const WCHAR *,
    const WCHAR *, const WCHAR *, INT);

"""

# Anchor: match the function definition line flexibly
# Use a regex to find the navigate_url function definition
func_def_pattern = r'^(HRESULT\s+navigate_url\s*\()'
func_match = re.search(func_def_pattern, content, re.MULTILINE)

if "extern HINSTANCE WINAPI ShellExecuteW" not in content:
    if func_match:
        insert_pos = func_match.start()
        content = content[:insert_pos] + declare_code + content[insert_pos:]
        print(f"Inserted ShellExecuteW forward declaration at line {content[:insert_pos].count(chr(10))+1}")
    else:
        print("ERROR: Could not find navigate_url function definition")
        sys.exit(1)
else:
    print("ShellExecuteW forward declaration already present")

# --- Step 2: Insert redirect logic after the browser null-check ---
redirect_code = """    /* Redirect http/https URLs to native Linux browser via ShellExecuteW.
     * Chain: ShellExecuteW -> shell32 -> winebrowser.exe -> __wine_unix_spawnvp -> xdg-open */
    if(new_url && (new_url[0]=='h' && new_url[1]=='t' && new_url[2]=='t' && new_url[3]=='p' &&
                   ((new_url[4]==':' && new_url[5]=='/' && new_url[6]=='/') ||
                    (new_url[4]=='s' && new_url[5]==':' && new_url[6]=='/' && new_url[7]=='/')))) {
        WARN("mshtml navigate_url: redirecting to native browser: %s\\n",
             debugstr_w(new_url));
        ShellExecuteW(NULL, L"open", new_url, NULL, NULL, SW_SHOWNORMAL);
        return S_OK;
    }
"""

# We must find the browser check INSIDE navigate_url, not in other functions.
# There are multiple 'if(!window->browser)' in navigate.c (e.g. navigate_new_window).
# Strategy: re-find navigate_url function def (after Step 1 may have shifted positions),
# then search for the browser check only after that point.
func_def_pattern2 = r'^(HRESULT\s+navigate_url\s*\()'
func_match2 = re.search(func_def_pattern2, content, re.MULTILINE)
if not func_match2:
    print("ERROR: Could not re-find navigate_url function definition")
    sys.exit(1)

search_start = func_match2.start()
search_region = content[search_start:]

browser_check_pattern = r'(if\s*\(\s*!window->browser\s*\)\s*\n\s*return\s+E_UNEXPECTED\s*;\s*\n)'
m = re.search(browser_check_pattern, search_region)

if not m:
    print("ERROR: Could not find 'if(!window->browser) return E_UNEXPECTED;' in navigate_url")
    print("Showing first 600 chars after navigate_url def:")
    print(repr(search_region[:600]))
    sys.exit(1)

if "redirecting to native browser" not in content:
    abs_pos = search_start + m.end()
    content = content[:abs_pos] + redirect_code + content[abs_pos:]
    print(f"Injected http/https redirect logic after browser check (at pos {abs_pos})")
else:
    print("Redirect logic already present")

with open(filepath, "w") as f:
    f.write(content)

print("Successfully patched navigate_url in mshtml")