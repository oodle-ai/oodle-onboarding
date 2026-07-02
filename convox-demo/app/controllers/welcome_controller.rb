class WelcomeController < ApplicationController
  def index
    @hostname = ENV.fetch("HOSTNAME", "unknown")
    @rails_env = Rails.env
    @ruby_version = RUBY_VERSION
    @rails_version = Rails.version
  end
end
