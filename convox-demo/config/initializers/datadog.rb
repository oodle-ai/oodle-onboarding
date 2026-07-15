# Datadog APM tracing for the Rails demo.
#
# The `datadog` gem reads DD_AGENT_HOST / DD_TRACE_AGENT_PORT / DD_SERVICE / DD_ENV /
# DD_VERSION from the environment (set via `convox env` — see datadog-agent/README.md).
# On this Convox ECS/EC2 rack the app runs in a bridge-network container, so
# DD_AGENT_HOST points at the docker bridge gateway 172.17.0.1, where the host-local
# Datadog agent (a Convox `agent:` daemon) publishes the APM port 8126.
#
# Only instrument when an agent host is configured, so local/other environments that
# don't set DD_AGENT_HOST don't try to ship traces to nowhere.
if ENV["DD_AGENT_HOST"].present?
  Datadog.configure do |c|
    c.service = ENV.fetch("DD_SERVICE", "rails-demo")
    c.env     = ENV["DD_ENV"]
    c.version = ENV["DD_VERSION"]

    # Web request spans (operation `rack.request`) — matches DD_APM_ANALYZED_SPANS.
    c.tracing.instrument :rails

    # Database spans. :active_record captures the SQL (as the span resource) for each
    # query; :pg adds the low-level libpq driver spans. Together they show DB queries
    # with SQL as child spans of each web request in Datadog APM.
    c.tracing.instrument :active_record
    c.tracing.instrument :pg
  end
end
