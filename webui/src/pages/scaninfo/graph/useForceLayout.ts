import { useMemo } from 'react';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
} from 'd3-force';
import type { GraphNode, GraphEdge, GraphLayoutMode } from '../../../types';

type Position = { x: number; y: number };

export type LayoutResult = {
  positions: Map<string, Position>; // node.id -> {x, y}
  bounds: { width: number; height: number };
};

const RANDOM_SEED_WIDTH = 1000;
const RANDOM_SEED_HEIGHT = 1000;
const FORCE_ITERATIONS = 300;
const FORCE_LINK_DISTANCE = 80;
const FORCE_CHARGE_STRENGTH = -200;
const FORCE_CENTER_X = 500;
const FORCE_CENTER_Y = 500;

export function useForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mode: GraphLayoutMode,
): LayoutResult {
  return useMemo(() => {
    if (nodes.length === 0) {
      return {
        positions: new Map(),
        bounds: { width: RANDOM_SEED_WIDTH, height: RANDOM_SEED_HEIGHT },
      };
    }

    if (mode === 'random') {
      const positions = new Map<string, Position>();
      for (const node of nodes) {
        positions.set(node.id, {
          x: Math.random() * RANDOM_SEED_WIDTH,
          y: Math.random() * RANDOM_SEED_HEIGHT,
        });
      }
      return {
        positions,
        bounds: { width: RANDOM_SEED_WIDTH, height: RANDOM_SEED_HEIGHT },
      };
    }

    // mode === 'force'
    type SimNode = GraphNode & { x?: number; y?: number; index?: number };
    type SimLink = { source: string | SimNode; target: string | SimNode };

    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }));
    const simLinks: SimLink[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(FORCE_LINK_DISTANCE),
      )
      .force('charge', forceManyBody().strength(FORCE_CHARGE_STRENGTH))
      .force('center', forceCenter(FORCE_CENTER_X, FORCE_CENTER_Y))
      .stop();

    sim.tick(FORCE_ITERATIONS);

    const positions = new Map<string, Position>();
    for (const node of simNodes) {
      positions.set(node.id, {
        x: node.x ?? FORCE_CENTER_X,
        y: node.y ?? FORCE_CENTER_Y,
      });
    }

    // Derive bounds from node positions so the renderer can set viewBox.
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const p of positions.values()) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    return {
      positions,
      bounds: {
        width: Math.max(1, maxX - minX),
        height: Math.max(1, maxY - minY),
      },
    };
  }, [nodes, edges, mode]);
}
