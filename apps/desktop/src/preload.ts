import { contextBridge } from "electron";

// expose minimal API; extend later
contextBridge.exposeInMainWorld("zml", {
  ping: () => "pong",
});