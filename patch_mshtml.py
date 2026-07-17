#!/usr/bin/env python3
"""Patch Wine's mshtml/navigate.c to redirect http/https URLs to xdg-open.
Works even if line numbers differ between Wine versions."""
import sys, re

INSERT_AFTER_INCLUDES = r'''#include <unistd.h>
#include <sys/wait.h>'''

NEW_FUNCTION = r'''
/* Check if a wide string starts with a given ASCII prefix */
static BOOL starts_with_w(const WCHAR *str, const char *prefix)
{
    while(*prefix) {
        if(*str++ != (WCHAR)(*prefix++))
            return FALSE;
    }
    return TRUE;
}

/* Redirect http/https navigations to native Linux browser via xdg-open.
 * This fixes Xbox Live auth in games that embed Wine's IE (mshtml). */
static HRESULT super_navigate_xdg_open(HTMLOuterWindow *window, IUri *uri)
{
    BSTR url_bstr = NULL;
    HRESULT hres;

    hres = IUri_GetDisplayUri(uri, &url_bstr);
    if(FAILED(hres) || !url_bstr)
        return E_FAIL;

    if(starts_with_w(url_bstr, "http://") || starts_with_w(url_bstr, "https://")) {
        char url_utf8[4096];
        int len = WideCharToMultiByte(CP_UTF8, 0, url_bstr, -1, url_utf8, sizeof(url_utf8), NULL, NULL);
        if(len > 0) {
            pid_t pid = fork();
            if(pid == 0) {
                execlp("xdg-open", "xdg-open", url_utf8, (char*)NULL);
                _exit(1);
            }
            WARN("mshtml: redirected to xdg-open: %s (pid %d)\\n", url_utf8, pid);
        }
        SysFreeString(url_bstr);
        return S_OK;
    }
    SysFreeString(url_bstr);
    return E_FAIL; /* Not http/https, let original handle it */
}
'''

SUPER_NAVIGATE_HOOK = r'''    /* Try redirecting http/https URLs to native browser */
    hres = super_navigate_xdg_open(window, uri);
    if(SUCCEEDED(hres))
        return hres;
'''

filepath = sys.argv[1] if len(sys.argv) > 1 else "dlls/mshtml/navigate.c"

with open(filepath, 'r') as f:
    content = f.read()

# 1. Add includes after existing includes
# Find the last #include line before the first non-include code
include_re = re.compile(r'^#include\s', re.MULTILINE)
matches = list(include_re.finditer(content))
if not matches:
    print("ERROR: No #include found", file=sys.stderr)
    sys.exit(1)

last_include_end = matches[-1].end()
content = content[:last_include_end] + '\n' + INSERT_AFTER_INCLUDES + content[last_include_end:]
print(f"Added unistd.h/wait.h includes after line {matches[-1].start()+1}")

# 2. Add the redirect function before super_navigate
# Find super_navigate function definition
super_nav_match = re.search(r'^HRESULT super_navigate\(HTMLOuterWindow \*window, IUri \*uri, DWORD flags,', content, re.MULTILINE)
if not super_nav_match:
    print("ERROR: Could not find super_navigate function", file=sys.stderr)
    sys.exit(1)

insert_pos = super_nav_match.start()
content = content[:insert_pos] + NEW_FUNCTION + '\n' + content[insert_pos:]
print(f"Added super_navigate_xdg_open before super_navigate at line ~{content[:insert_pos].count(chr(10))+1}")

# 3. Add the hook call inside super_navigate, after the uri_nofrag check
# Re-find super_navigate (line numbers shifted)
super_nav_match2 = re.search(r'^HRESULT super_navigate\(HTMLOuterWindow \*window, IUri \*uri, DWORD flags,', content, re.MULTILINE)

# Find the pattern: uri_nofrag = get_uri_nofrag(uri); ... if(!uri_nofrag) return E_FAIL;
hook_pattern = re.compile(
    r'(uri_nofrag = get_uri_nofrag\(uri\);\s*\n'
    r'\s*if\(!uri_nofrag\)\s*\n'
    r'\s*return E_FAIL;)'
)

hook_match = hook_pattern.search(content, super_nav_match2.start())
if not hook_match:
    print("ERROR: Could not find uri_nofrag check in super_navigate", file=sys.stderr)
    sys.exit(1)

insert_after = hook_match.end()
content = content[:insert_after] + '\n' + SUPER_NAVIGATE_HOOK + content[insert_after:]
print(f"Added xdg-open redirect hook in super_navigate after uri_nofrag check")

with open(filepath, 'w') as f:
    f.write(content)

print(f"Successfully patched {filepath}")