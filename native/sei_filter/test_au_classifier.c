#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "h264_au_classifier.h"
static int failed=0;
static void check(const char *name,const uint8_t *d,size_t n,int expected){
  int actual=c545d_classify_h264_au(d,n);
  if(actual!=expected){fprintf(stderr,"FAIL %s actual=%d expected=%d\n",name,actual,expected);failed++;}
  else printf("PASS %s\n",name);
}
int main(void){
  const uint8_t sei_only[] = {0,0,0,1,9,0xf0,0,0,0,1,6,5,1,0x80};
  const uint8_t sei_only_3[] = {0,0,1,6,5,2,0x80};
  const uint8_t sei_and_idr[] = {0,0,0,1,9,0xf0,0,0,0,1,6,5,1,0x80,0,0,1,0x65,0x88,0x84};
  const uint8_t pic_only[] = {0,0,0,1,0x41,0x9a,0x22};
  const uint8_t sps_only[] = {0,0,0,1,0x67,0x42,0,0x1f};
  const uint8_t sps_sei[] = {0,0,0,1,0x67,0x42,0,0x1f,0,0,0,1,6,0x80};
  const uint8_t unknown[] = {0,0,0,1,0x7e,0x20,0x00};
  const uint8_t avc_length[] = {0,0,0,4,6,0x42,0x33,0x01};
  const uint8_t malformed[] = {0,0,1};
  const uint8_t forbidden[] = {0,0,0,1,0x86,0x80};
  const uint8_t sei_filler[] = {0,0,0,1,6,0x80,0,0,1,0x0c,0x80};
  check("SEI-only AUD + SEI",sei_only,sizeof sei_only,1);
  check("SEI-only 3 byte",sei_only_3,sizeof sei_only_3,1);
  check("SEI plus IDR preserved",sei_and_idr,sizeof sei_and_idr,0);
  check("P frame preserved",pic_only,sizeof pic_only,0);
  check("SPS preserved",sps_only,sizeof sps_only,0);
  check("SPS plus SEI preserved",sps_sei,sizeof sps_sei,0);
  check("unknown NAL preserved",unknown,sizeof unknown,0);
  check("AVCC unknown fallback",avc_length,sizeof avc_length,0);
  check("malformed pass-through",malformed,sizeof malformed,0);
  check("forbidden bit pass-through",forbidden,sizeof forbidden,0);
  check("SEI and filler",sei_filler,sizeof sei_filler,1);
  /* Fuzz short payloads. No crashes/overflow, don't assume content semantics. */
  for(unsigned sz=0;sz<=255;sz++){
    uint8_t b[256]={0}; for(unsigned j=0;j<sz;j++)b[j]=(uint8_t)(sz+j*37);
    (void)c545d_classify_h264_au(b,sz);
  }
  return failed?1:0;
}
