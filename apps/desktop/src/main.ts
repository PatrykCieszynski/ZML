import { app, BrowserWindow } from "electron";
import { registerIpc } from "./ipc/registerIpc";
import { createMainWindow } from "./windows/createMainWindow";
import { registerWindow } from "./windows/registry";

app.whenReady().then(() => {
  registerIpc();

  const win = createMainWindow();
  registerWindow("main", win);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const w = createMainWindow();
      registerWindow("main", w);
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
