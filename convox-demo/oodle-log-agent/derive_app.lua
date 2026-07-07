-- Reduce the ECS task-definition family (added by the `ecs` filter as `task_definition`) to a
-- clean Convox app name, and map it onto Oodle's canonical `service` field. Also promote the
-- container short-id into Oodle's canonical `container_id`.
--
-- Family shape (verified on gm-test):
--   <rack>-<app>-Service<Kind>-<cfnRandom>-service-<svc>
--   e.g. gm-test-rails-demo-ServiceWeb-CRFBDIVNUAUO-service-web  ->  service = rails-demo
--
-- RACK_PREFIX (env) is the short rack name that prefixes every family (e.g. "gm-test").
-- Falls back gracefully: if the family doesn't match, `service` = the full family, so records
-- are still routed (just under a longer name) rather than dropped.
local RACK_PREFIX = os.getenv("RACK_PREFIX") or ""

local function escape(s)
    return (s:gsub("([%-%.%+%[%]%(%)%$%^%%%?%*])", "%%%1"))
end

function derive_app(tag, ts, record)
    local fam = record["task_definition"]
    if fam == nil then
        return 0, ts, record   -- 0 = leave record unchanged (no metadata to work with)
    end
    local app = fam
    local base = string.match(fam, "^(.-)%-Service")   -- strip "-Service<Kind>-..." suffix
    if base ~= nil then app = base end
    if RACK_PREFIX ~= "" then
        local stripped = string.match(app, "^" .. escape(RACK_PREFIX) .. "%-(.+)$")
        if stripped ~= nil then app = stripped end     -- strip "<rack>-" prefix
    end
    record["service"] = app                            -- Oodle canonical app field
    if record["appname"] ~= nil then
        record["container_id"] = record["appname"]     -- Oodle canonical container id (short)
    end
    return 2, ts, record       -- 2 = record modified
end
