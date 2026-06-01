import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { PathLayer, TextLayer } from "@deck.gl/layers";
import type { DeckPosition } from "../mapProjection";
import type { Color } from "../mapTypes";

export type MapHexCell = {
  id: string;
  path: DeckPosition[];
};

export type MapHexGuideLine = {
  id: string;
  axis: "x" | "y" | "diagonal";
  path: DeckPosition[];
  label?: string;
  labelPosition?: DeckPosition;
  labelPixelOffset?: [number, number];
};

type MapHexGuideLabelLine = MapHexGuideLine & {
  label: string;
  labelPosition: DeckPosition;
  labelPixelOffset: [number, number];
};

const HEX_LINE_COLOR: Color = [112, 178, 255, 90];
const GUIDE_LINE_COLORS: Record<MapHexGuideLine["axis"], Color> = {
  x: [255, 215, 82, 230],
  y: [94, 220, 255, 230],
  diagonal: [255, 255, 255, 170],
};

export function createHexGridLayer(cells: readonly MapHexCell[]): PathLayer<MapHexCell> | null {
  if (cells.length === 0) return null;

  return new PathLayer<MapHexCell>({
    id: "mining-hex-grid",
    data: cells,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    widthUnits: "pixels",
    getPath: (cell) => cell.path,
    getColor: () => HEX_LINE_COLOR,
    getWidth: () => 1,
  });
}

export function createHexGuideLineLayer(
  lines: readonly MapHexGuideLine[],
): PathLayer<MapHexGuideLine> | null {
  if (lines.length === 0) return null;

  return new PathLayer<MapHexGuideLine>({
    id: "mining-hex-guide-lines",
    data: lines,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    widthUnits: "pixels",
    getPath: (line) => line.path,
    getColor: (line) => GUIDE_LINE_COLORS[line.axis],
    getWidth: (line) => (line.axis === "diagonal" ? 1.5 : 2),
  });
}

export function createHexGuideLabelLayer(
  lines: readonly MapHexGuideLine[],
): TextLayer<MapHexGuideLabelLine> | null {
  const labeledLines = lines.filter(hasGuideLabel);
  if (labeledLines.length === 0) return null;

  return new TextLayer<MapHexGuideLabelLine>({
    id: "mining-hex-guide-labels",
    data: labeledLines,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    billboard: true,
    characterSet: "XY+-0123456789 ",
    fontFamily: '"Cascadia Mono", "Consolas", monospace',
    fontWeight: 700,
    getPosition: (line) => line.labelPosition,
    getText: (line) => line.label,
    getSize: () => 12,
    getColor: (line) => GUIDE_LINE_COLORS[line.axis],
    getPixelOffset: (line) => line.labelPixelOffset,
    getTextAnchor: () => "middle",
    getAlignmentBaseline: () => "center",
    fontSettings: {
      sdf: true,
      fontSize: 18,
      buffer: 2,
    },
  });
}

function hasGuideLabel(line: MapHexGuideLine): line is MapHexGuideLabelLine {
  return Boolean(line.label && line.labelPosition && line.labelPixelOffset);
}
