#!/usr/bin/env python3
"""Patch Wine's ieframe navigate_url to handle Xbox Live OAuth login.

For OAuth login URLs (login.live.com/oauth20_authorize):
  - Writes a Python OAuth helper script to /tmp (once)
  - Runs it via CreateProcessW to capture the callback
  - The helper modifies redirect_uri to localhost, opens Firefox, captures callback
  - Reads the callback URL and navigates the WebBrowser control to it
  - The game sees the callback URL in BeforeNavigate2/NavigateComplete2 events

For other http/https URLs (except OAuth callbacks):
  - Simple redirect to native browser via winebrowser.exe

OAuth callback URLs (oauth20_desktop.srf) pass through to normal navigation.
"""
import os, sys

def escape_c_string(s):
    """Escape a Python string for use as a C string literal."""
    return s.replace('\\', '\\\\').replace('"', '\\"')

filepath = sys.argv[1]
with open(filepath, "r") as f:
    content = f.read()

# Read the OAuth helper Python script (same directory as this script)
script_dir = os.path.dirname(os.path.abspath(__file__))
helper_path = os.path.join(script_dir, 'oauth_helper.py')
with open(helper_path, 'r') as f:
    helper_py = f.read()

# Convert Python script to C string literal (line-by-line)
helper_c_lines = []
for line in helper_py.split('\n'):
    helper_c_lines.append('"' + escape_c_string(line) + '\\n"')
helper_c_str = '\n            '.join(helper_c_lines)

# The C code to inject into navigate_url after the TRACE line.
inject_code = """    /* Xbox Live OAuth login handler + general http/https redirect */
    if(url && url[0]==L'h' && url[1]==L't' && url[2]==L't' && url[3]==L'p' &&
       ((url[4]==L':' && url[5]==L'/' && url[6]==L'/') ||
        (url[4]==L's' && url[5]==L':' && url[6]==L'/' && url[7]==L'/'))) {
        if(wcsstr(url, L"login.live.com") && wcsstr(url, L"oauth20_authorize")) {
            /* OAuth login URL - capture callback via Python helper */
            static int _oh_init = 0;
            static WCHAR _oh_cb[4096];
            static const char _oh_src[] =
            """ + helper_c_str + """;
            WCHAR _oh_cmd[8192], _oh_pbuf[64], _oh_pwbuf[MAX_PATH];
            DWORD _oh_pid;
            STARTUPINFOW _oh_si;
            PROCESS_INFORMATION _oh_pi;
            HANDLE _oh_hf;
            DWORD _oh_rd, _oh_sz;
            char _oh_buf[4096];
            int _oh_ok = 0;

            /* Write Python helper to /tmp on first call */
            if(!_oh_init) {
                _oh_hf = CreateFileW(L"Z:\\\\tmp\\\\_wine_oauth_helper.py",
                    GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
                if(_oh_hf != INVALID_HANDLE_VALUE) {
                    DWORD _oh_w;
                    WriteFile(_oh_hf, _oh_src, sizeof(_oh_src)-1, &_oh_w, NULL);
                    CloseHandle(_oh_hf);
                    _oh_init = 1;
                    WARN("ieframe: wrote OAuth helper to /tmp/_wine_oauth_helper.py\\n");
                }
            }
            if(_oh_init) {
                _oh_pid = GetCurrentProcessId();
                wsprintfW(_oh_pbuf, L"/tmp/_wine_oauth_cb_%u.txt", _oh_pid);
                wsprintfW(_oh_pwbuf, L"Z:\\\\tmp\\\\_wine_oauth_cb_%u.txt", _oh_pid);
                wsprintfW(_oh_cmd, L"/usr/bin/python3 /tmp/_wine_oauth_helper.py \\"%s\\" \\"%s\\"",
                          url, _oh_pbuf);
                WARN("ieframe: running OAuth helper\\n");
                memset(&_oh_si, 0, sizeof(_oh_si));
                memset(&_oh_pi, 0, sizeof(_oh_pi));
                _oh_si.cb = sizeof(_oh_si);
                if(CreateProcessW(NULL, _oh_cmd, NULL, NULL, FALSE,
                                  CREATE_NO_WINDOW, NULL, NULL, &_oh_si, &_oh_pi)) {
                    WaitForSingleObject(_oh_pi.hProcess, 300000);
                    CloseHandle(_oh_pi.hThread);
                    CloseHandle(_oh_pi.hProcess);
                    /* Read callback URL from file */
                    _oh_hf = CreateFileW(_oh_pwbuf, GENERIC_READ, 0, NULL,
                                          OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
                    if(_oh_hf != INVALID_HANDLE_VALUE) {
                        _oh_sz = GetFileSize(_oh_hf, NULL);
                        if(_oh_sz > 0 && _oh_sz < 4096) {
                            ReadFile(_oh_hf, _oh_buf, _oh_sz, &_oh_rd, NULL);
                            _oh_buf[_oh_rd] = 0;
                            for(DWORD _i = 0; _i <= _oh_rd && _i < 4095; _i++)
                                _oh_cb[_i] = (WCHAR)(unsigned char)_oh_buf[_i];
                            _oh_cb[_oh_rd < 4095 ? _oh_rd : 4095] = 0;
                            WARN("ieframe: captured OAuth callback: %s\\n",
                                 debugstr_w(_oh_cb));
                            /* Point url to callback URL so the game sees it
                             * in BeforeNavigate2 and extracts the auth code. */
                            {
                                LPCWSTR *_p = (LPCWSTR *)&url;
                                *_p = _oh_cb;
                            }
                            _oh_ok = 1;
                        }
                        CloseHandle(_oh_hf);
                    }
                    DeleteFileW(_oh_pwbuf);
                } else {
                    ERR("ieframe: CreateProcessW failed for OAuth helper\\n");
                }
            }
            if(!_oh_ok) {
                /* Fallback: simple redirect without callback capture */
                WARN("ieframe: OAuth helper failed, fallback redirect\\n");
                ShellExecuteW(NULL, NULL, L"winebrowser.exe", url, NULL, SW_SHOWNORMAL);
                set_doc_state(This, READYSTATE_COMPLETE);
                return S_OK;
            }
            /* _oh_ok: url now points to callback URL, fall through to normal nav */
        } else if(!wcsstr(url, L"oauth20_desktop.srf")) {
            /* Non-OAuth http/https URL: redirect to native browser */
            WARN("ieframe navigate_url: redirecting to native browser: %s\\n",
                 debugstr_w(url));
            ShellExecuteW(NULL, NULL, L"winebrowser.exe", url, NULL, SW_SHOWNORMAL);
            set_doc_state(This, READYSTATE_COMPLETE);
            return S_OK;
        }
        /* OAuth callback URLs: fall through to normal navigation */
    }
"""

func_anchor = 'TRACE("navigating to %s\\n", debugstr_w(url));'

if func_anchor not in content:
    print("ERROR: Could not find TRACE anchor in ieframe navigate_url")
    sys.exit(1)

if "OAuth login handler" not in content:
    content = content.replace(
        func_anchor + "\n",
        func_anchor + "\n" + inject_code,
        1
    )
    print("Injected OAuth login handler + http/https redirect into ieframe navigate_url")
else:
    print("Redirect logic already present")

with open(filepath, "w") as f:
    f.write(content)

print("Successfully patched ieframe navigate_url")