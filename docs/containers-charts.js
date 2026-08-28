// Container Manifest — rendering + interactivity.
// Vanilla D3 v7 (vendored at vendor/d3.v7.9.0.min.js). No build step: open
// docs/containers.html directly in a browser.

(function () {
  "use strict";

  const tooltip = document.getElementById("tooltip");
  function showTip(html, event) {
    tooltip.innerHTML = html;
    tooltip.style.left = event.clientX + "px";
    tooltip.style.top = event.clientY + "px";
    tooltip.classList.add("show");
  }
  function moveTip(event) {
    tooltip.style.left = event.clientX + "px";
    tooltip.style.top = event.clientY + "px";
  }
  function hideTip() {
    tooltip.classList.remove("show");
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Defined once in assets/docs.js (shared with every docs page); loaded before
  // this script, so it's already available on window here.
  const flashCard = window.docsFlash;

  // ============================================================
  // Generic node-link graph renderer, shared by both diagrams.
  // nodes: [{id,label,sub,x,y,w,external?}]  (x,y = top-left corner)
  // edges: [{source,target,kind,label}]
  // ============================================================
  function buildGraph(svgId, resetBtnSelector, nodesIn, edgesIn, opts) {
    const svg = d3.select("#" + svgId);
    const nodeH = opts.nodeH || 40;
    const animate = opts.animate !== false;
    const particleClass = opts.particleClass || "";
    const animatedKinds = opts.animatedKinds || ["data", "alert"];

    const nodes = nodesIn.map((d) => Object.assign({}, d));
    const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const edges = edgesIn
      .filter((e) => nodeById[e.source] && nodeById[e.target])
      .map((e) => Object.assign({}, e));

    const vb = svg.attr("viewBox").split(" ").map(Number);
    const zoomLayer = svg.append("g").attr("class", "zoom-layer");

    const zoom = d3
      .zoom()
      .scaleExtent([0.45, 4])
      .on("zoom", (event) => zoomLayer.attr("transform", event.transform));
    svg.call(zoom).on("dblclick.zoom", null);

    if (resetBtnSelector) {
      d3.select(resetBtnSelector).on("click", () => {
        svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
      });
    }

    const edgeLayer = zoomLayer.append("g").attr("class", "edge-layer");
    const particleLayer = zoomLayer.append("g").attr("class", "particle-layer");
    const nodeLayer = zoomLayer.append("g").attr("class", "node-layer");

    function anchor(node, side) {
      const y = node.y + nodeH / 2;
      return side === "left" ? { x: node.x, y } : { x: node.x + node.w, y };
    }

    function pathFor(e) {
      const s = nodeById[e.source];
      const t = nodeById[e.target];
      const goingRight = t.x >= s.x;
      const p0 = anchor(s, goingRight ? "right" : "left");
      const p1 = anchor(t, goingRight ? "left" : "right");
      const dx = Math.max(30, Math.abs(p1.x - p0.x) / 2);
      const c1x = p0.x + (goingRight ? dx : -dx);
      const c1y = p0.y;
      const c2x = p1.x - (goingRight ? dx : -dx);
      const c2y = p1.y;
      return `M${p0.x},${p0.y} C${c1x},${c1y} ${c2x},${c2y} ${p1.x},${p1.y}`;
    }

    const edgeSel = edgeLayer
      .selectAll("path.g-edge-path")
      .data(edges)
      .join("path")
      .attr("class", (d) => "g-edge-path k-" + d.kind)
      .attr("id", (d, i) => svgId + "-edge-" + i)
      .attr("d", pathFor)
      .on("mousemove", moveTip)
      .on("mouseover", function (event, d) {
        if (d.label) showTip(`<strong>${d.source} → ${d.target}</strong><br>${d.label}`, event);
      })
      .on("mouseout", hideTip);

    const labelSel = edgeLayer
      .selectAll("text.g-edge-label")
      .data(edges.filter((e) => e.label))
      .join("text")
      .attr("class", "g-edge-label")
      .attr("text-anchor", "middle")
      .text((d) => d.label);

    function positionLabels() {
      labelSel.attr("x", (d) => {
        const s = nodeById[d.source], t = nodeById[d.target];
        return (anchor(s, t.x >= s.x ? "right" : "left").x + anchor(t, t.x >= s.x ? "left" : "right").x) / 2;
      }).attr("y", (d) => {
        const s = nodeById[d.source], t = nodeById[d.target];
        return (anchor(s, "right").y + anchor(t, "left").y) / 2 - 5;
      });
    }
    positionLabels();

    // ---- nodes ----
    const nodeG = nodeLayer
      .selectAll("g.g-node")
      .data(nodes)
      .join("g")
      .attr("class", (d) => "g-node" + (d.external ? " external" : "") + (!d.external ? " is-container" : ""))
      .attr("transform", (d) => `translate(${d.x},${d.y})`);

    nodeG
      .append("rect")
      .attr("width", (d) => d.w)
      .attr("height", nodeH)
      .attr("rx", 5);

    nodeG
      .append("text")
      .attr("class", "g-title")
      .attr("x", (d) => d.w / 2)
      .attr("y", (d) => (d.sub ? nodeH / 2 - 4 : nodeH / 2 + 4))
      .attr("text-anchor", "middle")
      .text((d) => d.label);

    nodeG
      .filter((d) => d.sub)
      .append("text")
      .attr("class", "g-sub")
      .attr("x", (d) => d.w / 2)
      .attr("y", nodeH / 2 + 11)
      .attr("text-anchor", "middle")
      .text((d) => d.sub);

    function repositionAll() {
      nodeG.attr("transform", (d) => `translate(${d.x},${d.y})`);
      edgeSel.attr("d", pathFor);
      positionLabels();
    }

    nodeG.call(
      d3
        .drag()
        .on("start", function () { d3.select(this).raise(); })
        .on("drag", function (event, d) {
          d.x = event.x - d.w / 2;
          d.y = event.y - nodeH / 2;
          d3.select(this).attr("transform", `translate(${d.x},${d.y})`);
          edgeSel.attr("d", pathFor);
          positionLabels();
          updateParticles(true);
        })
    );

    // ---- click to isolate + jump to detail card ----
    let isolated = null;
    function applyIsolation() {
      if (!isolated) {
        nodeG.classed("dim", false);
        edgeSel.classed("dim", false);
        labelSel.classed("dim", false);
        return;
      }
      const connected = new Set([isolated]);
      edges.forEach((e) => {
        if (e.source === isolated) connected.add(e.target);
        if (e.target === isolated) connected.add(e.source);
      });
      nodeG.classed("dim", (d) => !connected.has(d.id));
      edgeSel.classed("dim", (d) => d.source !== isolated && d.target !== isolated);
      labelSel.classed("dim", (d) => d.source !== isolated && d.target !== isolated);
    }

    nodeG
      .on("mousemove", moveTip)
      .on("mouseover", function (event, d) {
        showTip(`<strong>${d.label}</strong>${d.sub ? "<br>" + d.sub : ""}${d.external ? "" : "<br><em>click to isolate + view detail</em>"}`, event);
      })
      .on("mouseout", hideTip)
      .on("click", function (event, d) {
        event.stopPropagation();
        isolated = isolated === d.id ? null : d.id;
        applyIsolation();
        if (isolated === d.id && !d.external) flashCard(d.id);
      });

    svg.on("click", () => {
      isolated = null;
      applyIsolation();
    });

    // ---- animated flow particles (single shared timer per graph) ----
    let particleData = [];
    if (animate) {
      particleData = edges
        .map((e, i) => ({ e, i, phase: (i * 0.61) % 1 }))
        .filter((p) => animatedKinds.indexOf(p.e.kind) !== -1);
    }
    const particleSel = particleLayer
      .selectAll("circle.g-particle")
      .data(particleData)
      .join("circle")
      .attr("class", (d) => "g-particle k-" + d.e.kind + " " + particleClass)
      .attr("r", 3.2);

    const DURATION = 3200;
    function updateParticles(instant) {
      particleSel.each(function (d) {
        const pathNode = document.getElementById(svgId + "-edge-" + d.i);
        if (!pathNode) return;
        const len = pathNode.getTotalLength();
        const t = instant ? d.phase : ((performance.now() / DURATION + d.phase) % 1);
        const pt = pathNode.getPointAtLength(t * len);
        d3.select(this).attr("cx", pt.x).attr("cy", pt.y);
      });
    }
    updateParticles(true);
    if (animate && particleData.length) {
      d3.timer(() => updateParticles(false));
    }

    return { repositionAll, updateParticles };
  }

  // ============================================================
  // Diagram 1 — data flow (hand-authored fixed layout from containers-data.js)
  // ============================================================
  buildGraph("flowDiagram", '[data-reset="flow"]', FLOW_NODES, FLOW_EDGES, {
    nodeH: 42,
    animate: true,
    animatedKinds: ["data", "alert"],
  });

  // ============================================================
  // Diagram 2 — boot/dependency graph, topologically auto-laid-out
  // ============================================================
  function computeBootLayout() {
    const level = {};
    SERVICES.forEach((s) => (level[s.id] = 0));
    let changed = true;
    let guard = 0;
    while (changed && guard++ < 50) {
      changed = false;
      DEP_EDGES.forEach((e) => {
        const want = (level[e.source] || 0) + 1;
        if (want > (level[e.target] || 0)) {
          level[e.target] = want;
          changed = true;
        }
      });
    }
    const byLevel = {};
    SERVICES.forEach((s) => {
      const lv = level[s.id];
      (byLevel[lv] = byLevel[lv] || []).push(s.id);
    });
    const COL_W = 250;
    const ROW_H = 62;
    const NODE_W = 172;
    const nodes = [];
    Object.keys(byLevel)
      .sort((a, b) => a - b)
      .forEach((lv) => {
        const ids = byLevel[lv];
        const totalH = ids.length * ROW_H;
        const startY = 30 + (620 - totalH) / 2;
        ids.forEach((id, i) => {
          const svc = SERVICES_BY_ID[id];
          nodes.push({
            id,
            label: id,
            sub: svc.lifecycle === "oneshot" ? "one-shot" : svc.category,
            x: 30 + lv * COL_W,
            y: Math.max(20, startY) + i * ROW_H,
            w: NODE_W,
          });
        });
      });
    return nodes;
  }

  // DEP_EDGES have no `kind` of their own — tag them before buildGraph copies
  // the edge objects, so the shared renderer's class/animation logic picks it up.
  DEP_EDGES.forEach((e) => (e.kind = e.kind || "dep"));

  buildGraph("bootDiagram", '[data-reset="boot"]', computeBootLayout(), DEP_EDGES, {
    nodeH: 38,
    animate: true,
    animatedKinds: ["dep"],
    particleClass: "k-dep",
  });

  // ============================================================
  // Hero stat chips
  // ============================================================
  (function renderStats() {
    const oneshot = SERVICES.filter((s) => s.lifecycle === "oneshot").length;
    const custom = SERVICES.filter((s) => s.build === "custom").length;
    const stats = [
      [SERVICES.length, "containers"],
      [oneshot, "one-shot init jobs"],
      [custom, "custom-built images"],
      [7, "named volumes"],
      [1, "Kafka topic"],
      [5, "Cassandra tables"],
    ];
    const wrap = d3.select("#statChips");
    stats.forEach(([n, label]) => {
      const chip = wrap.append("div").attr("class", "stat-chip");
      chip.append("strong").text(n);
      chip.append("span").text(label);
    });
  })();

  // ============================================================
  // Memory chart (horizontal bars, animated width-in on scroll)
  // ============================================================
  (function renderMemChart() {
    const data = [...SERVICES].sort((a, b) => b.mem - a.mem);
    const svg = d3.select("#memChart");
    const margin = { top: 6, right: 46, bottom: 6, left: 150 };
    const width = 620 - margin.left - margin.right;
    const rowH = 24;
    const height = data.length * rowH;
    svg.attr("viewBox", `0 0 620 ${height + margin.top + margin.bottom}`);

    const x = d3.scaleLinear().domain([0, d3.max(data, (d) => d.mem)]).nice().range([0, width]);
    const y = d3.scaleBand().domain(data.map((d) => d.id)).range([0, height]).padding(0.28);

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    g.selectAll("text.row-label")
      .data(data)
      .join("text")
      .attr("class", "bar-label")
      .attr("x", -8)
      .attr("y", (d) => y(d.id) + y.bandwidth() / 2 + 3.5)
      .attr("text-anchor", "end")
      .text((d) => d.id);

    const bars = g
      .selectAll("rect.bar")
      .data(data)
      .join("rect")
      .attr("class", "bar")
      .attr("x", 0)
      .attr("y", (d) => y(d.id))
      .attr("height", y.bandwidth())
      .attr("rx", 2)
      .style("fill", (d) => CATEGORY_COLOR[d.category])
      .attr("width", 0)
      .style("cursor", "pointer")
      .on("mousemove", moveTip)
      .on("mouseover", function (event, d) {
        d3.select(this).attr("opacity", 0.75);
        showTip(`<strong>${d.id}</strong><br>mem_limit: ${d.mem}m`, event);
      })
      .on("mouseout", function () {
        d3.select(this).attr("opacity", 1);
        hideTip();
      })
      .on("click", (event, d) => flashCard(d.id));

    g.selectAll("text.val")
      .data(data)
      .join("text")
      .attr("class", "bar-value")
      .attr("x", 4)
      .attr("y", (d) => y(d.id) + y.bandwidth() / 2 + 3.5)
      .text((d) => d.mem + "m")
      .attr("opacity", 0);

    function animateIn() {
      bars.transition().duration(650).delay((d, i) => i * 28).ease(d3.easeCubicOut).attr("width", (d) => x(d.mem));
      g.selectAll("text.val")
        .transition().delay((d, i) => i * 28 + 500).duration(200)
        .attr("x", (d) => x(d.mem) + 6)
        .attr("opacity", 1);
    }
    observeOnce(svg.node(), animateIn);

    const total = d3.sum(data, (d) => d.mem);
    document.getElementById("memTotalNote").innerHTML =
      `Sum of every <code>mem_limit</code> if all 19 containers hit their ceiling simultaneously: <strong>${(total / 1024).toFixed(1)} GB</strong> (${total.toLocaleString()}m) — the practical basis for this repo's README recommending ~16 GB of host RAM.`;
  })();

  // ============================================================
  // Fan-in chart ("most depended upon")
  // ============================================================
  (function renderFanin() {
    const counts = {};
    SERVICES.forEach((s) => (counts[s.id] = 0));
    DEP_EDGES.forEach((e) => (counts[e.source] = (counts[e.source] || 0) + 1));
    const data = Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([id, v]) => ({ id, v, category: SERVICES_BY_ID[id].category }))
      .sort((a, b) => b.v - a.v);

    const svg = d3.select("#faninChart");
    const margin = { top: 6, right: 30, bottom: 6, left: 130 };
    const width = 480 - margin.left - margin.right;
    const rowH = 26;
    const height = data.length * rowH;
    svg.attr("viewBox", `0 0 480 ${height + margin.top + margin.bottom}`);

    const x = d3.scaleLinear().domain([0, d3.max(data, (d) => d.v)]).nice().range([0, width]);
    const y = d3.scaleBand().domain(data.map((d) => d.id)).range([0, height]).padding(0.3);

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    g.selectAll("text.row-label")
      .data(data)
      .join("text")
      .attr("class", "bar-label")
      .attr("x", -8)
      .attr("y", (d) => y(d.id) + y.bandwidth() / 2 + 3.5)
      .attr("text-anchor", "end")
      .text((d) => d.id);

    const bars = g
      .selectAll("rect.bar")
      .data(data)
      .join("rect")
      .attr("y", (d) => y(d.id))
      .attr("height", y.bandwidth())
      .attr("rx", 2)
      .style("fill", (d) => CATEGORY_COLOR[d.category])
      .attr("width", 0)
      .style("cursor", "pointer")
      .on("mousemove", moveTip)
      .on("mouseover", function (event, d) {
        d3.select(this).attr("opacity", 0.75);
        showTip(`<strong>${d.id}</strong><br>${d.v} service${d.v > 1 ? "s" : ""} wait on this directly`, event);
      })
      .on("mouseout", function () {
        d3.select(this).attr("opacity", 1);
        hideTip();
      })
      .on("click", (event, d) => flashCard(d.id));

    g.selectAll("text.val")
      .data(data)
      .join("text")
      .attr("class", "bar-value")
      .attr("y", (d) => y(d.id) + y.bandwidth() / 2 + 3.5)
      .text((d) => d.v)
      .attr("opacity", 0);

    function animateIn() {
      bars.transition().duration(600).delay((d, i) => i * 45).ease(d3.easeCubicOut).attr("width", (d) => x(d.v));
      g.selectAll("text.val")
        .transition().delay((d, i) => i * 45 + 450).duration(200)
        .attr("x", (d) => x(d.v) + 6)
        .attr("opacity", 1);
    }
    observeOnce(svg.node(), animateIn);
  })();

  // ============================================================
  // Composition donuts
  // ============================================================
  function renderDonut(svgSel, legendSel, data, colorFn) {
    const svg = d3.select(svgSel);
    const size = 160;
    const radius = size / 2;
    const g = svg.append("g").attr("transform", `translate(${radius},${radius})`);
    const arc = d3.arc().innerRadius(radius * 0.62).outerRadius(radius - 4);
    const arcHover = d3.arc().innerRadius(radius * 0.62).outerRadius(radius);
    const pie = d3.pie().value((d) => d.value).sort(null).padAngle(0.02);

    const total = d3.sum(data, (d) => d.value);
    g.append("text").attr("class", "donut-center-num").attr("text-anchor", "middle").attr("dy", "-0.1em").attr("font-size", "22px").text(total);
    g.append("text").attr("class", "donut-center-label").attr("text-anchor", "middle").attr("dy", "1.3em").text("total");

    const arcs = g
      .selectAll("path")
      .data(pie(data))
      .join("path")
      .attr("fill", (d) => colorFn(d.data))
      .attr("d", arc)
      .style("cursor", "default")
      .on("mousemove", moveTip)
      .on("mouseover", function (event, d) {
        d3.select(this).transition().duration(120).attr("d", arcHover);
        showTip(`<strong>${d.data.label}</strong><br>${d.data.value} of ${total}`, event);
      })
      .on("mouseout", function () {
        d3.select(this).transition().duration(120).attr("d", arc);
        hideTip();
      });

    const legend = d3.select(legendSel);
    data.forEach((d) => {
      const row = legend.append("span");
      row.append("span").attr("class", "sw").style("background", colorFn(d));
      row.append("span").text(`${d.label} — ${d.value}`);
    });
  }

  renderDonut(
    "#donutLifecycle",
    "#legendLifecycle",
    [
      { label: "Long-running", value: SERVICES.filter((s) => s.lifecycle === "running").length },
      { label: "One-shot init", value: SERVICES.filter((s) => s.lifecycle === "oneshot").length },
    ],
    (d) => (d.label === "One-shot init" ? cssVar("--warn") : cssVar("--good"))
  );

  renderDonut(
    "#donutBuild",
    "#legendBuild",
    [
      { label: "Official image", value: SERVICES.filter((s) => s.build === "official").length },
      { label: "Custom build", value: SERVICES.filter((s) => s.build === "custom").length },
    ],
    (d) => (d.label === "Custom build" ? cssVar("--accent-2") : cssVar("--muted"))
  );

  // ============================================================
  // Small utility: run a callback once when an element scrolls into view
  // ============================================================
  function observeOnce(el, cb) {
    if (!("IntersectionObserver" in window)) return cb();
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          cb();
          io.disconnect();
        }
      });
    }, { threshold: 0.15 });
    io.observe(el);
  }

})();
