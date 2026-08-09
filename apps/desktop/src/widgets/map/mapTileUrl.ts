export function buildMapTileUrl(
  appBaseUrl: string,
  tileFolder: string,
  x: number,
  y: number,
): string {
  const baseUrl = appBaseUrl.endsWith("/") ? appBaseUrl : `${appBaseUrl}/`;
  const folder = tileFolder.replace(/^\/+|\/+$/g, "");

  return encodeURI(`${baseUrl}${folder}/x${x}_y${y}.webp`);
}
