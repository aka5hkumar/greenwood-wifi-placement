/** Generate a closed circle polygon (as [lon, lat] pairs) around a center point. */
export function circlePolygon(
  lat: number,
  lon: number,
  radiusMeters: number,
  points = 48
): [number, number][] {
  const coords: [number, number][] = [];
  const earthRadius = 6371000;
  const latRad = (lat * Math.PI) / 180;

  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * 2 * Math.PI;
    const dLat = (radiusMeters * Math.cos(angle)) / earthRadius;
    const dLon =
      (radiusMeters * Math.sin(angle)) / (earthRadius * Math.cos(latRad));
    const pointLat = lat + (dLat * 180) / Math.PI;
    const pointLon = lon + (dLon * 180) / Math.PI;
    coords.push([pointLon, pointLat]);
  }
  return coords;
}
