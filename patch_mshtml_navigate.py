#!/usr/bin/env python3
"""Patch Wine's mshtml navigate_url to redirect http/https URLs to xdg-open."""
import re, sys

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# 1. Add #include <unistd.h> after #include <stdarg.h>
if "#include <unistd.h>" not in content:
    content = content.replace("#include <stdarg.h>\n", "#include <stdarg.h>\n#include <unistd.h>\n", 1)
    print("Added #include <unistd.h>")
else:
    print("#include <unistd.h> already present")

# 2. Add xdg-open redirect in navigate_url after the browser check
redirect_code = """
    /* Redirect http/https URLs to native Linux browser via xdg-open.
     * Wine's mshtml cannot handle modern OAuth/Xbox Live login pages.
     * Fork+exec xdg-open so the page opens in the real browser (Firefox),
     * then return S_OK without loading anything in mshtml. */
    if(new_url && ((new_url[0]=='h' && new_url[1]=='t' && new_url[2]=='t' && new_url[3]=='p' &&
                    ((new_url[4]==':' && new_url[5]=='/' && new_url[6]=='/') ||
                     (new_url[4]=='s' && new_url[5]==':' && new_url[6]=='/' && new_url[7]=='/'))))) {
        char *url_utf8;
        int len = WideCharToMultiByte(CP_UTF8, 0, new_url, -1, NULL, 0, NULL, NULL);
        if(len > 0) {
            url_utf8 = HeapAlloc(GetProcessHeap(), 0, len);
            WideCharToMultiByte(CP_UTF8, 0, new_url, -1, url_utf8, len, NULL, NULL);
            WARN("mshtml navigate_url: redirecting to xdg-open: %s\\n", url_utf8);
            if(fork() == 0) { execlp("xdg-open", "xdg-open", url_utf8, (char*)NULL); _exit(1); }
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