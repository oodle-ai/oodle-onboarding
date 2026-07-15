class WelcomeController < ApplicationController
  def index
    # Exercise the database so each request emits SQL spans (INSERT + SELECTs) that
    # Datadog APM captures as `postgres`/`active_record` child spans of the request.
    Visit.create!(path: request.path, user_agent: request.user_agent)
    @visit_count = Visit.count
    @recent_visits = Visit.order(created_at: :desc).limit(5).to_a

    @hostname = ENV.fetch("HOSTNAME", "unknown")
    @rails_env = Rails.env
    @ruby_version = RUBY_VERSION
    @rails_version = Rails.version
  end
end
