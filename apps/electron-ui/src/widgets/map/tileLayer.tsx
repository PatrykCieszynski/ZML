import { useMemo } from "react";
import type { PlanetMapConfig } from "@zml/shared";

type Props = {
    planet: PlanetMapConfig;
};

export function TileLayer({ planet }: Props) {
    const tiles = useMemo(() => {
        // tileFolder should be something like "/maps/Calypso"
        const base = encodeURI(
            planet.tileFolder.startsWith("/") ? planet.tileFolder : `/${planet.tileFolder}`
        );

        const els: JSX.Element[] = [];
        for (let ty = 0; ty < planet.tileCountY; ty++) {
            for (let tx = 0; tx < planet.tileCountX; tx++) {
                const src = `${base}/x${tx}_y${ty}.webp`;

                els.push(
                    <img
                        key={`${tx}-${ty}`}
                        src={src}
                        alt=""
                        draggable={false}
                        loading="lazy"
                        decoding="async"
                        onError={(e) => {
                            // Missing tiles happen; hide the element to avoid broken icons.
                            e.currentTarget.style.display = "none";
                        }}
                        style={{
                            position: "absolute",
                            left: tx * planet.tileSize,
                            top: ty * planet.tileSize,
                            width: planet.tileSize,
                            height: planet.tileSize,
                            userSelect: "none",
                            pointerEvents: "none",
                        }}
                    />
                );
            }
        }
        return els;
    }, [planet.tileCountX, planet.tileCountY, planet.tileSize, planet.tileFolder]);

    return (
        <div
            style={{
                position: "relative",
                width: planet.tileCountX * planet.tileSize,
                height: planet.tileCountY * planet.tileSize,
                background: "#070707",
            }}
        >
            {tiles}
        </div>
    );
}
