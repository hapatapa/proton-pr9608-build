#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to xdg-open.

Uses system() which is available in MinGW/UCRT and routed by Wine to
the real Unix system() call. This avoids fork()/execlp() which are
POSIX-only and not available in MinGW cross-compilation.
"""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# Ensure stdlib.h is included (for system(), snprintf)
if "#include <stdlib.h>" not in content:
    # Insert after the first #include line
    content = content.replace("#include <stdarg.h>\n", "#include <stdarg.h>\n#include <stdlib.h>\n", 1)
    print("Added #include <stdlib.h>")
else:
    print("#include <stdlib.h> already present")

# Add xdg-open redirect in navigate_url after the browser check.
# We use system() instead of fork()/execlp() because Wine DLLs are
# cross-compiled with MinGW which doesn't provide POSIX functions.
# Wine's UCRT implementation of system() calls the real Unix system().
redirect_code = """
    /* Redirect http/https URLs to native Linux browser via xdg-open.
     * Wine's mshtml cannot handle modern OAuth/Xbox Live login pages.
     * Use system() (routed by Wine to Unix system()) to launch xdg-open
     * in the background, then return S_OK without loading in mshtml. */
    if(new_url && ((new_url[0]=='h' && new_url[1]=='t' && new_url[2]=='t' && new_url[3]=='p' &&
                    ((new_url[4]==':' && new_url[5]=='/' && new_url[6]=='/') ||
                     (new_url[4]=='s' && new_url[5]==':' && new_url[6]=='/' && new_url[7]=='/'))))) {
        char *url_utf8;
        int len = WideCharToMultiByte(CP_UTF8, 0, new_url, -1, NULL, 0, NULL, NULL);
        if(len > 0) {
            char *cmd;
            url_utf8 = HeapAlloc(GetProcessHeap(), 0, len);
            WideCharToMultiByte(CP_UTF8, 0, new_url, -1, url_utf8, len, NULL, NULL);
            WARN("mshtml navigate_url: redirecting to xdg-open: %s\\n", url_utf8);
            /* Allocate cmd buffer: "xdg-open '<url>' &" + NUL */
            cmd = HeapAlloc(GetProcessHeap(), 0, len + 16);
            snprintf(cmd, len + 16, "xdg-open '%s' &", url_utf8);
            system(cmd);
            HeapFree(GetProcessHeap(), 0, cmd);
            HeapFree(GetProcessHeap(), 0, url_utf8);
        }
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