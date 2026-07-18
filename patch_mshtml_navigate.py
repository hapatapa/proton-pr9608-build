#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to the
native Linux browser via ShellExecuteW.

WHY NOT system(): Wine's system() (MSVCRT._wsystem) constructs
"cmd.exe /c <cmd>" and runs it through Wine's built-in cmd.exe.
It does NOT reach the real Unix shell, so "xdg-open" never executes.

WHY ShellExecuteW: This is the standard Win32 API for opening URLs.
Wine's implementation ultimately delegates http:// URLs to the
'winebrowser' helper program, which calls __wine_unix_spawnvp()
to run xdg-open (or the user's configured browser) as a real Unix
process.  ShellExecuteW is available in shell32 which mshtml already
links against.
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# Ensure shellapi.h is included (for ShellExecuteW)
if "#include <shellapi.h>" not in content:
    # Insert after the first #include line
    content = content.replace("#include <stdarg.h>\n",
                              "#include <stdarg.h>\n#include <shellapi.h>\n", 1)
    print("Added #include <shellapi.h>")
else:
    print("#include <shellapi.h> already present")

# Add xdg-open redirect in navigate_url after the browser check.
# We use ShellExecuteW because:
#   1. It's a standard Win32 API, available in any MinGW build
#   2. Wine routes http:// URLs through 'winebrowser' which calls
#      __wine_unix_spawnvp() -> real xdg-open on the Linux host
#   3. system() does NOT work (it goes through cmd.exe, not Unix shell)
redirect_code = """
    /* Redirect http/https URLs to native Linux browser.
     * Wine's mshtml (IE engine) cannot render modern OAuth/Xbox Live
     * login pages.  ShellExecuteW delegates to winebrowser which calls
     * xdg-open on the Linux host. */
    if(new_url && ((new_url[0]=='h' && new_url[1]=='t' && new_url[2]=='t' && new_url[3]=='p' &&
                    ((new_url[4]==':' && new_url[5]=='/' && new_url[6]=='/') ||
                     (new_url[4]=='s' && new_url[5]==':' && new_url[6]=='/' && new_url[7]=='/'))))) {
        WARN("mshtml navigate_url: redirecting to native browser: %s\\n",
             debugstr_w(new_url));
        ShellExecuteW(NULL, L"open", new_url, NULL, NULL, SW_SHOWNORMAL);
        return S_OK;
    }
"""

func_pattern = r'(HRESULT navigate_url\(HTMLOuterWindow \*window.*?if\(!window->browser\)\s+return E_UNEXPECTED;\n)'
m = re.search(func_pattern, content, re.DOTALL)
if not m:
    print("ERROR: Could not find navigate_url function with browser check")
    sys.exit(1)

content = content[:m.end()] + redirect_code + content[m.end():]

with open(filepath, "w") as f:
    f.write(content)

print("Successfully patched navigate_url in mshtml")