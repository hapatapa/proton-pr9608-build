#!/usr/bin/env python3
"""Patch Wine's ieframe navigate_url to redirect http/https URLs to the
native Linux browser via winebrowser.exe.

ieframe/navigate_url is the entry point for IWebBrowser2::Navigate(), which
is what games call to open URLs in the embedded IE WebBrowser control.

Uses ShellExecuteW to launch winebrowser.exe directly (bypasses broken
URL protocol handlers in the Wine prefix registry like open-in-firefox.bat).
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# KEY FIX: Use winebrowser.exe as the program, url as parameter.
# This bypasses Wine's URL protocol handler registry entries.
redirect_code = """    /* Redirect http/https URLs to native Linux browser via winebrowser.exe.
     * We launch winebrowser.exe directly to bypass broken URL protocol handlers
     * in the Wine prefix (e.g. open-in-firefox.bat).
     * Chain: ShellExecuteW(winebrowser.exe, url) -> __wine_unix_spawnvp -> xdg-open */
    if(url && url[0]=='h' && url[1]=='t' && url[2]=='t' && url[3]=='p' &&
       ((url[4]==':' && url[5]=='/' && url[6]=='/') ||
        (url[4]=='s' && url[5]==':' && url[6]=='/' && url[7]=='/'))) {
        WARN("ieframe navigate_url: redirecting to native browser: %s\\n", debugstr_w(url));
        ShellExecuteW(NULL, NULL, L"winebrowser.exe", url, NULL, SW_SHOWNORMAL);
        set_doc_state(This, READYSTATE_COMPLETE);
        return S_OK;
    }

"""

func_anchor = 'TRACE("navigating to %s\\n", debugstr_w(url));'

if func_anchor not in content:
    print("ERROR: Could not find TRACE anchor in ieframe navigate_url")
    sys.exit(1)

if "redirecting to native browser" not in content:
    content = content.replace(
        func_anchor + "\n",
        func_anchor + "\n" + redirect_code,
        1
    )
    print("Injected http/https redirect into ieframe navigate_url")
else:
    print("Redirect logic already present")

with open(filepath, "w") as f:
    f.write(content)

print("Successfully patched ieframe navigate_url")
