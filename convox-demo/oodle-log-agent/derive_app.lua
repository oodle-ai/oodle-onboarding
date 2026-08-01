-- Reduce the ECS task-definition family (added by the `ecs` filter as `task_definition`) to a
-- clean Convox app name, and map it onto Oodle's canonical `service` field. Also promote the
-- container short-id into Oodle's canonical `container_id`.
--
-- Family shape (Convox generation-2, ECS/CloudFormation):
--   <rack>-<app>-<CfnLogicalId>-<cfnRandom>-<kind>-<...>
--   where <CfnLogicalId> is the first PascalCase segment CloudFormation injects per process, e.g.
--     <rack>-<app>-Service<Proc>-<cfnRandom>-service-<proc>   (a service)  ->  service = <app>
--     <rack>-<app>-Timer<Proc>-<cfnRandom>-timer-<proc>       (a timer)    ->  service = <app>
--   Convox app names are always lowercase DNS labels, so the FIRST hyphen segment that starts with
--   an uppercase letter reliably marks the app/process boundary for ANY process kind (Service,
--   Timer, ...). Keying off that (instead of `-Service` only) folds every process of an app -- the
--   web service AND all its timers -- onto ONE app name, hence ONE CloudWatch LogGroup. Two distinct
--   Convox apps still resolve to distinct names/groups.
--
-- RACK_PREFIX (env) is the short rack name that prefixes every family.
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
    -- Cut at the first hyphen segment beginning with an uppercase letter -- the CloudFormation
    -- process logical id (Service<Proc>, Timer<Proc>, ...). This folds a Convox app's web service
    -- and all its timers onto one app name (one LogGroup).
    local base = string.match(fam, "^(.-)%-%u")
    if base ~= nil then app = base end
    if RACK_PREFIX ~= "" then
        local stripped = string.match(app, "^" .. escape(RACK_PREFIX) .. "%-(.+)$")
        if stripped ~= nil then app = stripped end     -- strip "<rack>-" prefix
    end
    record["service"] = app                            -- Oodle canonical app field
    -- CloudWatch group that mirrors Convox's native <rack>-<app>-LogGroup-<hash>, with a fixed
    -- "oodle" suffix in place of the CloudFormation hash. Composed here rather than in the output
    -- template because cloudwatch_logs templates can't place a hyphen after a $variable.
    if RACK_PREFIX ~= "" then
        record["cw_group"] = RACK_PREFIX .. "-" .. app .. "-LogGroup-oodle"
    else
        record["cw_group"] = app .. "-LogGroup-oodle"
    end
    if record["appname"] ~= nil then
        record["container_id"] = record["appname"]     -- Oodle canonical container id (short)
    end
    return 2, ts, record       -- 2 = record modified
end
