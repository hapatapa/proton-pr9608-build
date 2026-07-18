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
links against (see Makefile.in IMPORTS).

NOTE: We do NOT #include <shellapi.h> because it causes massive type
conflicts in navigate.c.  Instead we forward-declare ShellExecuteW.
Since mshtml links shell32, the linker will resolve it.
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# Add a forward declaration for ShellExecuteW instead of including
# shellapi.h (which causes type conflicts in this translation unit).
# We also need SW_SHOWNORMAL (=1).
declare_code = """
/* Forward declarations for ShellExecuteW (linked from shell32).
 * We cannot #include <shellapi.h> here due to type conflicts. */
#ifndef SW_SHOWNORMAL
#define SW_SHOWNORMAL 1
#endif
extern HINSTANCE WINAPI ShellExecuteW(HWND hwnd, const WCHAR *lpOperation,
    const WCHAR *lpFile, const WCHAR *lpParameters, const WCHAR *lpDirectory,
    INT nShowCmd);
"""

if "extern HINSTANCE WINAPI ShellExecuteW" not in content:
    # Insert after the last #include before the first C code
    content = content.replace("#include <stdarg.h>\n",
                              "#include <stdarg.h>\n" + declare_code, 1)
    print("Added ShellExecuteW forward declaration")
else:
    print("ShellExecuteW declaration already present")

# Add redirect in navigate_url after the browser check.
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