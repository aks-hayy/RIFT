export type TopologyLayoutNodeInput = { nodeId: string };

export type TopologyLayoutLinkInput = {
  sourceNodeId: string;
  targetNodeId: string;
};

export function buildNodeMapLayout<
  TNode extends TopologyLayoutNodeInput,
  TLink extends TopologyLayoutLinkInput,
>(nodes: TNode[], links: TLink[]) {
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  const rows = Math.max(1, Math.ceil(nodes.length / columns));
  const layoutNodes = nodes.map((node, index) => ({
    id: node.nodeId,
    x: ((index % columns) + 0.5) * (100 / columns),
    y: (Math.floor(index / columns) + 0.5) * (100 / rows),
  }));
  const ids = new Set(nodes.map((node) => node.nodeId));
  const measuredLinks = links.filter(
    (link) => ids.has(link.sourceNodeId) && ids.has(link.targetNodeId),
  );
  return { nodes: layoutNodes, links: measuredLinks };
}
