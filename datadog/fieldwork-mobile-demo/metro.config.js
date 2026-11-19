const { getDefaultConfig } = require("expo/metro-config");
const {
  withSessionReplayAssetBundler,
} = require("@datadog/mobile-react-native-session-replay/metro");
module.exports = withSessionReplayAssetBundler(getDefaultConfig(__dirname));
