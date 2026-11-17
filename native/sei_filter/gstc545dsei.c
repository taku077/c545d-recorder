/* Optional H264 AU-native filter, intentionally restricted to byte-stream/AU.
 * This is a GStreamer *decode-input* filter, not an MP4 encoder/sink modifier.
 * It drops only SEI-only access units which have no VCL picture, retaining
 * all picture-carrying AUs and any SPS/PPS-containing AU unchanged.
 * Such SEI may contain metadata: opt-in only; default legacy path stays intact.
 */
#include <gst/gst.h>
#include <gst/base/gstbasetransform.h>
#include "h264_au_classifier.h"
#ifndef PACKAGE
#define PACKAGE "c545d"
#endif
#ifndef VERSION
#define VERSION "0.1.0"
#endif
typedef struct _GstC545dSeiFilter {
  GstBaseTransform parent;
  volatile gint dropped;
} GstC545dSeiFilter;
typedef struct _GstC545dSeiFilterClass {
  GstBaseTransformClass parent_class;
} GstC545dSeiFilterClass;
G_DEFINE_TYPE(GstC545dSeiFilter,gst_c545d_sei_filter,GST_TYPE_BASE_TRANSFORM)

static GstStaticPadTemplate sink_template = GST_STATIC_PAD_TEMPLATE(
  "sink", GST_PAD_SINK, GST_PAD_ALWAYS, GST_STATIC_CAPS(
  "video/x-h264,parsed=(boolean)true,stream-format=(string)byte-stream,alignment=(string)au"));
static GstStaticPadTemplate src_template = GST_STATIC_PAD_TEMPLATE(
  "src", GST_PAD_SRC, GST_PAD_ALWAYS, GST_STATIC_CAPS(
  "video/x-h264,parsed=(boolean)true,stream-format=(string)byte-stream,alignment=(string)au"));

static GstFlowReturn gst_c545d_sei_filter_transform_ip(GstBaseTransform *base,GstBuffer *buffer) {
  GstMapInfo map;
  if (!gst_buffer_map(buffer,&map,GST_MAP_READ)) return GST_FLOW_OK;
  enum C545DAuDisposition decision = c545d_classify_h264_au(map.data,map.size);
  gst_buffer_unmap(buffer,&map);
  if (decision == C545D_AU_SEI_ONLY) {
    GstC545dSeiFilter *self=(GstC545dSeiFilter*)base;
    gint old=g_atomic_int_add(&self->dropped,1);
    if ((old % 1024) == 0) {
      GST_INFO_OBJECT(base,"dropping SEI-only non-picture AU (cumulative=%d)",old+1);
    }
    return GST_BASE_TRANSFORM_FLOW_DROPPED;
  }
  return GST_FLOW_OK;
}
static void gst_c545d_sei_filter_class_init(GstC545dSeiFilterClass *klass) {
  GstElementClass *element_class=GST_ELEMENT_CLASS(klass);
  GstBaseTransformClass *transform_class=GST_BASE_TRANSFORM_CLASS(klass);
  gst_element_class_set_static_metadata(element_class,
    "C545D SEI-only AU decoder guard","Filter/Video",
    "Exclude non-picture standalone SEI-only H264 access units before decoding",
    "C545D recorder project");
  gst_element_class_add_static_pad_template(element_class,&sink_template);
  gst_element_class_add_static_pad_template(element_class,&src_template);
  transform_class->passthrough_on_same_caps=FALSE;
  transform_class->transform_ip_on_passthrough=TRUE;
  transform_class->transform_ip=gst_c545d_sei_filter_transform_ip;
}
static void gst_c545d_sei_filter_init(GstC545dSeiFilter *self) {
  g_atomic_int_set(&self->dropped,0);
  /* Read only, never copies decoded buffers. BaseTransform will still run
   * transform_ip because transform_ip_on_passthrough is TRUE. */
  gst_base_transform_set_passthrough(GST_BASE_TRANSFORM(self),TRUE);
}
static gboolean c545d_plugin_init(GstPlugin *plugin) {
  return gst_element_register(plugin,"c545dseifilter",GST_RANK_NONE,
    gst_c545d_sei_filter_get_type());
}
GST_PLUGIN_DEFINE(GST_VERSION_MAJOR,GST_VERSION_MINOR,c545dsei,
  "C545D SEI-only AU decoder guard",c545d_plugin_init,VERSION,"LGPL",PACKAGE,
  "https://github.com/taku077/c545d-recorder")
