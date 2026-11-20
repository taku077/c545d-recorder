/* Disposable CI-only packaged application entry point. Never launched.
 * No RTSP, media, network, filesystem writes, credentials or registry.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
int WINAPI wWinMain(HINSTANCE h, HINSTANCE prev, PWSTR args, int show) {
  (void)h; (void)prev; (void)args; (void)show;
  return 0;
}
