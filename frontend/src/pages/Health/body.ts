/** VO2max and Poids tiles: which ones carry a value (pure, unit-tested). */
import type { HomeHealth } from '@/types/home';

export type BodyKey = 'vo2max' | 'weight';

export const BODY_TILES: ReadonlyArray<{ key: BodyKey; label: string; unit?: string }> = [
  { key: 'vo2max', label: 'home.health.vo2max', unit: 'health.body.vo2maxUnit' },
  { key: 'weight', label: 'home.health.weight' },
];

/** The tiles that carry a value, in display order. */
export function visibleBodyTiles(health: Pick<HomeHealth, BodyKey>): BodyKey[] {
  return BODY_TILES.filter((tile) => health[tile.key]?.value != null).map((tile) => tile.key);
}

export function bodyTilesVisible(health: Pick<HomeHealth, BodyKey>): boolean {
  return visibleBodyTiles(health).length > 0;
}

