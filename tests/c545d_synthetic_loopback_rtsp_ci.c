/*
 * Windows CI ONLY. Genuine gst-rtsp-server dual synthetic endpoint and client.
 * Server binds strictly to 127.0.0.1:554 and offers only /stream1 /stream6.
 * No disk recordings, no authentication, no camera/network discovery.
 * Mode: server (forever, CI controller owns process), client (12s bounded).
 */
#include <gst/gst.h>
#include <gst/rtsp-server/rtsp-server.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  GMainLoop *loop;
  guint64 packets[4];
  gboolean error;
} C545DTest;

static GstPadProbeReturn
count_buffers(GstPad *pad, GstPadProbeInfo *info, gpointer user_data)
{
  guint64 *count = (guint64*) user_data;
  (void) pad;
  if ((GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER) != 0)
    (*count)++;
  return GST_PAD_PROBE_OK;
}

static gboolean
stop_timeout(gpointer user_data)
{
  g_main_loop_quit((GMainLoop*) user_data);
  return G_SOURCE_REMOVE;
}

static gboolean
handle_bus(GstBus *bus, GstMessage *message, gpointer user_data)
{
  C545DTest *state = (C545DTest*) user_data;
  (void) bus;
  if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
    /* Never forward error content, tokens, URLs, usernames or paths to CI. */
    state->error = TRUE;
    g_main_loop_quit(state->loop);
  } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_EOS) {
    g_main_loop_quit(state->loop);
  }
  return TRUE;
}

static int
run_server(void)
{
  GstRTSPServer *server = gst_rtsp_server_new();
  GstRTSPMountPoints *mounts;
  GstRTSPMediaFactory *wide;
  GstRTSPMediaFactory *tele;
  GMainLoop *loop;
  guint id;
  /* Never allow a non-loopback address: test is not a network server. */
  gst_rtsp_server_set_address(server, "127.0.0.1");
  gst_rtsp_server_set_service(server, "554");
  mounts = gst_rtsp_server_get_mount_points(server);
  wide = gst_rtsp_media_factory_new();
  tele = gst_rtsp_media_factory_new();
  gst_rtsp_media_factory_set_launch(wide,
    "( videotestsrc is-live=true pattern=smpte "
    "! video/x-raw,format=I420,width=1280,height=720,framerate=15/1 "
    "! x264enc speed-preset=ultrafast tune=zerolatency key-int-max=30 "
    "! h264parse ! rtph264pay config-interval=1 pt=96 name=pay0 "
    "audiotestsrc is-live=true wave=sine "
    "! audio/x-raw,rate=8000,channels=1 "
    "! audioconvert ! alawenc ! rtppcmapay pt=8 name=pay1 )");
  gst_rtsp_media_factory_set_launch(tele,
    "( videotestsrc is-live=true pattern=ball "
    "! video/x-raw,format=I420,width=1280,height=720,framerate=15/1 "
    "! x264enc speed-preset=ultrafast tune=zerolatency key-int-max=30 "
    "! h264parse ! rtph264pay config-interval=1 pt=96 name=pay0 "
    "audiotestsrc is-live=true wave=sine "
    "! audio/x-raw,rate=8000,channels=1 "
    "! audioconvert ! alawenc ! rtppcmapay pt=8 name=pay1 )");
  gst_rtsp_media_factory_set_shared(wide, TRUE);
  gst_rtsp_media_factory_set_shared(tele, TRUE);
  gst_rtsp_mount_points_add_factory(mounts, "/stream1", wide);
  gst_rtsp_mount_points_add_factory(mounts, "/stream6", tele);
  g_object_unref(mounts);
  id = gst_rtsp_server_attach(server, NULL);
  if (id == 0) {
    g_print("C545D_SYNTHETIC_RTSP_SERVER,ready=0,loopback_only=1,reason=BIND_FAILED\n");
    fflush(stdout);
    g_object_unref(server);
    return 3;
  }
  g_print("C545D_SYNTHETIC_RTSP_SERVER,ready=1,loopback_only=1,port=554,streams=2,real_camera=0\n");
  fflush(stdout);
  loop = g_main_loop_new(NULL, FALSE);
  g_main_loop_run(loop);
  g_main_loop_unref(loop);
  g_source_remove(id);
  g_object_unref(server);
  return 0;
}

static int
run_client(void)
{
  const gchar *desc =
    "rtspsrc name=wide location=rtsp://127.0.0.1:554/stream1 "
      "protocols=tcp latency=250 ntp-sync=true tcp-timestamp=true "
    "wide. ! application/x-rtp,media=video,encoding-name=H264 "
      "! queue ! rtph264depay ! h264parse ! avdec_h264 "
      "! fakesink name=v0 sync=false "
    "wide. ! application/x-rtp,media=audio "
      "! queue ! rtppcmadepay ! alawdec ! fakesink name=a0 sync=false "
    "rtspsrc name=tele location=rtsp://127.0.0.1:554/stream6 "
      "protocols=tcp latency=250 ntp-sync=true tcp-timestamp=true "
    "tele. ! application/x-rtp,media=video,encoding-name=H264 "
      "! queue ! rtph264depay ! h264parse ! avdec_h264 "
      "! fakesink name=v1 sync=false "
    "tele. ! application/x-rtp,media=audio "
      "! queue ! rtppcmadepay ! alawdec ! fakesink name=a1 sync=false";
  GstElement *pipeline;
  GstBus *bus;
  C545DTest state = { 0 };
  GError *error = NULL;
  guint bus_watch;
  guint timer;
  const gchar *names[] = {"v0","a0","v1","a1"};
  guint i;
  gboolean pass;

  pipeline = gst_parse_launch(desc, &error);
  if (!pipeline || error) {
    if (error) g_error_free(error);
    if (pipeline) gst_object_unref(pipeline);
    g_print("C545D_SYNTHETIC_RTSP_CLIENT,pass=0,reason=PARSE\n");
    return 3;
  }
  state.loop = g_main_loop_new(NULL, FALSE);
  for (i = 0; i < 4; i++) {
    GstElement *sink = gst_bin_get_by_name(GST_BIN(pipeline), names[i]);
    GstPad *pad;
    if (!sink) {
      gst_element_set_state(pipeline, GST_STATE_NULL);
      gst_object_unref(pipeline);
      g_main_loop_unref(state.loop);
      return 3;
    }
    pad = gst_element_get_static_pad(sink, "sink");
    gst_pad_add_probe(pad, GST_PAD_PROBE_TYPE_BUFFER,
                      count_buffers, &state.packets[i], NULL);
    gst_object_unref(pad);
    gst_object_unref(sink);
  }
  bus = gst_element_get_bus(pipeline);
  bus_watch = gst_bus_add_watch(bus, handle_bus, &state);
  gst_object_unref(bus);
  timer = g_timeout_add_seconds(12, stop_timeout, state.loop);
  if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE)
    state.error = TRUE;
  else
    g_main_loop_run(state.loop);
  gst_element_set_state(pipeline, GST_STATE_NULL);
  g_source_remove(bus_watch);
  if (g_main_context_find_source_by_id(NULL, timer) != NULL)
    g_source_remove(timer);
  gst_object_unref(pipeline);
  g_main_loop_unref(state.loop);
  pass = !state.error && state.packets[0] >= 10 && state.packets[1] >= 5 &&
         state.packets[2] >= 10 && state.packets[3] >= 5;
  g_print("C545D_SYNTHETIC_RTSP_CLIENT,pass=%d,loopback_only=1,streams=2,video_branches=2,audio_branches=2,v0_present=%d,a0_present=%d,v1_present=%d,a1_present=%d,real_camera=0\n",
    pass ? 1 : 0, state.packets[0] >= 10, state.packets[1] >= 5,
    state.packets[2] >= 10, state.packets[3] >= 5);
  return pass ? 0 : 3;
}

int
main(int argc, char **argv)
{
  /* A test-only binary must refuse all non-CI hosts before Gst startup. */
  const char *ci = getenv("GITHUB_ACTIONS");
  const char *os = getenv("RUNNER_OS");
  if (!ci || !os || strcmp(ci, "true") != 0 ||
      strcmp(os, "Windows") != 0) return 3;
  gst_init(&argc, &argv);
  if (argc != 2) return 3;
  if (strcmp(argv[1], "server") == 0) return run_server();
  if (strcmp(argv[1], "client") == 0) return run_client();
  return 3;
}
