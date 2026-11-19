const { withAndroidManifest } = require("expo/config-plugins");
module.exports = (config, { enabled = false } = {}) =>
  withAndroidManifest(config, (result) => {
    result.modResults.manifest.application[0].$[
      "android:usesCleartextTraffic"
    ] = enabled ? "true" : "false";
    return result;
  });
