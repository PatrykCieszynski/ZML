import { useEffect, useMemo, useRef, useState } from "react";
import { MAP_CONFIG, worldToPixel, type PlanetId } from "@zml/shared";
import { TileLayer } from "./tileLayer";

type MapPoint = { x: number; y: number };
type Offset = { x: number; y: number };

function clamp(v: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, v));
}

export function MapViewport({
                                planetId,
                                point,
                            }: {
    planetId: PlanetId;
    point: MapPoint | null;
}) {
    const planet = MAP_CONFIG.planets[planetId];

    const viewportRef = useRef<HTMLDivElement | null>(null);
    const [scale, setScale] = useState(1);
    const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);

    const dragRef = useRef<{
        pointerId: number;
        sx: number;
        sy: number;
        ox: number;
        oy: number;
    } | null>(null);

    const marker = useMemo(() => {
        if (!point) return null;
        return worldToPixel(MAP_CONFIG, planetId, point.x, point.y);
    }, [planetId, point]);

    useEffect(() => {
        const el = viewportRef.current;
        if (!el) return;

        const onWheel = (e: WheelEvent) => {
            e.preventDefault();

            const rect = el.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;

            setScale((prevScale) => {
                const nextScale = clamp(prevScale * factor, 0.2, 16);

                // Keep point under cursor stable:
                // screen = offset + world * scale
                // world = (screen - offset) / scale
                const worldX = (mx - offset.x) / prevScale;
                const worldY = (my - offset.y) / prevScale;

                const nextOffsetX = mx - worldX * nextScale;
                const nextOffsetY = my - worldY * nextScale;

                setOffset({ x: nextOffsetX, y: nextOffsetY });
                return nextScale;
            });
        };

        el.addEventListener("wheel", onWheel, { passive: false });
        return () => el.removeEventListener("wheel", onWheel);
    }, [offset.x, offset.y]);

    const onPointerDown = (e: React.PointerEvent) => {
        if (e.button !== 0) return;
        const el = viewportRef.current;
        if (!el) return;

        el.setPointerCapture(e.pointerId);
        dragRef.current = { pointerId: e.pointerId, sx: e.clientX, sy: e.clientY, ox: offset.x, oy: offset.y };
        setIsDragging(true);
    };

    const onPointerMove = (e: React.PointerEvent) => {
        const d = dragRef.current;
        if (!d || d.pointerId !== e.pointerId) return;

        const dx = e.clientX - d.sx;
        const dy = e.clientY - d.sy;
        setOffset({ x: d.ox + dx, y: d.oy + dy });
    };

    const endDrag = (e: React.PointerEvent) => {
        const d = dragRef.current;
        if (!d || d.pointerId !== e.pointerId) return;

        dragRef.current = null;
        setIsDragging(false);
    };

    return (
        <div
            ref={viewportRef}
            style={{
                width: "100%",
                height: "100%",
                background: "#0b0b0b",
                overflow: "hidden",
                position: "relative",
                cursor: isDragging ? "grabbing" : "grab",
                userSelect: "none",
            }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onPointerLeave={(e) => {
                if (isDragging) endDrag(e);
            }}
        >
            <div
                style={{
                    transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
                    transformOrigin: "0 0",
                    position: "absolute",
                    left: 0,
                    top: 0,
                    willChange: "transform",
                }}
            >
                <TileLayer planet={planet} />

                {marker && (
                    <div
                        title={point ? `(${point.x}, ${point.y})` : ""}
                        style={{
                            position: "absolute",
                            left: marker.px,
                            top: marker.py,
                            width: 1,
                            height: 1,
                            borderRadius: 999,
                            background: "#44f",
                            transform: "translate(-50%, -50%)",
                            boxShadow: "0 0 0 2px rgba(0,0,0,0.7)",
                            pointerEvents: "none",
                        }}
                    />
                )}
            </div>
        </div>
    );
}
