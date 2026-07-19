#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to the
native Linux browser via ShellExecuteW.

Key insight: the forward declaration of ShellExecuteW must be placed AFTER
all Wine headers have been included (so HWND, WCHAR, INT, WINAPI, HINSTANCE
etc. are already defined), NOT at the top of the file after stdarg.h.
Placing it right before the navigate_url function ensures all types exist.
We cannot #include <shellapi.h> because it conflicts with mshtml's other
includes (expected '{' at end of input).
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# The forward declaration to inject right before navigate_url function.
# By this point in the file, ALL Wine types are already defined:
# HWND, WCHAR, INT, HINSTANCE, WINAPI (from windef.h, winnt.h, etc.)
# We only need to guard SW_SHOWNORMAL in case shellapi.h wasn't included.
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

# Insert declaration right before the navigate_url function definition.
# The function signature is unique and serves as a reliable anchor.
func_anchor = "HRESULT navigate_url(HTMLOuterWindow *window, const WCHAR *new_url, DWORD flags)"

if "extern HINSTANCE WINAPI ShellExecuteW" not in content:
    if func_anchor in content:
        content = content.replace(
            func_anchor,
            declare_code + func_anchor,
            1
        )
        print("Inserted ShellExecuteW forward declaration before navigate_url")
    else:
        print("ERROR: Could not find navigate_url function signature")
        idx = content.find("navigate_url")
        if idx >= 0:
            print("Found 'navigate_url' at index", idx)
            print("Context:", repr(content[idx:idx+300]))
        sys.exit(1)
else:
    print("ShellExecuteW forward declaration already present")

# Now inject the redirect logic after the browser null-check.
redirect_code = """        /* Redirect http/https URLs to native Linux browser via ShellExecuteW.
         * Chain: ShellExecuteW -> shell32 -> winebrowser.exe -> __wine_unix_spawnvp -> xdg-open */
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
    # Broader pattern in case whitespace differs
    func_pattern2 = r'(HRESULT navigate_url\(HTMLOuterWindow \*window[^\{]*\{[^}]*?if\s*\(\s*!window->browser\s*\)\s*return\s+E_UNEXPECTED\s*;\s*\n)'
    m = re.search(func_pattern2, content, re.DOTALL)
    if not m:
        print("ERROR: Could not find navigate_url browser check")
        idx = content.find("navigate_url")
        if idx >= 0:
            print("Context around navigate_url:", repr(content[idx:idx+500]))
        sys.exit(1)

if "redirecting to native browser" not in content:
    content = content[:m.end()] + redirect_code + content[m.end():]
    print("Injected http/https redirect logic into navigate_url")
else:
    print("Redirect logic already present")

with open(filepath, "w") as f:
    f.write(content)

print("Successfully patched navigate_url in mshtml")