#!/bin/sh
set -eu

: "${OPENCODE_SERVER_PASSWORD:?OPENCODE_SERVER_PASSWORD must be set}"

config_dir="${HOME}/.config/opencode"
mkdir -p "$config_dir"
export OPENCODE_CONFIG_PATH="$config_dir/opencode.json"

# JSON.stringify keeps passwords and model names valid even when they contain
# shell-sensitive characters. The file lives in the ephemeral container layer.
node -e '
  const fs = require("fs");
  const config = { server: { password: process.env.OPENCODE_SERVER_PASSWORD } };
  if (process.env.OPENCODE_MODEL) {
    config.model = process.env.OPENCODE_MODEL;
    config.small_model = process.env.OPENCODE_MODEL;
  }
  if (process.env.KOSMO_AI_PROVIDER) {
    config.provider = {
      [process.env.KOSMO_AI_PROVIDER]: {
        options: {
          apiKey: "{file:/run/kosmo-secrets/provider-key}",
          timeout: false,
        },
      },
    };
  }
  fs.writeFileSync(process.env.OPENCODE_CONFIG_PATH, JSON.stringify(config));
'

exec opencode serve --hostname 0.0.0.0 --port 4096
