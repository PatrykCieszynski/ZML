export function getZml() {
    const api = window.zml;
    if (!api) {
        throw new Error("window.zml is missing (not running inside Electron preload?)");
    }
    return api;
}