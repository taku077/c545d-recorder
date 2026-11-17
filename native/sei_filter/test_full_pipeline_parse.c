/* Parse the ACTUAL PowerShell-generated gst-launch argument vector without
 * connecting to RTSP, creating MP4, or setting the pipeline to PLAYING.
 * Strict: even recoverable parser/link errors are fatal for release.
 * This is a production graph syntax/element-linking test, not a full
 * real-camera streaming test. The input contains synthetic credentials only.
 */
#include <gst/gst.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
  gchar *content=NULL; gsize len=0; GError *error=NULL; int result=1;
  if (argc!=2) { fputs("Usage: test_full_pipeline_parse tokenfile\n",stderr); return 2; }
  gst_init(&argc,&argv);
  if (!g_file_get_contents(argv[1],&content,&len,&error)) {
    fputs("Failed reading synthetic graph tokens\n",stderr);
    if(error) g_clear_error(&error);
    return 2;
  }
  gchar **tokens=g_strsplit(content,"\n",-1);
  size_t count=0;
  while(tokens[count]) {
    size_t n=strlen(tokens[count]);
    if(n && tokens[count][n-1]=='\r')tokens[count][n-1]=0;
    if(tokens[count][0]==0)break;
    count++;
  }
  tokens[count]=NULL;
  if(count<75){fputs("Unexpectedly short production graph\n",stderr);goto done;}
  GstElement *pipeline=gst_parse_launchv((const gchar **)tokens,&error);
  if(error){
    /* CI is synthetic-only: there are no real addresses or passwords here. */
    fprintf(stderr,"GSTREAMER PARSE FAILED: %s\n",error->message);
    g_clear_error(&error);
  }else if(!pipeline){
    fputs("GSTREAMER PARSE FAILED: null pipeline\n",stderr);
  }else{
    fprintf(stdout,"PASS actual assembled production graph: %zu tokens\n",count);
    result=0;
  }
  if(pipeline)gst_object_unref(pipeline);
done:
  g_strfreev(tokens);
  g_free(content);
  return result;
}
