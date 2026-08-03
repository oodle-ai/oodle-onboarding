#!/usr/bin/env python3
"""Post-process raw benchmark results into corrected CSV + a combined HTML report.

Sections:
  1. Plain awss3receiver replay (gauge, nop sink) - object-bound, O(1) memory.
  2. Histogram fan-in (awss3receiver -> deltatocumulative -> interval) - CPU vs
     datapoints, memory vs streams.
  3. Stream-cardinality sweep - where memory starts to climb.

Correction (section 1): otelcol_receiver_accepted_metric_points increments once
per S3 object, not per datapoint (verified). Datapoint totals are lossless.
"""
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def load(name):
    p = os.path.join(RES, name)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


# ---- section 1: correct the plain-receiver results ----
raw = load("results.csv")
base_rows = []
for r in raw:
    mc, rate = int(r["metric_count"]), int(r["rate_per_metric"])
    dur, wall = int(r["duration_min"]), float(r["read_wall_s"])
    objs, dps, cpu = int(r["expected_files"]), int(r["expected_samples"]), float(r["cpu_seconds"])
    base_rows.append({
        "metric_count": mc, "rate_per_metric": rate, "duration_min": dur,
        "objects": objs, "datapoints": dps, "read_wall_s": round(wall, 3),
        "objects_per_sec": round(objs / wall, 1),
        "datapoints_per_sec": round(dps / wall),
        "cpu_seconds": round(cpu, 3), "avg_cores": round(cpu / wall, 3),
        "peak_rss_mb": float(r["peak_rss_mb"]), "avg_rss_mb": float(r["avg_rss_mb"]),
    })
if base_rows:
    with open(os.path.join(RES, "results_corrected.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(base_rows[0].keys())); w.writeheader()
        for r in base_rows:
            w.writerow(r)

hist_rows = load("results_histagg.csv")
card_rows = load("results_cardinality.csv")


def cost_model(rows):
    X = [(int(r["objects"]), int(r["datapoints"])) for r in rows]
    y = [float(r["cpu_seconds"]) for r in rows]
    sxx = sum(o * o for o, d in X); sdd = sum(d * d for o, d in X)
    sod = sum(o * d for o, d in X)
    soy = sum(o * yy for (o, d), yy in zip(X, y))
    sdy = sum(d * yy for (o, d), yy in zip(X, y))
    det = sxx * sdd - sod * sod
    if not det:
        return 0, 0
    a = (soy * sdd - sdy * sod) / det
    b = (sxx * sdy - sod * soy) / det
    return a, b


ga, gb = cost_model(base_rows) if base_rows else (0, 0)
ha, hb = cost_model(hist_rows) if hist_rows else (0, 0)

HTML = """<!doctype html><html lang=en><head><meta charset=utf-8>
<title>awss3receiver load benchmark</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 .wrap{max-width:1100px;margin:0 auto;padding:24px}
 h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:34px 0 6px;color:#9ad;border-top:1px solid #262b36;padding-top:20px}
 h3{font-size:14px;margin:20px 0 6px;color:#7aa} .sub{color:#8a93a2;margin-bottom:14px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
 .card{background:#171a21;border:1px solid #262b36;border-radius:10px;padding:14px}
 .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0 4px}
 .kpi{background:#171a21;border:1px solid #262b36;border-radius:10px;padding:12px}
 .kpi b{display:block;font-size:19px;color:#7CFC98} .kpi span{color:#8a93a2;font-size:12px}
 table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}
 th,td{border:1px solid #262b36;padding:5px 7px;text-align:right} th{background:#1b1f28;color:#9ad}
 td:first-child,th:first-child{text-align:left}
 .note{background:#1a1e27;border-left:3px solid #d1a54a;padding:10px 14px;border-radius:6px;margin:14px 0;color:#d7d0bf}
 code{color:#7CFC98}
 @media(max-width:800px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}}
</style></head><body><div class=wrap>
<h1>awss3receiver &mdash; load, CPU & memory benchmark (MinIO backend)</h1>
<div class=sub>opentelemetry-collector-contrib v0.155.0 &middot; MinIO S3 backend &middot; metrics replay &middot;
file model 600 objects/min (capped at datapoints/min) &middot; durations measured as sub-windows of one 20-min dataset</div>

<h2>1. Plain replay &mdash; awss3receiver &rarr; nop (gauges)</h2>
<div class=note><b>Object-bound, O(1) memory.</b> Read time/CPU track the number of S3 objects; datapoint volume
inside objects is nearly free; memory is flat (streaming). Lossless (<code>refused=0</code>).
Model: <b>~__GA__ &micro;s/object + __GB__ &micro;s/datapoint</b>. Local-MinIO ceiling; real S3 per-object latency dominates.</div>
<div class=kpis id=k1></div>
<div class=grid>
 <div class=card><canvas id=g_cpu></canvas></div>
 <div class=card><canvas id=g_rss></canvas></div>
</div>

<h2>2. Histogram fan-in &mdash; awss3receiver &rarr; deltatocumulative &rarr; interval</h2>
<div class=sub>crawler_msg_file_count, delta histograms from many "lambdas" merged (summed) into one aggregate per stream.
Here "series" = tracked streams. All runs lossless: processed == datapoints, out-of-order == 0.</div>
<div class=note><b>Aggregation shifts cost toward datapoints.</b> Merge model: <b>~__HA__ &micro;s/object + __HB__ &micro;s/datapoint</b>
(datapoints ~__HRATIO__x costlier than the plain gauge read: 11-bucket add + delta accumulation). Memory stays flat because
state is O(streams), and streams here are only 1 or 10. <b>deltatocumulative requires in-order delta samples per stream</b>;
out-of-order objects are dropped (watch <code>otelcol_deltatocumulative_datapoints{error="delta.ErrOutOfOrder"}</code>).</div>
<div class=kpis id=k2></div>
<div class=grid>
 <div class=card><canvas id=h_cpu></canvas></div>
 <div class=card><canvas id=h_rss></canvas></div>
</div>

<h2>3. Stream-cardinality sweep &mdash; where memory climbs</h2>
<div class=sub>~2 delta datapoints per stream, 600 objects fixed, varying the number of unique streams.
Isolates deltatocumulative + interval per-stream memory.</div>
<div class=kpis id=k3></div>
<div class=grid>
 <div class=card><canvas id=c_rss></canvas></div>
 <div class=card><canvas id=c_cpu></canvas></div>
</div>

<h2>Tables</h2>
<h3>Plain replay</h3><div class=card style="overflow:auto"><table id=t1></table></div>
<h3>Histogram fan-in</h3><div class=card style="overflow:auto"><table id=t2></table></div>
<h3>Cardinality sweep</h3><div class=card style="overflow:auto"><table id=t3></table></div>
</div>
<script>
const BASE=__BASE__, HIST=__HIST__, CARD=__CARD__;
const dark={plugins:{legend:{labels:{color:'#cdd'}}},
 scales:{x:{ticks:{color:'#9aa'},grid:{color:'#222833'},title:{display:true,color:'#9aa'}},
         y:{ticks:{color:'#9aa'},grid:{color:'#222833'},title:{display:true,color:'#9aa'},beginAtZero:true}}};
const colors={1:'#7CFC98',10:'#5aa9ff'};
function tbl(id,rows){if(!rows.length)return;const c=Object.keys(rows[0]);
 document.getElementById(id).innerHTML='<tr>'+c.map(x=>'<th>'+x+'</th>').join('')+'</tr>'+
 rows.map(r=>'<tr>'+c.map(x=>'<td>'+r[x]+'</td>').join('')+'</tr>').join('');}
function kpi(id,items){document.getElementById(id).innerHTML=
 items.map(([b,s])=>`<div class=kpi><b>${b}</b><span>${s}</span></div>`).join('');}
function opt(xl,yl,xtype){const o=JSON.parse(JSON.stringify(dark));o.scales.x.title.text=xl;
 o.scales.y.title.text=yl;if(xtype)o.scales.x.type=xtype;return o;}
function byKey(rows,key,xk,yk){const vals=[...new Set(rows.map(r=>+r[key]))].sort((a,b)=>a-b);
 return vals.map(v=>({label:key+'='+v,borderColor:colors[v]||'#e0a15a',backgroundColor:colors[v]||'#e0a15a',
  showLine:true,tension:.2,data:rows.filter(r=>+r[key]===v).map(r=>({x:+r[xk],y:+r[yk]})).sort((a,b)=>a.x-b.x)}));}

// section 1
const mx=(rows,k)=>Math.max(...rows.map(r=>+r[k]));
kpi('k1',[['~'+Math.round(mx(BASE,'peak_rss_mb'))+' MB','peak RSS (worst)'],
 [Math.round(mx(BASE,'objects_per_sec')).toLocaleString(),'max objects/sec'],
 [Math.round(mx(BASE,'datapoints_per_sec')).toLocaleString(),'max datapoints/sec'],
 [mx(BASE,'cpu_seconds').toFixed(2)+' s','worst-case CPU']]);
new Chart(g_cpu,{type:'scatter',data:{datasets:byKey(BASE,'metric_count','objects','cpu_seconds')},
 options:opt('S3 objects read','CPU seconds')});
new Chart(g_rss,{type:'scatter',data:{datasets:byKey(BASE,'metric_count','objects','peak_rss_mb')},
 options:opt('S3 objects read','Peak RSS (MB)')});
tbl('t1',BASE);

// section 2
if(HIST.length){
 kpi('k2',[['~'+Math.round(mx(HIST,'peak_rss_mb'))+' MB','peak RSS (worst)'],
  [mx(HIST,'cpu_seconds').toFixed(2)+' s','worst-case CPU'],
  [Math.max(...HIST.map(r=>+r.datapoints)).toLocaleString(),'max datapoints merged'],
  ['0','out-of-order dropped']]);
 new Chart(h_cpu,{type:'scatter',data:{datasets:byKey(HIST,'series','datapoints','cpu_seconds')},
  options:opt('datapoints merged','CPU seconds')});
 new Chart(h_rss,{type:'scatter',data:{datasets:byKey(HIST,'series','datapoints','peak_rss_mb')},
  options:opt('datapoints merged','Peak RSS (MB)')});
 tbl('t2',HIST);
}
// section 3
if(CARD.length){
 kpi('k3',[[Math.max(...CARD.map(r=>+r.streams)).toLocaleString(),'max streams tracked'],
  ['~'+Math.round(mx(CARD,'peak_rss_mb'))+' MB','peak RSS at max streams'],
  [((mx(CARD,'peak_rss_mb')-Math.min(...CARD.map(r=>+r.peak_rss_mb)))).toFixed(0)+' MB','RSS growth over sweep'],
  [mx(CARD,'cpu_seconds').toFixed(2)+' s','CPU at max streams']]);
 new Chart(c_rss,{type:'scatter',data:{datasets:[{label:'peak RSS',borderColor:'#e0a15a',
  backgroundColor:'#e0a15a',showLine:true,tension:.2,
  data:CARD.map(r=>({x:+r.streams,y:+r.peak_rss_mb})).sort((a,b)=>a.x-b.x)}]},
  options:opt('streams tracked (log)','Peak RSS (MB)','logarithmic')});
 new Chart(c_cpu,{type:'scatter',data:{datasets:[{label:'CPU',borderColor:'#5aa9ff',
  backgroundColor:'#5aa9ff',showLine:true,tension:.2,
  data:CARD.map(r=>({x:+r.streams,y:+r.cpu_seconds})).sort((a,b)=>a.x-b.x)}]},
  options:opt('streams tracked (log)','CPU seconds','logarithmic')});
 tbl('t3',CARD);
}
</script></body></html>"""

HTML = (HTML.replace("__BASE__", json.dumps(base_rows))
            .replace("__HIST__", json.dumps(hist_rows))
            .replace("__CARD__", json.dumps(card_rows))
            .replace("__GA__", str(round(ga * 1e6)))
            .replace("__GB__", str(round(gb * 1e6, 2)))
            .replace("__HA__", str(round(ha * 1e6)))
            .replace("__HB__", str(round(hb * 1e6, 2)))
            .replace("__HRATIO__", str(round(hb / gb)) if gb else "?"))
open(os.path.join(RES, "report.html"), "w").write(HTML)
print(f"wrote report.html (base={len(base_rows)} hist={len(hist_rows)} card={len(card_rows)} rows)")
print(f"gauge model ~{ga*1e6:.0f}us/obj+{gb*1e6:.2f}us/dp | hist model ~{ha*1e6:.0f}us/obj+{hb*1e6:.2f}us/dp")
