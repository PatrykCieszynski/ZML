export type PlanetId =
    | "arkadia"
    | "calypso"
    | "cyrene"
    | "monria"
    | "next_island"
    | "rocktropia"
    | "toulan";

export type TileCoord = readonly [x: number, y: number];

export type PlanetMapConfig = {
    id: PlanetId;
    name: string;

    tileFolder: string;
    tileSize: number;

    minLon: number;
    maxLon: number;
    minLat: number;
    maxLat: number;

    tileCountX: number;
    tileCountY: number;

    // Some planets do not occupy a full rectangular tile grid.
    // When omitted, every tile inside tileCountX/tileCountY is treated as present.
    availableTiles?: readonly TileCoord[];
};

export type MapConfig = {
    tileSize: number;
    planets: Record<PlanetId, PlanetMapConfig>;
};

export const MAP_CONFIG: MapConfig = {
    tileSize: 512,
    planets: {
        arkadia: {
            id: "arkadia",
            name: "Arkadia",
            tileFolder: "Maps/Arkadia",
            tileSize: 512,
            minLon: 8192,
            maxLon: 32768,
            minLat: 8192,
            maxLat: 32768,
            tileCountX: 3,
            tileCountY: 3,
        },
        calypso: {
            id: "calypso",
            name: "Calypso",
            tileFolder: "Maps/Calypso",
            tileSize: 512,
            minLon: 16384,
            maxLon: 90112,
            minLat: 24576,
            maxLat: 98304,
            tileCountX: 9,
            tileCountY: 9,
            availableTiles: [
                [0, 4], [0, 5], [0, 6], [0, 7], [0, 8],
                [1, 4], [1, 5], [1, 6], [1, 7], [1, 8],
                [2, 4], [2, 5], [2, 6], [2, 7], [2, 8],
                [3, 4],
                [4, 3], [4, 4],
                [5, 1], [5, 2], [5, 3],
                [6, 1], [6, 2], [6, 3],
                [7, 0], [7, 1], [7, 2], [7, 3],
                [8, 0], [8, 1], [8, 2],
            ],
        },
        cyrene: {
            id: "cyrene",
            name: "Cyrene",
            tileFolder: "Maps/Cyrene",
            tileSize: 512,
            minLon: 122880,
            maxLon: 139264,
            minLat: 73728,
            maxLat: 90112,
            tileCountX: 2,
            tileCountY: 2,
        },
        monria: {
            id: "monria",
            name: "Monria",
            tileFolder: "Maps/Monria",
            tileSize: 512,
            minLon: 32768,
            maxLon: 40960,
            minLat: 16384,
            maxLat: 24576,
            tileCountX: 1,
            tileCountY: 1,
        },
        next_island: {
            id: "next_island",
            name: "Next Island",
            tileFolder: "Maps/Next Island",
            tileSize: 512,
            minLon: 122880,
            maxLon: 147456,
            minLat: 81920,
            maxLat: 98304,
            tileCountX: 3,
            tileCountY: 2,
            availableTiles: [
                [0, 0], [0, 1],
                [1, 0], [1, 1],
                [2, 1],
            ],
        },
        rocktropia: {
            id: "rocktropia",
            name: "Rocktropia",
            tileFolder: "Maps/Rocktropia",
            tileSize: 512,
            minLon: 122880,
            maxLon: 139264,
            minLat: 81920,
            maxLat: 98304,
            tileCountX: 2,
            tileCountY: 2,
        },
        toulan: {
            id: "toulan",
            name: "Toulan",
            tileFolder: "Maps/Toulan",
            tileSize: 512,
            minLon: 131072,
            maxLon: 139264,
            minLat: 90112,
            maxLat: 98304,
            tileCountX: 1,
            tileCountY: 1,
        },
    },
};
