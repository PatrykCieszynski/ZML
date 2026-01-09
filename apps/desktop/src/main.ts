import { app, BrowserWindow } from "electron";
import path from "path";

const DEV_URL = process.env.ELECTRON_RENDERER_URL ?? "http://localhost:5173";

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // In dev we load Vite dev server. In production we load the built index.html.
  if (!app.isPackaged) {
    win.loadURL(DEV_URL);
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    // Adjust this path to match where your UI build ends up
    win.loadFile(path.join(__dirname, "../../ui/dist/index.html"));
  }

  return win;
}

app.whenReady().then(() => {
  createMainWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
