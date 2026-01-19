import { app, BrowserWindow } from "electron";
import path from "path";

const DEV_URL = process.env.VITE_DEV_SERVER_URL ?? "http://localhost:5173";

export function createMainWindow(): BrowserWindow {
    const win = new BrowserWindow({
        width: 1280,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, "../preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    if (!app.isPackaged) {
        win.loadURL(DEV_URL);
        win.webContents.openDevTools({ mode: "detach" });
    } else {
        win.loadFile(path.join(__dirname, "../../ui/dist/index.html"));
    }

    return win;
}
