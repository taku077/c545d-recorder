/*
 * CI ONLY: finite, private, dual RTSP media source for exercising an
 * unmodified production-equivalent Record.ps1 source mirror.
 * Only 127.0.0.1:554 /stream1 /stream6; synthetic H264 + PCMA.
 * Never uploads media, authenticates cameras, changes host settings,
 * or runs outside a Windows GitHub Actions job.
 *
 * Unlike the separately proven endless RTSP fixture, BOTH media streams
 * terminate naturally after about 22 seconds. The only purpose is to
 * observe whether an unmodified recorder can finalize with end-of-stream
 * from a synthetic RTSP source; do not conflate this with GUI Ctrl+C EOS.
 */
#include <gst/gst.h>
#include <gst/rtsp-server/rtsp-server.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int run_server(void)
{
  GstRTSPServer *server;
  GstRTSPMountPoints *mounts;
  GstRTSPMediaFactory *wide, *tele;
  GMainLoop *loop;
  guint id;
  const char *wide_launch =
    "( videotestsrc is-live=true num-buffers=330 pattern=smpte "
    "! video/x-raw,format=I420,width=1280,height=720,framerate=15/1 "
    "! x264enc speed-preset=ultrafast tune=zerolatency key-int-max=30 "
    "! h264parse ! rtph264pay config-interval=1 pt=96 name=pay0 "
    "audiotestsrc is-live=true num-buffers=550 samplesperbuffer=320 wave=sine "
    "! audio/x-raw,rate=8000,channels=1 "
    "! audioconvert ! alawenc ! rtppcmapay pt=8 name=pay1 )";
  const char *tele_launch =
    "( videotestsrc is-live=true num-buffers=330 pattern=ball "
    "! video/x-raw,format=I420,width=1280,height=720,framerate=15/1 "
    "! x264enc speed-preset=ultrafast tune=zerolatency key-int-max=30 "
    "! h264parse ! rtph264pay config-interval=1 pt=96 name=pay0 "
    "audiotestsrc is-live=true num-buffers=550 samplesperbuffer=320 wave=sine "
    "! audio/x-raw,rate=8000,channels=1 "
    "! audioconvert ! alawenc ! rtppcmapay pt=8 name=pay1 )";
  server = gst_rtsp_server_new();
  gst_rtsp_server_set_address(server, "127.0.0.1");
  gst_rtsp_server_set_service(server, "554");
  mounts = gst_rtsp_server_get_mount_points(server);
  wide = gst_rtsp_media_factory_new();
  tele = gst_rtsp_media_factory_new();
  gst_rtsp_media_factory_set_launch(wide, wide_launch);
  gst_rtsp_media_factory_set_launch(tele, tele_launch);
  gst_rtsp_mount_points_add_factory(mounts, "/stream1", wide);
  gst_rtsp_mount_points_add_factory(mounts, "/stream6", tele);
  g_object_unref(mounts);
  id = gst_rtsp_server_attach(server, NULL);
  if (id == 0) {
    g_print("C545D_FINITE_RTSP_SERVER,ready=0,reason=BIND_FAILED,real_camera=0\n");
    fflush(stdout);
    g_object_unref(server);
    return 3;
  }
  g_print("C545D_FINITE_RTSP_SERVER,ready=1,loopback_only=1,port=554,streams=2,video_frames_per_stream=330,pcma_buffers_per_stream=550,real_camera=0\n");
  fflush(stdout);
  loop = g_main_loop_new(NULL,FALSE);
  g_main_loop_run(loop);
  g_main_loop_unref(loop);
  g_source_remove(id);
  g_object_unref(server);
  return 0;
}

int main(int argc, char **argv)
{
  const char *ci=getenv("GITHUB_ACTIONS");
  const char *os=getenv("RUNNER_OS");
  if (!ci || !os || strcmp(ci,"true") != 0 ||
      strcmp(os,"Windows") != 0) return 3;
  if (argc != 2 || strcmp(argv[1],"server") != 0) return 3;
  gst_init(&argc,&argv);
  return run_server();
}
