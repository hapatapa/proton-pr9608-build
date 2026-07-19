#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to the
native Linux browser via winebrowser.exe.

Uses ShellExecuteW to launch winebrowser.exe directly (bypasses broken
URL protocol handlers in the Wine prefix registry like open-in-firefox.bat).
Chain: ShellExecuteW("winebrowser.exe", url) -> winebrowser.exe -> __wine_unix_spawnvp -> xdg-open
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# --- Step 1: Insert ShellExecuteW forward declaration before navigate_url ---
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
# KEY FIX: Use winebrowser.exe as the program, url as parameter.
# This bypasses Wine's URL protocol handler registry entries (e.g. open-in-firefox.bat)
# and goes directly: winebrowser.exe -> __wine_unix_spawnvp -> xdg-open -> native browser
redirect_code = """    /* Redirect http/https URLs to native Linux browser via winebrowser.exe.
     * We launch winebrowser.exe directly (not ShellExecute "open" on the URL) to bypass
     * broken URL protocol handlers in the Wine prefix (e.g. open-in-firefox.bat).
     * Chain: ShellExecuteW(winebrowser.exe, url) -> __wine_unix_spawnvp -> xdg-open */
    if(new_url && (new_url[0]=='h' && new_url[1]=='t' && new_url[2]=='t' && new_url[3]=='p' &&
                   ((new_url[4]==':' && new_url[5]=='/' && new_url[6]=='/') ||
                    (new_url[4]=='s' && new_url[5]==':' && new_url[6]=='/' && new_url[7]=='/')))) {
        WARN("mshtml navigate_url: redirecting to native browser: %s\\n",
             debugstr_w(new_url));
        ShellExecuteW(NULL, NULL, L"winebrowser.exe", new_url, NULL, SW_SHOWNORMAL);
        return S_OK;
    }
"""

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
