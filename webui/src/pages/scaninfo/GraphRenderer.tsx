import { useRef } from 'react';
import { Button, Group } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { ParentSize } from '@visx/responsive';
import { Zoom } from '@visx/zoom';
import { Graph, DefaultNode } from '@visx/network';
import type { GraphNode, GraphEdge } from '../../types';
import type { LayoutResult } from './graph/useForceLayout';

const ROOT_COLOR = '#f00';
const NODE_COLOR = '#228be6';
const EDGE_COLOR = '#ccc';

type NetworkNode = GraphNode & { x: number; y: number };
type NetworkLink = { source: NetworkNode; target: NetworkNode };

function exportSvgAsPng(svgEl: SVGSVGElement, filename: string): Promise<void> {
  const serialized = new XMLSerializer().serializeToString(svgEl);
  const svgBlob = new Blob([serialized], {
    type: 'image/svg+xml;charset=utf-8',
  });
  const url = URL.createObjectURL(svgBlob);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = svgEl.clientWidth || 1000;
      canvas.height = svgEl.clientHeight || 600;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        URL.revokeObjectURL(url);
        reject(new Error('Canvas 2d context unavailable'));
        return;
      }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        if (!blob) return reject(new Error('PNG export failed'));
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        resolve();
      }, 'image/png');
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('SVG -> image load failed'));
    };
    img.src = url;
  });
}

export function GraphRenderer({
  nodes,
  edges,
  layout,
  scanId,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layout: LayoutResult;
  scanId: string;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Build fully-typed network shape for visx.
  const networkNodes: NetworkNode[] = nodes.map((n) => {
    const pos = layout.positions.get(n.id) ?? { x: 0, y: 0 };
    return { ...n, x: pos.x, y: pos.y };
  });
  const nodeById = new Map<string, NetworkNode>();
  for (const n of networkNodes) nodeById.set(n.id, n);
  const networkLinks: NetworkLink[] = edges
    .map((e) => {
      const source = nodeById.get(e.source);
      const target = nodeById.get(e.target);
      if (!source || !target) return null;
      return { source, target };
    })
    .filter((x): x is NetworkLink => x !== null);

  return (
    <>
      <Group justify="flex-end" mb="sm">
        <Button
          variant="light"
          leftSection={<IconDownload size={14} />}
          onClick={() => {
            if (!svgRef.current) return;
            void exportSvgAsPng(svgRef.current, `scan-graph-${scanId}.png`);
          }}
        >
          Download PNG
        </Button>
        <Button
          component="a"
          href={`/scanviz?id=${encodeURIComponent(scanId)}&gexf=1`}
          variant="light"
          leftSection={<IconDownload size={14} />}
        >
          Download GEXF
        </Button>
      </Group>
      <div style={{ width: '100%', height: 600, border: '1px solid #e9ecef', borderRadius: 4 }}>
        <ParentSize>
          {({ width, height }) => (
            <Zoom<SVGSVGElement>
              width={width}
              height={height}
              scaleXMin={0.1}
              scaleXMax={10}
              scaleYMin={0.1}
              scaleYMax={10}
            >
              {(zoom) => (
                <svg
                  ref={svgRef}
                  width={width}
                  height={height}
                  style={{ cursor: zoom.isDragging ? 'grabbing' : 'grab' }}
                  onWheel={zoom.handleWheel}
                  onMouseDown={zoom.dragStart}
                  onMouseMove={zoom.dragMove}
                  onMouseUp={zoom.dragEnd}
                  onMouseLeave={() => {
                    if (zoom.isDragging) zoom.dragEnd();
                  }}
                >
                  <rect width={width} height={height} fill="#fff" />
                  <g transform={zoom.toString()}>
                    <Graph<NetworkLink, NetworkNode>
                      graph={{ nodes: networkNodes, links: networkLinks }}
                      linkComponent={({ link }) => (
                        <line
                          x1={link.source.x}
                          y1={link.source.y}
                          x2={link.target.x}
                          y2={link.target.y}
                          stroke={EDGE_COLOR}
                          strokeWidth={1}
                        />
                      )}
                      nodeComponent={({ node }) => (
                        <g>
                          <DefaultNode
                            cx={0}
                            cy={0}
                            r={6}
                            fill={node.isRoot ? ROOT_COLOR : NODE_COLOR}
                          />
                          <text
                            x={10}
                            y={4}
                            fontSize={10}
                            fill="#333"
                          >
                            {node.label.length > 24
                              ? `${node.label.slice(0, 24)}…`
                              : node.label}
                          </text>
                        </g>
                      )}
                    />
                  </g>
                </svg>
              )}
            </Zoom>
          )}
        </ParentSize>
      </div>
    </>
  );
}
