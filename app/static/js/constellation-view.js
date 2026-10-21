// Ambient overview of the user's accepted concepts, aggregates, and source groups.
(function createConstellationView() {
    let simulation = null;
    let cachedData = null;

    function render(data) {
        const container = document.getElementById('constellation-container');
        const empty = document.getElementById('constellation-empty');
        if (!container || typeof d3 === 'undefined') return;
        simulation?.stop();
        container.innerHTML = '';
        const nodes = (data.nodes || []).map(node => ({ ...node }));
        const known = new Set(nodes.map(node => node.id));
        const semanticLinks = (data.edges || []).filter(edge => known.has(edge.source_id) && known.has(edge.target_id))
            .map(edge => ({ ...edge, source: edge.source_id, target: edge.target_id }));
        const pairKeys = new Set(semanticLinks.map(edge => [edge.source_id, edge.target_id].sort().join('|')));
        const ambientLinks = [];
        nodes.forEach((node, index) => {
            if (nodes.length < 2) return;
            const target = nodes[(index + 1) % nodes.length];
            const key = [node.id, target.id].sort().join('|');
            if (!pairKeys.has(key)) {
                pairKeys.add(key);
                ambientLinks.push({ source: node.id, target: target.id, visual_only: true, confidence: 0.12 });
            }
        });
        const links = [...semanticLinks, ...ambientLinks];
        empty.hidden = nodes.length > 0;
        if (!nodes.length) return;

        const width = container.clientWidth || window.innerWidth;
        const height = container.clientHeight || window.innerHeight;
        const baseRadius = Math.min(width, height) * 0.29;
        nodes.forEach((item, index) => {
            const angle = index * 2.399963229728653;
            const ringOffset = ((index % 5) - 2) * 18;
            item.x = width / 2 + Math.cos(angle) * (baseRadius + ringOffset);
            item.y = height / 2 + Math.sin(angle) * (baseRadius + ringOffset);
        });
        const svg = d3.select(container).append('svg').attr('viewBox', `0 0 ${width} ${height}`);
        const root = svg.append('g');
        root.append('g').attr('class', 'constellation-links').selectAll('line').data(links).join('line')
            .attr('class', edge => edge.visual_only ? 'constellation-link-ambient' : 'constellation-link-semantic')
            .attr('stroke-width', edge => 0.5 + Math.min(1.5, Number(edge.confidence || 0.5)));
        const node = root.append('g').attr('class', 'constellation-nodes').selectAll('g').data(nodes).join('g')
            .attr('class', item => `constellation-node constellation-node-${item.kind}`)
            .attr('tabindex', item => item.kind === 'concept' || item.source_url ? 0 : null)
            .attr('role', item => item.kind === 'concept' || item.source_url ? 'button' : null);
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('font-size', item => 10 + Math.min(12, Math.sqrt(Number(item.weight || 1)) * 2.3))
            .text(item => item.label);

        function activate(item) {
            if (item.kind === 'source' && item.source_url) {
                window.open(item.source_url, '_blank', 'noopener');
                return;
            }
            window.setWebMode?.(false);
            const input = document.getElementById('query');
            if (input) input.value = item.label;
            document.getElementById('search-form')?.requestSubmit();
        }
        node.on('click', (_event, item) => activate(item)).on('keydown', (event, item) => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(item); }
        });
        const respectSystemMotion = localStorage.getItem('respectSystemMotion') !== 'false';
        const reducedMotion = respectSystemMotion && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        const motionScale = reducedMotion ? 0 : Math.max(0, Math.min(2, Number(localStorage.getItem('graphMotion') || 100) / 100));
        let pointer = null;

        function ellipticalCollision() {
            let forceNodes = [];
            function force(alpha) {
                for (let index = 0; index < forceNodes.length; index += 1) {
                    const first = forceNodes[index];
                    const firstRx = Math.max(42, String(first.label || '').length * 4.6 + 16);
                    const firstRy = 13;
                    for (let otherIndex = index + 1; otherIndex < forceNodes.length; otherIndex += 1) {
                        const second = forceNodes[otherIndex];
                        const rx = firstRx + Math.max(42, String(second.label || '').length * 4.6 + 16);
                        const ry = firstRy + 13;
                        let dx = (second.x || 0) - (first.x || 0);
                        let dy = (second.y || 0) - (first.y || 0);
                        if (!dx && !dy) dx = 0.01;
                        const normalized = Math.hypot(dx / rx, dy / ry);
                        if (normalized >= 1) continue;
                        const overlap = (1 - normalized) * 0.42 * alpha;
                        const nx = (dx / (rx * rx)) / Math.max(0.0001, Math.hypot(dx / (rx * rx), dy / (ry * ry)));
                        const ny = (dy / (ry * ry)) / Math.max(0.0001, Math.hypot(dx / (rx * rx), dy / (ry * ry)));
                        const pushX = nx * overlap * rx;
                        const pushY = ny * overlap * ry;
                        first.vx -= pushX;
                        first.vy -= pushY;
                        second.vx += pushX;
                        second.vy += pushY;
                    }
                }
            }
            force.initialize = items => { forceNodes = items; };
            return force;
        }

        function pointerAvoidance() {
            let forceNodes = [];
            function force() {
                if (!pointer || !motionScale) return;
                forceNodes.forEach(item => {
                    const dx = (item.x || 0) - pointer[0];
                    const dy = (item.y || 0) - pointer[1];
                    const distance = Math.max(20, Math.hypot(dx, dy));
                    if (distance >= 190) return;
                    const push = Math.pow((190 - distance) / 190, 1.35) * 0.72 * 5.4 * motionScale;
                    item.vx += (dx / distance) * push;
                    item.vy += (dy / distance) * push;
                });
            }
            force.initialize = items => { forceNodes = items; };
            return force;
        }
        function searchBarAvoidance() {
            let forceNodes = [];
            function force(alpha) {
                const bar = document.getElementById('search-bar-wrapper')?.getBoundingClientRect();
                const canvas = container.getBoundingClientRect();
                if (!bar || !canvas) return;
                // Include the likely label width, not only the node's centre, so
                // long concept names cannot remain visually behind the input.
                const left = bar.left - canvas.left - 150;
                const right = bar.right - canvas.left + 150;
                const top = bar.top - canvas.top - 28;
                const bottom = bar.bottom - canvas.top + 28;
                forceNodes.forEach(item => {
                    if (item.x < left || item.x > right || item.y < top || item.y > bottom) return;
                    const topDistance = Math.abs(item.y - top);
                    const bottomDistance = Math.abs(bottom - item.y);
                    const direction = topDistance < bottomDistance ? -1 : 1;
                    const target = direction < 0 ? top : bottom;
                    const delta = target - item.y;
                    item.vy += delta * Math.max(0.18, alpha) * 0.42 * 4;
                    if (Math.abs(delta) < 0.5) item.vy *= 0.45;
                });
            }
            force.initialize = items => { forceNodes = items; };
            return force;
        }
        simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links).id(item => item.id).distance(edge => edge.visual_only ? 155 : 118).strength(edge => edge.visual_only ? 0.025 : 0.18))
            .force('charge', d3.forceManyBody().strength(-46))
            .force('collide', ellipticalCollision())
            .force('radial', d3.forceRadial(Math.min(width, height) * 0.34, width / 2, height / 2).strength(0.018))
            .force('search-bar', searchBarAvoidance())
            .force('pointer', pointerAvoidance())
            .velocityDecay(0.58)
            .alphaDecay(0.035).on('tick', () => {
                root.selectAll('.constellation-links line')
                    .attr('x1', edge => edge.source.x).attr('y1', edge => edge.source.y)
                    .attr('x2', edge => edge.target.x).attr('y2', edge => edge.target.y);
                node.attr('transform', item => {
                    const x = Math.max(70, Math.min(width - 70, item.x || width / 2));
                    const y = Math.max(40, Math.min(height - 40, item.y || height / 2));
                    const distance = Math.hypot(x - width / 2, y - height / 2);
                    const edgeDistance = Math.max(1, Math.hypot(width / 2, height / 2));
                    item._opacity = Math.max(0.04, Math.min(0.96, 0.04 + Math.pow(distance / edgeDistance, 1.7) * 1.35));
                    return `translate(${x},${y})`;
                }).style('opacity', item => item._opacity);
            });

        svg.on('mousemove', event => {
            pointer = d3.pointer(event, svg.node());
            simulation.alphaTarget(motionScale ? 0.022 : 0).restart();
        }).on('mouseleave', () => {
            pointer = null;
            simulation.alphaTarget(0);
        });
    }

    async function load() {
        try {
            const response = await fetch('/api/memory/constellation/overview?limit=48');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            cachedData = await response.json();
            render(cachedData);
        } catch (_error) {
            const empty = document.getElementById('constellation-empty');
            if (empty) { empty.textContent = 'Knowledge overview is temporarily unavailable.'; empty.hidden = false; }
            if (typeof showToast === 'function') showToast('Knowledge overview could not be loaded', 'error');
        }
    }

    window.nodecastConstellation = { load, render: () => cachedData && render(cachedData) };
    window.addEventListener('DOMContentLoaded', () => {
        load();
        const container = document.getElementById('constellation-container');
        if (container && typeof ResizeObserver !== 'undefined') {
            new ResizeObserver(() => cachedData && render(cachedData)).observe(container);
        }
    });
})();
