/* C545D H.264 access-unit classifier (dependency-free, C11).
 * This function is deliberately conservative. Drop only complete Annex B AUs
 * consisting of SEI NAL type 6, optional AUD 9 or filler 12. Pass VCL pictures,
 * SPS/PPS, unsupported extensions and malformed buffers untouched.
 * An SEI-only AU cannot yield a decoded picture, but may contain metadata.
 * This filter is opt-in and should not be used where that metadata is required.
 * It does not rewrite, allocate or re-time H.264 data.
 */
#ifndef C545D_H264_AU_CLASSIFIER_H
#define C545D_H264_AU_CLASSIFIER_H
#include <stddef.h>
#include <stdint.h>
enum C545DAuDisposition { C545D_AU_PASS = 0, C545D_AU_SEI_ONLY = 1 };
static int c545d_start_code(const uint8_t *d, size_t n, size_t pos, size_t *sz) {
    if (pos + 3 > n || d[pos] != 0 || d[pos+1] != 0) return 0;
    if (d[pos+2] == 1) { *sz=3; return 1; }
    if (pos + 4 <= n && d[pos+2] == 0 && d[pos+3] == 1) { *sz=4; return 1; }
    return 0;
}
static enum C545DAuDisposition c545d_classify_h264_au(const uint8_t *d,size_t n) {
    if (!d || n < 5) return C545D_AU_PASS;
    size_t sc = 0, at = 0, pos = 0;
    /* At most a small number of leading zero bytes before Annex B start. */
    while (at < n && d[at] == 0 && at < 4) at++;
    if (at == 0 || at > 3) return C545D_AU_PASS;
    size_t start = 0;
    if (!c545d_start_code(d,n,0,&sc)) {
        /* Also allow one extra leading_zero_8bits */
        if (d[0] != 0 || !c545d_start_code(d,n,1,&sc)) return C545D_AU_PASS;
        start = 1;
    }
    int saw_sei = 0;
    size_t checks = 0;
    while (start < n) {
        if (++checks > 65536) return C545D_AU_PASS; /* fail open */
        if (!c545d_start_code(d,n,start,&sc)) return C545D_AU_PASS;
        pos = start + sc;
        if (pos >= n) return C545D_AU_PASS;
        uint8_t h = d[pos];
        if (h & 0x80) return C545D_AU_PASS; /* forbidden_zero_bit */
        unsigned type = h & 31;
        if (type == 6) saw_sei = 1;
        else if (type != 9 && type != 12) return C545D_AU_PASS;
        /* Scan for next valid start code (emulation prevention makes this safe).
         * Do not allocate or touch payload bytes. */
        size_t next = pos + 1, nsc = 0;
        for (; next + 3 <= n; next++)
            if (c545d_start_code(d,n,next,&nsc)) break;
        if (next + 3 > n) break;
        /* Padding zeros before next start are allowed. */
        start = next;
    }
    return saw_sei ? C545D_AU_SEI_ONLY : C545D_AU_PASS;
}
#endif
