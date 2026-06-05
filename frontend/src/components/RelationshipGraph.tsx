import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  wealth: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  trust: number;
  friendship: number;
}

interface Props {
  agents: Array<{ id: string; name: string; stats: { wealth: number } }>;
  relationships: Array<{
    a_id: string;
    b_id: string;
    a_name?: string;
    b_name?: string;
    trust: number;
    friendship: number;
  }>;
}

export default function RelationshipGraph({ agents, relationships }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || agents.length === 0) return;

    const width = svgRef.current.clientWidth || 500;
    const height = 320;

    const nodes: SimNode[] = agents.map((a) => ({
      id: a.id,
      name: a.name,
      wealth: a.stats.wealth,
    }));

    const links: SimLink[] = relationships.map((r) => ({
      source: r.a_id,
      target: r.b_id,
      trust: r.trust,
      friendship: r.friendship,
    }));

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(80)
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = svg
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", (d) => d3.interpolateRdYlGn(d.trust))
      .attr("stroke-width", (d) => 1 + d.friendship * 4)
      .attr("stroke-opacity", 0.7);

    const node = svg
      .append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x ?? 0;
            d.fy = d.y ?? 0;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    node
      .append("circle")
      .attr("r", (d) => 6 + Math.min(d.wealth / 5, 12))
      .attr("fill", "#4ecdc4")
      .attr("stroke", "#2d3a4f")
      .attr("stroke-width", 2);

    node
      .append("text")
      .text((d) => d.name)
      .attr("x", 10)
      .attr("y", 4)
      .attr("fill", "#e8edf4")
      .attr("font-size", "10px");

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);

      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      simulation.stop();
    };
  }, [agents, relationships]);

  return (
    <div className="graph-panel">
      <h3>Relationship Graph</h3>
      <svg ref={svgRef} width="100%" height={320} />
      <style>{`
        .graph-panel {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 1rem;
        }
        .graph-panel h3 { font-size: 0.875rem; color: var(--muted); margin-bottom: 0.5rem; }
      `}</style>
    </div>
  );
}
