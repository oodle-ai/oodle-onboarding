# aws-for-fluent-bit bundles the syslog input, `ecs` filter, and the cloudwatch_logs + http
# outputs we need — all built-in C plugins, no `-e` Go plugin loads required.
# The base image's default CMD runs `-c /fluent-bit/etc/fluent-bit.conf`, which we overwrite.
FROM public.ecr.aws/aws-observability/aws-for-fluent-bit:stable

COPY fluent-bit.conf     /fluent-bit/etc/fluent-bit.conf
COPY parsers-convox.conf /fluent-bit/etc/parsers-convox.conf
COPY derive_app.lua      /fluent-bit/etc/derive_app.lua
