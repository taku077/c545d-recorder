/*
 * Tiny CI-ONLY Windows COM apartment contract test. NO GIO DLL is loaded.
 * It tests the exact CoInitializeEx success/S_FALSE/failure guard used by
 * tests/patch_glib_2824_parser_com_balance_ci.py on fresh worker threads.
 * This does not establish GLib binary compatibility or fix memory leaks.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <objbase.h>
#include <stdio.h>

typedef struct {
    int scenario;
    int success;
} State;

static int apartment_is(APTTYPE expected) {
    APTTYPE type;
    APTTYPEQUALIFIER qualifier;
    const HRESULT hr = CoGetApartmentType(&type, &qualifier);
    return hr == S_OK && type == expected;
}

static DWORD WINAPI run_scenario(LPVOID ctx) {
    State *state = (State *)ctx;
    HRESULT owned, result, second;
    APTTYPE at;
    APTTYPEQUALIFIER qualifier;
    state->success = 0;
    if (state->scenario == 1) {
        /* Brand new STA thread: first init S_OK, second init S_FALSE. */
        owned = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
        if (owned != S_OK) return 10;
        second = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
        if (second != S_FALSE) {
            CoUninitialize();
            return 11;
        }
        /* Candidate guard MUST balance even S_FALSE. */
        if (second == S_OK || second == S_FALSE) CoUninitialize();
        if (!apartment_is(APTTYPE_STA)) {
            CoUninitialize();
            return 12;
        }
        CoUninitialize();
        state->success = 1;
        return 0;
    }
    owned = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (owned != S_OK) return 20;
    result = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (result != RPC_E_CHANGED_MODE) {
        CoUninitialize();
        return 21;
    }
    if (state->scenario == 2) {
        /* Fixed source guard: do NOT uninitialize on failed init. */
        if (result == S_OK || result == S_FALSE) CoUninitialize();
        if (!apartment_is(APTTYPE_MTA)) {
            CoUninitialize();
            return 22;
        }
        CoUninitialize();
        state->success = 1;
        return 0;
    }
    if (state->scenario == 3) {
        /* Negative-control: old unconditional cleanup over-uninitializes
         * the *previous* successful MTA initialization after changed mode.
         * Run this ONLY on this throwaway isolated CI thread.
         */
        CoUninitialize();
        second = CoGetApartmentType(&at, &qualifier);
        if (second != CO_E_NOTINITIALIZED) return 31;
        state->success = 1;
        return 0;
    }
    CoUninitialize();
    return 40;
}

int main(void) {
    int scenario;
    for (scenario = 1; scenario <= 3; ++scenario) {
        HANDLE thread;
        DWORD exit_code = 0xffffffffu;
        State state;
        DWORD wait_result;
        state.scenario = scenario;
        state.success = 0;
        thread = CreateThread(NULL, 0, run_scenario, &state, 0, NULL);
        if (thread == NULL) return 60;
        wait_result = WaitForSingleObject(thread, 10000);
        if (wait_result == WAIT_OBJECT_0 && !GetExitCodeThread(thread, &exit_code))
            exit_code = 0xfffffffeu;
        CloseHandle(thread);
        if (wait_result != WAIT_OBJECT_0 || exit_code != 0 || !state.success) {
            printf("C545D_COM_APARTMENT_CONTRACT_FAIL,scenario=%d,status=%lu\n",
                   scenario, (unsigned long)exit_code);
            return 2;
        }
    }
    puts("C545D_COM_APARTMENT_CONTRACT_PASS,STA_OK=1,STA_SFALSE=1,"
         "MTA_CHANGED_MODE_GUARDED=1,legacy_failure_exposed=1,"
         "GIO_DLL_UNTESTED=1,windows_runner_only=1,user_host_modified=0");
    return 0;
}
