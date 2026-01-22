import { getWindowType } from "./getWindowType";
import { MainWindow } from "./windows/MainWindow";
import { MapWindow } from "./windows/MapWindow";

export default function App() {
  const wt = getWindowType();

  if (wt === "map") return <MapWindow />;
  if (wt === "hud") return <div style={{ padding: 16 }}>HUD (todo)</div>;
  return <MainWindow />;
}
