/* End-to-end GStreamer integration: a fake SEI-only AU is consumed and a
 * picture-coded AU passes through byte-identically. No camera and no MP4.
 * Uses appsrc/appsink and the loaded c545dseifilter DLL.
 */
#include <gst/gst.h>
#include <gst/app/gstappsrc.h>
#include <gst/app/gstappsink.h>
#include <stdio.h>
#include <string.h>
static int push(GstElement *src,const guint8 *bytes,gsize n,GstClockTime pts) {
    GstBuffer *b=gst_buffer_new_allocate(NULL,n,NULL);
    if(!b) return 0;
    gst_buffer_fill(b,0,bytes,n);
    GST_BUFFER_PTS(b)=pts;
    GST_BUFFER_DURATION(b)=GST_SECOND/15;
    return gst_app_src_push_buffer(GST_APP_SRC(src),b)==GST_FLOW_OK;
}
int main(int argc,char **argv) {
    gst_init(&argc,&argv);
    GstElement *pipeline=gst_pipeline_new("c545d-sei-test");
    GstElement *src=gst_element_factory_make("appsrc","testsrc");
    GstElement *filter=gst_element_factory_make("c545dseifilter","target");
    GstElement *sink=gst_element_factory_make("appsink","testsink");
    if(!pipeline||!src||!filter||!sink){fprintf(stderr,"Element unavailable\n");return 2;}
    GstCaps *caps=gst_caps_from_string("video/x-h264,parsed=(boolean)true,stream-format=(string)byte-stream,alignment=(string)au");
    g_object_set(src,"caps",caps,"format",GST_FORMAT_TIME,NULL);
    g_object_set(sink,"sync",FALSE,"emit-signals",FALSE,NULL);
    gst_caps_unref(caps);
    gst_bin_add_many(GST_BIN(pipeline),src,filter,sink,NULL);
    if(!gst_element_link_many(src,filter,sink,NULL)){fprintf(stderr,"Caps link failure\n");return 3;}
    if(gst_element_set_state(pipeline,GST_STATE_PLAYING)==GST_STATE_CHANGE_FAILURE){return 4;}
    const guint8 sei[]={0,0,0,1,9,0xf0,0,0,0,1,6,5,1,0x80};
    const guint8 pic[]={0,0,0,1,0x41,0x9a,0x22};
    if(!push(src,sei,sizeof sei,0)||!push(src,pic,sizeof pic,GST_SECOND/15)){return 5;}
    if(gst_app_src_end_of_stream(GST_APP_SRC(src))!=GST_FLOW_OK){return 6;}
    GstSample *first=gst_app_sink_try_pull_sample(GST_APP_SINK(sink),5*GST_SECOND);
    if(!first){fprintf(stderr,"Picture AU missing\n");return 7;}
    GstBuffer *out=gst_sample_get_buffer(first); GstMapInfo map;
    if(!gst_buffer_map(out,&map,GST_MAP_READ)){return 8;}
    int ok=(map.size==sizeof pic && memcmp(map.data,pic,sizeof pic)==0);
    gst_buffer_unmap(out,&map);
    gst_sample_unref(first);
    GstSample *second=gst_app_sink_try_pull_sample(GST_APP_SINK(sink),GST_SECOND);
    if(second){gst_sample_unref(second);ok=0;}
    gst_element_set_state(pipeline,GST_STATE_NULL);
    gst_object_unref(pipeline);
    if(!ok){fprintf(stderr,"Filter did not drop SEI-only or changed picture buffer\n");return 9;}
    puts("PASS GStreamer appsrc SEI-only drop and untouched picture AU");
    return 0;
}
