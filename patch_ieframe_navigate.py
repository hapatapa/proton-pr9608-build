#!/usr/bin/env python3
"""Patch Wine's ieframe navigate_url to redirect http/https URLs to the
native Linux browser via ShellExecuteW.

ieframe/navigate_url is the entry point for IWebBrowser2::Navigate(), which
is what games call to open URLs in the embedded IE WebBrowser control.

Unlike mshtml/navigate.c (which only handles JS-triggered navigations),
ieframe/navigate.c already includes shellapi.h and links against shell32,
so ShellExecuteW is available without any forward declarations.
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# The redirect code to inject right after the TRACE line in navigate_url.
# Uses 4-space indent to match Wine's coding style.
# We check url (not new_url) since that's the parameter name in ieframe.
redirect_code = """    /* Redirect http/https URLs to native Linux browser via ShellExecuteW.
     * Chain: ShellExecuteW -> shell32 -> winebrowser.exe -> __wine_unix_spawnvp -> xdg-open */
    if(url && url[0]=='h' && url[1]=='t' && url[2]=='t' && url[3]=='p' &&
       ((url[4]==':' && url[5]=='/' && url[6]=='/') ||
        (url[4]=='s' && url[5]==':' && url[6]=='/' && url[7]=='/'))) {
        WARN("ieframe navigate_url: redirecting to native browser: %s\\n", debugstr_w(url));
        ShellExecuteW(NULL, L"open", url, NULL, NULL, SW_SHOWNORMAL);
        set_doc_state(This, READYSTATE_COMPLETE);
        return S_OK;
    }

"""

# Anchor: find the navigate_url function in ieframe (not mshtml).
# The signature is unique: navigate_url(DocHost *This, LPCWSTR url, ...
# We insert right after the TRACE line.
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