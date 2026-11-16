# Security and publishing policy

Do not upload private camera addresses, usernames/passwords, RTSP URLs with credentials, DPAPI files, configuration, recordings, ETL/WPR traces, or unredacted logs, **including to the private repository**.

- Review all source before making a public push.
- Remove secrets before publishing; `.gitignore` does **not** remove them from Git history.
- No real camera connection is required or used in CI.
- Keep actual camera parameters local in `%LOCALAPPDATA%\C545D_GStreamer`.
- Never publish raw diagnostic traces or videos.
