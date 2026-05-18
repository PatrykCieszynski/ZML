import { lazy, Suspense } from "react";
import { getWindowType } from "./getWindowType";
import { MainWindow } from "./windows/mainWindow.tsx";

const MapWindow = lazy(() => import("./windows/mapWindow.tsx").then((module) => ({ default: module.MapWindow })));

export default function App() {
  const wt = getWindowType();

  if (wt === "map") {
    return (
      <Suspense fallback={<div style={{ position: "fixed", inset: 0, background: "#050505" }} />}>
        <MapWindow />
      </Suspense>
    );
  }
  if (wt === "hud") return <div style={{ padding: 16 }}>HUD (todo)</div>;
  return <MainWindow />;
}
