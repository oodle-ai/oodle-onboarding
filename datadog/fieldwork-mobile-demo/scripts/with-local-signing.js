const { withEntitlementsPlist } = require("expo/config-plugins");
module.exports = (config, { nativePush = false } = {}) =>
  withEntitlementsPlist(config, (result) => {
    // Local notifications must not require an APNs signing entitlement.
    if (!nativePush) delete result.modResults["aps-environment"];
    return result;
  });
