"""Write dashboard.json: the DataPilot app signals next to the E2B signals.

Import it with: oodle dashboards create -f datapilot/dashboard.json
"""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "${datasource}"}


def panel(pid, title, desc, x, y, w, h, targets, unit="short", stack=False):
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 15 if stack else 0,
                    "stacking": {"mode": "normal" if stack else "none"},
                    "spanNulls": False,
                },
            },
            "overrides": [],
        },
        "options": {"legend": {"displayMode": "table", "placement": "right"}, "tooltip": {"mode": "multi"}},
        "targets": [
            {"datasource": DS, "refId": chr(65 + i), "expr": e, "legendFormat": l, "range": True, "editorMode": "code"}
            for i, (e, l) in enumerate(targets)
        ],
    }


def row(pid, title, y):
    return {"id": pid, "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


panels = [
    row(1, "What the agent sees (service datapilot-agent)", 0),
    panel(
        2,
        "Questions per minute, by outcome and error",
        "Each failed question shows the last error that the E2B SDK gave the agent.",
        0, 1, 12, 8,
        [("sum by (outcome, error_type) (increase(datapilot_analysis_requests[1m]))", "{{outcome}} {{error_type}}")],
        stack=True,
    ),
    panel(
        3,
        "Failed questions per minute, by tenant, question and planner",
        "The failures come from one tenant, one question, and planner v2 only.",
        12, 1, 12, 8,
        [(
            "sum by (tenant, question, planner_version) (increase(datapilot_analysis_requests{outcome=\"error\"}[1m]))",
            "{{tenant}} {{question}} {{planner_version}}",
        )],
    ),
    row(4, "What the sandbox shows (E2B OTel export and datapilot-kernel)", 9),
    panel(
        5,
        "Sandboxes: the agent's count and E2B's count",
        "The agent stops to count a session when the session fails, but it does not kill the sandbox. "
        "E2B counts the sandbox until its timeout ends.",
        0, 10, 12, 8,
        [
            ("sum(datapilot_sessions_active)", "agent: sessions that hold a sandbox"),
            ("sum(e2b_team_sandbox_running)", "E2B: sandboxes running"),
        ],
    ),
    panel(
        6,
        "Sandbox memory used (E2B, sampled every 5s)",
        "Memory of the whole sandbox VM, measured from outside the VM. A drop to the idle level in the middle "
        "of a session means that the kernel was killed and restarted.",
        12, 10, 12, 8,
        [
            ("max by (sandbox_id) (last_over_time(e2b_sandbox_ram_used[30s]))", "{{sandbox_id}}"),
            ("max(last_over_time(e2b_sandbox_ram_total[30s]))", "memory limit"),
        ],
        unit="bytes",
    ),
    panel(
        7,
        "Kernel memory as the kernel reports it (datapilot-kernel, every 10s)",
        "The kernel reports its own memory on a timer. A kernel that is killed between two reports never "
        "reports the peak.",
        0, 18, 12, 8,
        [("max by (sandbox_id, tenant) (last_over_time(datapilot_kernel_rss[30s]))", "{{tenant}} {{sandbox_id}}")],
        unit="bytes",
    ),
    panel(
        8,
        "Sessions per minute, by outcome",
        "failed means that the session could not start a sandbox, for example because the team reached "
        "its limit of concurrent E2B sandboxes.",
        12, 18, 12, 8,
        [("sum by (outcome, error_type) (increase(datapilot_sessions[1m]))", "{{outcome}} {{error_type}}")],
        stack=True,
    ),
]

dashboard = {
    "dashboard": {
        "uid": "datapilot-e2b-oom",
        "title": "DataPilot on E2B",
        "description": "DataPilot agent signals next to the E2B sandbox signals, for the OOM demo.",
        "tags": ["e2b", "datapilot", "demo"],
        "editable": True,
        "schemaVersion": 39,
        "refresh": "30s",
        "time": {"from": "now-30m", "to": "now"},
        "templating": {
            "list": [
                {
                    "current": {"text": "Prometheus", "value": "prometheus"},
                    "hide": 2,
                    "label": "Data source",
                    "name": "datasource",
                    "query": "prometheus",
                    "type": "datasource",
                }
            ]
        },
        "panels": panels,
    },
    "overwrite": True,
}

Path(__file__).with_name("dashboard.json").write_text(json.dumps(dashboard, indent=2) + "\n")
print("wrote dashboard.json")
