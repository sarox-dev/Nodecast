// graph-view.js — Knowledge Graph (D3 force simulation)

(function initGraphGlobals() {
    window.graphMode = false;
    window.graphSimulation = null;
})();

window.addEventListener('DOMContentLoaded', () => {
    function readGraphSettings() {
        const s = Number(document.getElementById('graph-spacing')?.value || 5);
        const g = Number(document.getElementById('graph-gravity')?.value || 3);
        return { spacing: s, gravity: g };
    }

    function _transitionDuration() {
        const spd = localStorage.getItem('animationSpeed') || 'fast';
        if (spd === 'instant') return 0;
        if (spd === 'fast') return 0.2;
        if (spd === 'slow') return 1;
        return 0.5;
    }

    function flowAnimationSpeed() {
        const spd = localStorage.getItem('animationSpeed') || 'fast';
        if (spd === 'instant') return 0;
        if (spd === 'fast') return 2;
        if (spd === 'slow') return 5;
        return 3;
    }

    window.setGraphMode = function() {
        window.graphMode = true;
        webMode = false;
        const pageShell = document.getElementById('page-shell');
        if (pageShell) pageShell.classList.remove('web-search-mode');
        const graphArea = document.getElementById('graph-area');
        if (graphArea) graphArea.hidden = false;
        const contentView = document.getElementById('content-view');
        if (contentView) contentView.hidden = true;
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', false);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', false);
        document.getElementById('sidebar-graph-nav')?.classList.toggle('active', true);
        loadGraph();
    };

    async function loadGraph() {
        const area = document.getElementById('graph-area');
        const container = document.getElementById('graph-container');
        const loadingEl = document.getElementById('graph-loading');
        const empty = document.getElementById('graph-empty');
        if (loadingEl) loadingEl.hidden = false;
        if (empty) empty.hidden = true;
        if (window.graphSimulation) {
            window.graphSimulation.stop();
            window.graphSimulation = null;
        }
        if (container) container.innerHTML = '';
        try {
            const showOrphans = document.getElementById('graph-show-orphans')?.checked || false;
            const r = await fetch(`/api/ai/relation-graph?limit=200&include_orphans=${showOrphans}`);
            const data = await r.json();
            if (loadingEl) loadingEl.hidden = true;
            if (!data.nodes || data.nodes.length === 0) {
                if (empty) empty.hidden = false;
                const statsEl = document.getElementById('graph-stats');
                if (statsEl) statsEl.hidden = true;
                return;
            }
            renderGraph(data, container);
            const statsEl = document.getElementById('graph-stats');
            const statsText = document.getElementById('graph-stats-text');
            if (statsEl && statsText) {
                const atomics = data.nodes.length;
                const entities = data.nodes.filter(n => n.type === 'entity').length;
                const edges = data.edges.length;
                const parts = [`${atomics} atomics`];
                if (entities > 0) parts.push(`${entities} entities`);
                parts.push(`${edges} connections`);
                statsText.textContent = parts.join(' · ');
                statsEl.hidden = false;
            }
        } catch (e) {
            if (loadingEl) loadingEl.hidden = true;
            if (container) container.innerHTML = `<div class="graph-error">Error loading graph: ${e.message}</div>`;
            const statsEl = document.getElementById('graph-stats');
            if (statsEl) statsEl.hidden = true;
        }
    }

    function renderGraph(data, container) {
        const width = container.clientWidth || 800;
        const height = container.clientHeight || 500;
        const svg = d3.select(container).append('svg')
            .attr('width', width).attr('height', height);

        const g = svg.append('g');

        let currentZoom = 1;
        let animDur = _transitionDuration();

        svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', (e) => {
            g.attr('transform', e.transform);
            currentZoom = e.transform.k;
            refreshLinkOpacity();
        }));

        const nodes = data.nodes.map(n => ({ ...n }));
        const nodeMap = {};
        nodes.forEach(n => nodeMap[n.id] = n);

        const links = data.edges.map(e => ({
            source: e.source_id,
            target: e.target_id,
            relation_type: e.relation_type,
            strength: e.strength || 0.5,
        })).filter(e => nodeMap[e.source] && nodeMap[e.target]);

        const TYPE_COLORS = {
            related: { stroke: '#475569', text: '#94a3b8' },
            related_to: { stroke: '#64748b', text: '#94a3b8' },
            references: { stroke: '#1f6feb', text: '#60a5fa' },
            depends_on: { stroke: '#da3633', text: '#f87171' },
            implements: { stroke: '#8250df', text: '#a78bfa' },
            supports: { stroke: '#238636', text: '#4ade80' },
            contradicts: { stroke: '#da3633', text: '#f87171' },
            part_of: { stroke: '#9e6a03', text: '#fbbf24' },
            similar_to: { stroke: '#d29922', text: '#fbbf24' },
            version_of: { stroke: '#238636', text: '#4ade80' },
        };
        const TYPE_ORDER = [
            'related', 'related_to', 'depends_on', 'implements', 'references',
            'supports', 'contradicts', 'part_of', 'similar_to', 'version_of',
        ];
        links.sort((a, b) => TYPE_ORDER.indexOf(a.relation_type) - TYPE_ORDER.indexOf(b.relation_type));

        const defaultColors = { stroke: '#475569', text: '#94a3b8' };

        const linkBundle = new Map();
        links.forEach((l, idx) => {
            l._idx = idx;
            const key = l.source < l.target ? `${l.source}|${l.target}` : `${l.target}|${l.source}`;
            if (!linkBundle.has(key)) linkBundle.set(key, []);
            linkBundle.get(key).push(l);
        });

        links.forEach(l => {
            const key = l.source < l.target ? `${l.source}|${l.target}` : `${l.target}|${l.source}`;
            const bundle = linkBundle.get(key);
            l._bundleSize = bundle.length;
            l._bundleIdx = bundle.indexOf(l);
        });

        function getCurvature() {
            return Number(document.getElementById('graph-curvature')?.value || 30);
        }

        function computePath(src, tgt, bundleIdx, bundleSize) {
            const dx = tgt.x - src.x;
            const dy = tgt.y - src.y;
            const len = Math.sqrt(dx * dx + dy * dy);
            if (len < 1) return { d: `M${src.x},${src.y}L${tgt.x},${tgt.y}`, cp: null };

            const nx = -dy / len;
            const ny = dx / len;
            const curv = getCurvature() / 100;
            const totalOff = (bundleSize - 1) * 0.5;
            const sign = bundleIdx - totalOff;
            const offset = sign * curv * 30;

            if (Math.abs(offset) < 0.5) {
                return { d: `M${src.x},${src.y}L${tgt.x},${tgt.y}`, cp: null, tParam: 0.25 + curv * 0.25 };
            }

            const mx = (src.x + tgt.x) / 2 + nx * offset;
            const my = (src.y + tgt.y) / 2 + ny * offset;
            return {
                d: `M${src.x},${src.y}Q${mx},${my},${tgt.x},${tgt.y}`,
                cp: { x: mx, y: my },
                tParam: 0.25 + curv * 0.25,
            };
        }

        function getPointOnQuad(p0, p1, p2, t) {
            const mt = 1 - t;
            return {
                x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
                y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
            };
        }

        const linkPath = g.append('g').selectAll('path')
            .data(links).join('path')
            .attr('fill', 'none')
            .attr('stroke', d => (TYPE_COLORS[d.relation_type] || defaultColors).stroke)
            .attr('stroke-width', d => Math.max(1.5, (d.strength || 0.5) * 4))
            .attr('stroke-opacity', 0.4)
            .style('transition', `stroke-opacity ${animDur}s ease`);

        const linkFlow = g.append('g').selectAll('path')
            .data(links).join('path')
            .attr('fill', 'none')
            .attr('stroke', d => (TYPE_COLORS[d.relation_type] || defaultColors).text)
            .attr('stroke-width', d => Math.max(1, (d.strength || 0.5) * 2))
            .attr('stroke-dasharray', '2 10')
            .attr('stroke-opacity', 0.3)
            .style('transition', `stroke-opacity ${animDur}s ease`);

        const linkLabel = g.append('g').selectAll('text')
            .data(links).join('text')
            .text(d => d.relation_type)
            .attr('class', 'link-label')
            .attr('font-size', '10px')
            .attr('fill', d => (TYPE_COLORS[d.relation_type] || defaultColors).text)
            .attr('text-anchor', 'middle')
            .attr('font-weight', '500')
            .style('transition', `opacity ${animDur}s ease`);

        function refreshLinkOpacity() {
            const base = Math.min(1, Math.max(0.25, (currentZoom - 0.1) / 1.5));
            linkPath.attr('stroke-opacity', 0.15 + base * 0.45);
            linkFlow.attr('stroke-opacity', 0.1 + base * 0.3);
            linkLabel.attr('opacity', 0.1 + base * 0.6);
        }
        refreshLinkOpacity();

        (function animateFlow() {
            const dur = flowAnimationSpeed();
            if (dur <= 0) return;
            linkFlow.style('animation', `link-flow ${dur}s linear infinite`);
        })();

        const node = g.append('g').selectAll('g')
            .data(nodes).join('g')
            .style('cursor', 'pointer')
            .style('transition', `opacity ${animDur}s ease`)
            .call(d3.drag()
                .on('start', (e, d) => {
                    window.graphSimulation?.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
                .on('end', (e, d) => {
                    window.graphSimulation?.alphaTarget(0);
                    d.fx = null; d.fy = null;
                })
            );

        node.append('circle')
            .attr('r', d => d.orphan ? 5 : (d.type === 'capture' ? 8 : 6))
            .attr('fill', d => d.orphan ? '#334155' : (d.type === 'capture' ? '#60a5fa' : '#22c55e'))
            .attr('stroke', '#1a1a2e')
            .attr('stroke-width', d => d.orphan ? 1 : 2);

        node.append('text')
            .text(d => d.label.length > 30 ? d.label.slice(0, 30) + '...' : d.label)
            .attr('dx', d => d.type === 'capture' ? 12 : 8)
            .attr('dy', 4)
            .attr('font-size', d => d.orphan ? '9px' : '11px')
            .attr('fill', d => d.orphan ? '#64748b' : '#e2e8f0')
            .attr('pointer-events', 'none');

        node.on('click', (e, d) => {
            if (d.type === 'capture') {
                window.open(`/capture/${d.id}`, '_blank');
            }
        });

        node.append('title')
            .text(d => `${d.label} (${d.type}${d.subtype ? ': ' + d.subtype : ''})`);

        function setLinkProximity(mx, my) {
            const maxDist = Math.max(width, height) * 0.5;
            links.forEach((l, i) => {
                const sx = typeof l.source === 'object' ? l.source.x : 0;
                const sy = typeof l.source === 'object' ? l.source.y : 0;
                const tx = typeof l.target === 'object' ? l.target.x : 0;
                const ty = typeof l.target === 'object' ? l.target.y : 0;
                const cx = (sx + tx) / 2;
                const cy = (sy + ty) / 2;
                const d = Math.sqrt((mx - cx) ** 2 + (my - cy) ** 2);
                const t = Math.min(1, d / maxDist);
                const op = Math.max(0.02, 1 - t * t);
                linkPath.filter((_, j) => j === i).attr('stroke-opacity', 0.15 + op * 0.6);
                linkFlow.filter((_, j) => j === i).attr('stroke-opacity', 0.1 + op * 0.4);
                linkLabel.filter((_, j) => j === i).attr('opacity', Math.max(0.02, op * 0.7));
            });
            node.attr('opacity', 1);
        }

        svg.on('mousemove', (e) => {
            if (_hoverActive) return;
            const [mx, my] = d3.pointer(e, g.node());
            setLinkProximity(mx, my);
        });
        svg.on('mouseleave', () => {
            if (_hoverActive) return;
            refreshLinkOpacity();
            node.attr('opacity', 1);
        });

        let _hoverActive = false;

        function dimAll() {
            linkPath.attr('stroke-opacity', 0.04);
            linkFlow.attr('stroke-opacity', 0.02);
            linkLabel.attr('opacity', 0.02);
            node.attr('opacity', 0.08);
        }

        function restoreOnLeave() {
            _hoverActive = false;
            refreshLinkOpacity();
            node.attr('opacity', 1);
        }

        const nodeLinks = {};
        links.forEach((l, i) => {
            const sid = typeof l.source === 'object' ? l.source.id : l.source;
            const tid = typeof l.target === 'object' ? l.target.id : l.target;
            (nodeLinks[sid] = nodeLinks[sid] || []).push(i);
            (nodeLinks[tid] = nodeLinks[tid] || []).push(i);
        });

        function applyHover(indices) {
            const activeIds = new Set();
            indices.forEach(i => {
                const l = links[i];
                const sid = typeof l.source === 'object' ? l.source.id : l.source;
                const tid = typeof l.target === 'object' ? l.target.id : l.target;
                activeIds.add(sid);
                activeIds.add(tid);
                linkPath.filter((_, j) => j === i).attr('stroke-opacity', 0.75);
                linkFlow.filter((_, j) => j === i).attr('stroke-opacity', 0.5);
                linkLabel.filter((_, j) => j === i).attr('opacity', 1);
            });
            node.filter(n => activeIds.has(n.id)).attr('opacity', 1);
        }

        node.on('mouseenter', (e, d) => {
            _hoverActive = true;
            dimAll();
            applyHover(nodeLinks[d.id] || []);
        });
        node.on('mouseleave', restoreOnLeave);

        linkPath.on('mouseenter', (e, d) => {
            _hoverActive = true;
            dimAll();
            applyHover([d._idx]);
        });
        linkPath.on('mouseleave', restoreOnLeave);

        linkFlow.on('mouseenter', (e, d) => {
            _hoverActive = true;
            dimAll();
            applyHover([d._idx]);
        });
        linkFlow.on('mouseleave', restoreOnLeave);

        function rebuildCurves() {
            links.forEach(l => {
                const src = typeof l.source === 'object' ? l.source : nodeMap[l.source];
                const tgt = typeof l.target === 'object' ? l.target : nodeMap[l.target];
                if (!src || !tgt) return;
                const pathData = computePath(src, tgt, l._bundleIdx, l._bundleSize);
                linkPath.filter((_, i) => i === l._idx).attr('d', pathData.d);
                linkFlow.filter((_, i) => i === l._idx).attr('d', pathData.d);
                if (pathData.cp) {
                    const p = getPointOnQuad(src, pathData.cp, tgt, pathData.tParam);
                    linkLabel.filter((_, i) => i === l._idx).attr('x', p.x).attr('y', p.y);
                } else {
                    const mx = (src.x + tgt.x) / 2;
                    const my = (src.y + tgt.y) / 2;
                    linkLabel.filter((_, i) => i === l._idx).attr('x', mx).attr('y', my);
                }
            });
        }

        function buildSimFromSettings() {
            const { spacing, gravity } = readGraphSettings();
            const s = spacing;
            const g = gravity * 0.005;
            if (window.graphSimulation) {
                window.graphSimulation.force('link').distance(30 * s);
                window.graphSimulation.force('charge').strength(-50 * s);
                window.graphSimulation.force('collision').radius(10 + s * 4);
                window.graphSimulation.force('x').strength(g);
                window.graphSimulation.force('y').strength(g);
                window.graphSimulation.alpha(1).restart();
            } else {
                window.graphSimulation = d3.forceSimulation(nodes)
                    .force('link', d3.forceLink(links).id(d => d.id).distance(30 * s).strength(0.3))
                    .force('charge', d3.forceManyBody().strength(-50 * s))
                    .force('center', d3.forceCenter(width / 2, height / 2))
                    .force('collision', d3.forceCollide().radius(10 + s * 4))
                    .force('x', d3.forceX(width / 2).strength(g))
                    .force('y', d3.forceY(height / 2).strength(g));

                window.graphSimulation.on('tick', () => {
                    rebuildCurves();
                    node.attr('transform', d => `translate(${d.x},${d.y})`);
                });

                window.graphSimulation.alpha(1).restart();
            }
        }

        buildSimFromSettings();

        const spacingSlider = document.getElementById('graph-spacing');
        const spacingVal = document.getElementById('graph-spacing-val');
        const gravitySlider = document.getElementById('graph-gravity');
        const gravityVal = document.getElementById('graph-gravity-val');
        const curvatureSlider = document.getElementById('graph-curvature');
        const curvatureVal = document.getElementById('graph-curvature-val');

        function wireSlider(slider, valDisplay, onChange) {
            if (slider) {
                slider.addEventListener('input', () => {
                    if (valDisplay) valDisplay.textContent = slider.value;
                    if (onChange) onChange();
                    else buildSimFromSettings();
                });
            }
        }
        wireSlider(spacingSlider, spacingVal);
        wireSlider(gravitySlider, gravityVal);
        wireSlider(curvatureSlider, curvatureVal, rebuildCurves);

        const ro = new ResizeObserver(() => {
            const w = container.clientWidth;
            const h = container.clientHeight;
            svg.attr('width', w).attr('height', h);
            if (window.graphSimulation) {
                window.graphSimulation.force('center', d3.forceCenter(w / 2, h / 2));
                window.graphSimulation.force('x', d3.forceX(w / 2));
                window.graphSimulation.force('y', d3.forceY(h / 2));
                window.graphSimulation.alpha(0.3).restart();
            }
        });
        ro.observe(container);
    }

    // ─── Graph menu (hamburger) ──────────────────────────────────
    (function initGraphMenu() {
        const btn = document.getElementById('graph-settings-btn');
        const popup = document.getElementById('graph-settings-popup');
        if (!btn || !popup) return;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            popup.hidden = !popup.hidden;
        });
        document.addEventListener('click', (e) => {
            if (!popup.hidden && !popup.contains(e.target) && e.target !== btn) {
                popup.hidden = true;
            }
        });
    })();

    // ─── Graph event listeners ─────────────────────────────────
    document.getElementById('sidebar-graph-nav')?.addEventListener('click', () => window.setGraphMode());
    document.getElementById('graph-show-orphans')?.addEventListener('change', () => {
        if (window.graphMode) setTimeout(loadGraph, 100);
    });
    document.getElementById('graph-show-entities')?.addEventListener('change', () => {
        if (window.graphMode) setTimeout(loadGraph, 100);
    });
});
