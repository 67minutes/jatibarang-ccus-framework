import type {
  CarbonPricePlan,
  Coordinate,
  ScreenRequest,
} from "../api/types";
import type { SelectionKind } from "../state/selection.store";
import type { ArtifactReferencedRequestSummary } from "../memo/studyMemo";

type SceneRequest = ScreenRequest | ArtifactReferencedRequestSummary;

/**
 * Scene assembly shared by the 2D map and (Phase 4) the 3D viewport. Produces a
 * geographic, renderer-agnostic model; the renderers project it to their own
 * coordinate space.
 *
 * Node coordinates come from the request (sources and candidate wells carry
 * lat/lon). Route geometry in the result is expressed as node-to-node segments;
 * junction nodes without coordinates are dropped, so the map draws the richest
 * subset it can resolve without inventing geometry (see plan risk note).
 */

export interface SceneNode {
  id: string;
  kind: "source" | "well";
  location: Coordinate;
  dim: boolean;
}

export interface SceneRoute {
  id: string;
  mode: "pipeline" | "trucking";
  path: Coordinate[];
}

export interface SceneBooster {
  id: string;
  location: Coordinate;
}

export interface Scene {
  nodes: SceneNode[];
  routes: SceneRoute[];
  boosters: SceneBooster[];
}

function isCoordinate(value: unknown): value is Coordinate {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as Coordinate).latitude === "number" &&
    typeof (value as Coordinate).longitude === "number"
  );
}

/** Extract `{id -> location}` from the loosely-typed request candidates/sources. */
export function nodeCoordinateMap(request: SceneRequest): Map<string, Coordinate> {
  const coords = new Map<string, Coordinate>();
  if (request.mode !== "inline") return coords;
  for (const source of request.sources) {
    coords.set(source.id, source.location);
  }
  for (const raw of request.candidates) {
    if (raw && typeof raw === "object") {
      const c = raw as { candidate_id?: unknown; location?: unknown };
      if (typeof c.candidate_id === "string" && isCoordinate(c.location)) {
        coords.set(c.candidate_id, c.location);
      }
    }
  }
  return coords;
}

export function collectSceneObjects(
  request: SceneRequest,
  plan: CarbonPricePlan | null,
): Scene {
  const coords = nodeCoordinateMap(request);
  const sourceIds = new Set(
    request.mode === "inline" ? request.sources.map((s) => s.id) : [],
  );
  const selectedWells = new Set(plan?.selected_wells ?? []);

  const nodes: SceneNode[] = [];
  for (const [id, location] of coords) {
    const isSource = sourceIds.has(id);
    nodes.push({
      id,
      kind: isSource ? "source" : "well",
      location,
      dim: !isSource && plan != null && !selectedWells.has(id),
    });
  }

  const routes: SceneRoute[] = [];
  const boosters: SceneBooster[] = [];

  if (plan) {
    const pipeline = plan.pipeline;
    const networkAccepted = pipeline.domain_status === "accepted";

    if (networkAccepted) {
      for (const seg of pipeline.built_segments) {
        const from = coords.get(seg.from_node);
        const to = coords.get(seg.to_node);
        if (from && to) {
          routes.push({ id: seg.segment_id, mode: "pipeline", path: [from, to] });
        }
      }
      for (const booster of pipeline.boosters) {
        const location = coords.get(booster.node_id);
        if (location) boosters.push({ id: booster.node_id, location });
      }
    } else {
      // No viable pipeline (the correct HnP outcome): show the indicated
      // trucking supply from the first source to each candidate well.
      const source = request.mode === "inline" ? request.sources[0] : undefined;
      if (source) {
        const targets = selectedWells.size > 0 ? [...selectedWells] : [...coords.keys()].filter((id) => !sourceIds.has(id));
        for (const wellId of targets) {
          const to = coords.get(wellId);
          if (to) {
            routes.push({
              id: `truck:${wellId}`,
              mode: "trucking",
              path: [source.location, to],
            });
          }
        }
      }
    }
  }

  return { nodes, routes, boosters };
}

// ---- Projection to a 2D view box ----------------------------------------

export interface ViewPoint {
  x: number;
  y: number;
}
export interface ViewNode extends ViewPoint {
  id: string;
  kind: SelectionKind;
  dim: boolean;
}
export interface ViewRoute {
  id: string;
  mode: "pipeline" | "trucking";
  points: ViewPoint[];
}
export interface ViewBooster extends ViewPoint {
  id: string;
}
export interface ProjectedScene {
  nodes: ViewNode[];
  routes: ViewRoute[];
  boosters: ViewBooster[];
}

interface Bounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

function bounds(scene: Scene): Bounds {
  const lats: number[] = [];
  const lons: number[] = [];
  const push = (c: Coordinate) => {
    lats.push(c.latitude);
    lons.push(c.longitude);
  };
  scene.nodes.forEach((n) => push(n.location));
  scene.routes.forEach((r) => r.path.forEach(push));
  scene.boosters.forEach((b) => push(b.location));
  return {
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
  };
}

/** Project geographic scene to a WxH view box with equal-aspect scaling. */
export function projectToView(
  scene: Scene,
  width: number,
  height: number,
  pad: number,
): ProjectedScene {
  const b = bounds(scene);
  const spanLon = Math.max(b.maxLon - b.minLon, 1e-6);
  const spanLat = Math.max(b.maxLat - b.minLat, 1e-6);
  const scale = Math.min((width - 2 * pad) / spanLon, (height - 2 * pad) / spanLat);
  const offsetX = (width - spanLon * scale) / 2;
  const offsetY = (height - spanLat * scale) / 2;

  const project = (c: Coordinate): ViewPoint => ({
    x: offsetX + (c.longitude - b.minLon) * scale,
    // Flip latitude so north is up.
    y: offsetY + (b.maxLat - c.latitude) * scale,
  });

  return {
    nodes: scene.nodes.map((n) => ({
      ...project(n.location),
      id: n.id,
      kind: n.kind,
      dim: n.dim,
    })),
    routes: scene.routes.map((r) => ({
      id: r.id,
      mode: r.mode,
      points: r.path.map(project),
    })),
    boosters: scene.boosters.map((b2) => ({ ...project(b2.location), id: b2.id })),
  };
}
