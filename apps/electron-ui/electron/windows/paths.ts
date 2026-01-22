import path from "node:path";

export function getIndexHtml(distDir: string): string {
    // distDir should be process.env.DIST (renderer output root)
    return path.join(distDir, "index.html");
}
